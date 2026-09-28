"""موتور شبیه‌ساز v2 — ۴۹۵ خودروی واقعی، ورود/خروج منطقی، ردیابی داخل مجموعه."""
import asyncio
import random
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.modules.vehicles.models import Vehicle
from app.realtime.manager import manager

LETTERS = ["ب","ج","د","س","ص","ط","ق","ل","م","ن","و","هـ","ی"]

_state = {"running": False, "task": None, "interval": 4.0, "resident_ratio": 0.8,
          "stats": {"events": 0, "entry": 0, "exit": 0, "violations": 0},
          "inside": {}, "last": None}


def _broadcast(event, data):
    try:
        manager.broadcast_threadsafe(event, data)
    except Exception:
        pass


async def _resident_plates():
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Vehicle).limit(600))).scalars().all()
        return [(v.plate_raw, v.is_active) for v in rows]


def _guest_plate():
    code = random.choice(["11","12","13","14","15","16","22","23","24","28","30","32",
                          "36","46","51","56","63","67","72","77","83","93"])
    letter = random.choice(LETTERS)
    return f"{random.randint(10,99)} {letter} {random.randint(100,999)} ایران {code}"


async def _tick():
    from app.modules.access_control.service import GateDecisionService

    async with AsyncSessionLocal() as db:
        stats = _state["stats"]
        stats["events"] += 1
        inside = _state["inside"]

        if inside and random.random() < 0.45:
            plate_raw = random.choice(list(inside.keys()))
            info = inside.pop(plate_raw)
            gate, direction = "GATE-OUT-01", "OUT"
            kind = info.get("kind", "RESIDENT")
        else:
            plates = await _resident_plates()
            if plates and random.random() < _state["resident_ratio"]:
                plate_raw, active = random.choice(plates)
                kind = "RESIDENT"
            else:
                plate_raw, active = _guest_plate(), True
                kind = "GUEST"
            gate, direction = "GATE-IN-01", "IN"

        try:
            result = await GateDecisionService.process_plate_event(
                db, gate_code=gate, direction=direction, plate_raw=plate_raw,
                source_event_id=f"sim-{datetime.now(timezone.utc).timestamp()}-{random.randint(10000,99999)}",
                confidence=round(random.uniform(90, 99), 1),
                raw_payload={"source": "simulator"})
        except Exception as exc:
            print(f"[simulator] decision error: {exc}")
            return

        decision = result.get("decision")
        if decision in ("DENY", "UNKNOWN_PLATE", "REQUIRE_OPERATOR_APPROVAL", "OFFLINE_REQUIRE_REVIEW"):
            stats["violations"] += 1
        elif direction == "IN":
            stats["entry"] += 1
            inside[plate_raw] = {"since": datetime.now(timezone.utc).isoformat(), "kind": kind}
        else:
            stats["exit"] += 1

        _state["last"] = {"time": datetime.now(timezone.utc).isoformat(),
                          "gate": gate, "direction": direction, "plate": plate_raw,
                          "kind": kind, "decision": decision,
                          "reason": result.get("decision_reason"),
                          "barrier": result.get("barrier_action")}
        _broadcast("simulator.event", {**_state["last"],
                                       "inside_count": len(inside), "stats": dict(stats)})


async def _loop():
    while _state["running"]:
        try:
            await _tick()
        except Exception as exc:
            print(f"[simulator] loop error: {exc}")
        await asyncio.sleep(_state["interval"])


def start(interval=4.0, resident_ratio=0.8):
    if _state["running"]:
        return False
    _state["running"] = True
    _state["interval"] = max(1.0, float(interval))
    _state["resident_ratio"] = min(0.95, max(0.1, float(resident_ratio)))
    _state["stats"] = {"events": 0, "entry": 0, "exit": 0, "violations": 0}
    _state["inside"] = {}
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
            "inside_count": len(_state["inside"]), "last": _state.get("last")}


async def inside_report():
    from app.shared.dt import as_utc
    now = datetime.now(timezone.utc)
    items = []
    for plate, info in list(_state["inside"].items()):
        dur = (now - as_utc(datetime.fromisoformat(info["since"]))).total_seconds()
        items.append({"plate": plate, "kind": info["kind"], "seconds": int(dur)})
    items.sort(key=lambda x: -x["seconds"])
    return {"count": len(items), "items": items[:50]}


async def durations_report(limit=30):
    from sqlalchemy import select
    from app.modules.access_control.models import AccessEvent
    from app.modules.vehicles.models import Vehicle
    from app.modules.residents.models import Person
    from app.modules.complexes.models import Tower, Unit
    from app.shared.dt import as_utc

    async with AsyncSessionLocal() as db:
        events = (await db.execute(
            select(AccessEvent)
            .where(AccessEvent.plate_normalized.isnot(None))
            .order_by(AccessEvent.event_time.desc()).limit(400))).scalars().all()

        last_in, out = {}, []
        for ev in reversed(events):
            p = ev.plate_normalized
            if ev.event_type == "ENTRY":
                last_in[p] = as_utc(ev.event_time)
            elif ev.event_type == "EXIT" and p in last_in:
                secs = int((as_utc(ev.event_time) - last_in[p]).total_seconds())
                if secs > 0:
                    out.append({"plate": p, "seconds": secs,
                                "from": last_in[p].isoformat(),
                                "to": as_utc(ev.event_time).isoformat()})
                last_in.pop(p, None)
        out = list(reversed(out))[:limit]

        enriched = []
        for it in out:
            v = (await db.execute(select(Vehicle).where(
                Vehicle.plate_normalized == it["plate"]))).scalars().first()
            row = {**it, "kind": "RESIDENT" if v else "GUEST",
                   "owner": None, "unit": None, "tower": None,
                   "province": (v.plate_province if v else None),
                   "city": (v.plate_city if v else None)}
            if v:
                if v.owner_person_id:
                    p = await db.get(Person, v.owner_person_id)
                    if p:
                        row["owner"] = f"{p.first_name} {p.last_name}"
                if v.unit_id:
                    u = await db.get(Unit, v.unit_id)
                    if u:
                        row["unit"] = u.unit_number
                        t = await db.get(Tower, u.tower_id)
                        row["tower"] = (t.name if t else None)
            enriched.append(row)
        return {"items": enriched}