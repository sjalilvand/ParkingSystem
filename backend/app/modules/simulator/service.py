"""موتور شبیه‌ساز تردد — از همان مسیر واقعی گیت (GateDecisionService) عبور می‌دهد."""
import asyncio
import random
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.modules.base_data.models import PlateRegion
from app.modules.vehicles.models import Vehicle
from app.realtime.manager import manager

_letters_fa = ["الف", "ب", "پ", "ت", "ث", "ج", "د", "س", "ص", "ط",
               "ع", "ف", "ق", "ک", "گ", "ل", "م", "ن", "و", "هـ", "ی"]
_brands = ["پژو", "سایپا", "ایران‌خودرو", "کیا", "هیوندای", "تویوتا", "ام‌وی‌ام", "چری"]
_models = ["206", "Pride", "سمند", "سراتو", "النترا", "کمری", "Dena", "تیگو 7"]
_colors = ["سفید", "نقره‌ای", "مشکی", "خاکستری", "آبی", "قرمز"]

_state = {"running": False, "task": None, "interval": 4.0,
          "resident_ratio": 0.6,
          "stats": {"events": 0, "entry": 0, "exit": 0, "violations": 0},
          "last": None}


def _rand_plate_parts():
    code = random.choice(["11", "12", "22", "28", "30", "36", "46", "51", "63", "67", "77", "93"])
    letter = random.choice(_letters_fa)
    three = str(random.randint(100, 999))
    return code, letter, three


def _broadcast(event, data):
    try:
        manager.broadcast_threadsafe(event, data)
    except Exception:
        pass


async def _ensure_residents(count=12):
    async with AsyncSessionLocal() as db:
        vehicles = (await db.execute(select(Vehicle).limit(count))).scalars().all()
        if len(vehicles) >= 5:
            return [v.plate_raw for v in vehicles]
        regions = (await db.execute(select(PlateRegion).limit(20))).scalars().all()
        created = []
        for i in range(count):
            code, letter, three = _rand_plate_parts()
            raw = f"{code} {letter} {three} ایران {code}"
            reg = regions[i % len(regions)] if regions else None
            db.add(Vehicle(plate_raw=raw, plate_normalized=f"{code}{letter}{three}IR{code}",
                           plate_letter=letter, plate_province_code=code,
                           plate_province=(reg.province if reg else "تهران"),
                           plate_city=(reg.city if reg else "تهران"),
                           brand=random.choice(_brands), model=random.choice(_models),
                           color=random.choice(_colors), year=random.randint(1395, 1404),
                           is_active=(i % 7 != 0)))
            created.append(raw)
        await db.commit()
        print(f"[simulator] created {len(created)} fake resident vehicles")
        return created


async def _tick():
    from app.modules.access_control.service import GateDecisionService

    async with AsyncSessionLocal() as db:
        stats = _state["stats"]
        plates = await _ensure_residents()
        stats["events"] += 1

        gate = random.choice(["GATE-IN-01", "GATE-OUT-01"])
        direction = "IN" if gate == "GATE-IN-01" else "OUT"

        if direction == "IN" and random.random() > _state["resident_ratio"]:
            raw = _rand_plate_parts() and "{0} {1} {2} ایران {0}".format(*_rand_plate_parts())
        else:
            raw = random.choice(plates)

        try:
            result = await GateDecisionService.process_plate_event(
                db, gate_code=gate, direction=direction, plate_raw=raw,
                source_event_id=f"sim-{datetime.now(timezone.utc).timestamp()}-{random.randint(1000,9999)}",
                confidence=round(random.uniform(88, 99), 1),
                raw_payload={"source": "simulator"})
        except Exception as exc:
            print(f"[simulator] decision error: {exc}")
            return

        decision = result.get("decision")
        stats["entry" if direction == "IN" else "exit"] += 1
        if decision in ("DENY", "UNKNOWN_PLATE", "REQUIRE_OPERATOR_APPROVAL", "OFFLINE_REQUIRE_REVIEW"):
            stats["violations"] += 1

        _state["last"] = {"time": datetime.now(timezone.utc).isoformat(),
                          "gate": gate, "direction": direction, "plate": raw,
                          "decision": decision, "reason": result.get("decision_reason"),
                          "barrier": result.get("barrier_action")}
        _broadcast("simulator.event", {**_state["last"], "stats": dict(stats)})


async def _loop():
    while _state["running"]:
        try:
            await _tick()
        except Exception as exc:
            print(f"[simulator] loop error: {exc}")
        await asyncio.sleep(_state["interval"])


def start(interval=4.0, resident_ratio=0.6):
    if _state["running"]:
        return False
    _state["running"] = True
    _state["interval"] = max(1.0, float(interval))
    _state["resident_ratio"] = min(0.95, max(0.1, float(resident_ratio)))
    _state["stats"] = {"events": 0, "entry": 0, "exit": 0, "violations": 0}
    _state["task"] = asyncio.create_task(_loop())
    return True


def stop():
    if not _state["running"]:
        return False
    _state["running"] = False
    if _state["task"]:
        _state["task"].cancel()
    _state["task"] = None
    return True


def status():
    return {"running": _state["running"], **_state["stats"],
            "interval": _state["interval"], "resident_ratio": _state["resident_ratio"],
            "last": _state.get("last")}