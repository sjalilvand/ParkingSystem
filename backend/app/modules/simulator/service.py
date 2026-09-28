"""موتور شبیه‌ساز v3 — مجوز ساکن/مهمان، آمار تفکیکی، استان/شهرستان، بیشترین توقف."""
import asyncio
import random
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.modules.base_data.models import PlateRegion
from app.modules.vehicles.models import Vehicle
from app.realtime.manager import manager
from app.shared.plate import normalize_plate

LETTERS = ["ب","ج","د","س","ص","ط","ق","ل","م","ن","و","هـ","ی"]
DENY_SET = {"DENY", "UNKNOWN_PLATE", "REQUIRE_OPERATOR_APPROVAL", "OFFLINE_REQUIRE_REVIEW"}

_state = {"running": False, "task": None, "interval": 4.0,
          "resident_ratio": 0.8, "guest_permit_ratio": 0.7,
          "stats": {"events": 0, "entry": 0, "exit": 0, "violations": 0,
                    "resident_entries": 0, "guest_entries": 0},
          "by_province": {}, "inside": {}, "last": None, "_rcache": {}}


def _broadcast(event, data):
    try:
        manager.broadcast_threadsafe(event, data)
    except Exception:
        pass


async def _resolve_region(raw: str):
    """استان/شهرستان از پلاک خام (کد بعد از ایران + حرف)."""
    m = re.search(r"ایران\s*(\d{2})", raw)
    if not m:
        return None, None
    code = m.group(1)
    letter = None
    for tok in raw.split():
        if tok == "ایران" or tok.isdigit():
            continue
        if all("\u0600" <= ch <= "\u06FF" for ch in tok.replace("\u0640", "")):
            letter = tok.replace("\u0640", "")
            break
    key = f"{code}|{letter}"
    if key in _state["_rcache"]:
        return _state["_rcache"][key]
    prov = city = None
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(PlateRegion).where(
            PlateRegion.plate_code == code))).scalars().all()
        for r in rows:
            ls = {t.replace("\u0640", "").strip() for t in (r.letters or "").split()}
            if letter and letter in ls:
                prov, city = r.province, r.city
                break
        if prov is None and rows:
            prov, city = rows[0].province, rows[0].city
    _state["_rcache"][key] = (prov, city)
    return prov, city


async def _resident_plates():
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Vehicle).limit(600))).scalars().all()
        return [(v.plate_raw, v.is_active, v.plate_province, v.plate_city) for v in rows]


def _guest_plate():
    code = random.choice(["11","12","13","14","15","16","22","23","24","28","30","32",
                          "36","46","51","56","63","67","72","77","83","93"])
    letter = random.choice(LETTERS)
    return f"{random.randint(10,99)} {letter} {random.randint(100,999)} ایران {code}"


async def _grant_guest_permit(raw: str):
    norm = normalize_plate(raw) or raw
    async with AsyncSessionLocal() as db:
        db.add(AccessPermit := __import__("app.modules.vehicles.models", fromlist=["AccessPermit"]).AccessPermit(
            plate_normalized=norm, permit_type="GUEST",
            valid_from=datetime.now(timezone.utc),
            valid_until=datetime.now(timezone.utc) + timedelta(hours=3),
            status="ACTIVE"))
        await db.commit()


async def _tick():
    from app.modules.access_control.service import GateDecisionService

    async with AsyncSessionLocal() as db:
        stats = _state["stats"]
        stats["events"] += 1
        inside = _state["inside"]

        if inside and random.random() < 0.5:
            plate_raw = random.choice(list(inside.keys()))
            info = inside.pop(plate_raw)
            gate, direction = "GATE-OUT-01", "OUT"
            kind = info.get("kind", "RESIDENT")
            prov, city = info.get("province"), info.get("city")
        else:
            plates = await _resident_plates()
            free = [(p, pr, ci) for (p, a, pr, ci) in plates if p not in inside]
            if free and random.random() < _state["resident_ratio"]:
                plate_raw, prov, city = random.choice(free)
                kind = "RESIDENT"
                if not prov:
                    prov, city = await _resolve_region(plate_raw)
            else:
                plate_raw = _guest_plate()
                kind = "GUEST"
                if random.random() < _state["guest_permit_ratio"]:
                    await _grant_guest_permit(plate_raw)
                prov, city = await _resolve_region(plate_raw)
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
        allowed = decision in ("ALLOW", "ALLOW_WITH_WARNING")

        if decision in DENY_SET:
            stats["violations"] += 1
        elif allowed and direction == "IN":
            stats["entry"] += 1
            if kind == "RESIDENT":
                stats["resident_entries"] += 1
            else:
                stats["guest_entries"] += 1
            if prov:
                _state["by_province"][prov] = _state["by_province"].get(prov, 0) + 1
            inside[plate_raw] = {"since": datetime.now(timezone.utc).isoformat(),
                                 "kind": kind, "province": prov, "city": city}
        elif allowed and direction == "OUT":
            stats["exit"] += 1

        _state["last"] = {"time": datetime.now(timezone.utc).isoformat(),
                          "gate": gate, "direction": direction, "plate": plate_raw,
                          "kind": kind, "decision": decision,
                          "reason": result.get("decision_reason"),
                          "barrier": result.get("barrier_action"),
                          "province": prov, "city": city,
                          "inside_count": len(inside)}
        _broadcast("simulator.event", {**_state["last"], "stats": dict(stats)})


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
    _state["stats"] = {"events": 0, "entry": 0, "exit": 0, "violations": 0,
                       "resident_entries": 0, "guest_entries": 0}
    _state["by_province"] = {}
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
    from app.shared.dt import as_utc
    now = datetime.now(timezone.utc)
    mx = 0
    for info in _state["inside"].values():
        try:
            d = (now - as_utc(datetime.fromisoformat(info["since"]))).total_seconds()
            mx = max(mx, int(d))
        except Exception:
            pass
    top = sorted(_state["by_province"].items(), key=lambda x: -x[1])[:12]
    s = dict(_state["stats"])
    return {"running": _state["running"], **s,
            "interval": _state["interval"], "resident_ratio": _state["resident_ratio"],
            "inside_count": len(_state["inside"]),
            "max_stay_seconds": int(mx),
            "by_province": dict(top), "provinces_total": len(_state["by_province"]),
            "last": _state.get("last")}


async def inside_report():
    from app.shared.dt import as_utc
    now = datetime.now(timezone.utc)
    items = []
    for plate, info in list(_state["inside"].items()):
        try:
            d = int((now - as_utc(datetime.fromisoformat(info["since"]))).total_seconds())
        except Exception:
            d = 0
        items.append({"plate": plate, "kind": info.get("kind"),
                      "seconds": d, "province": info.get("province"), "city": info.get("city")})
    items.sort(key=lambda x: -x["seconds"])
    return {"count": len(items), "items": items[:60]}


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
            .order_by(AccessEvent.event_time.desc()).limit(600))).scalars().all()

        last_in, out = {}, []
        for ev in reversed(events):
            p = ev.plate_normalized
            if ev.event_type == "ENTRY":
                last_in[p] = as_utc(ev.event_time)
            elif ev.event_type == "EXIT" and p in last_in:
                secs = int((as_utc(ev.event_time) - last_in[p]).total_seconds())
                if secs > 0:
                    out.append({"plate": p, "seconds": secs,
                                "to": as_utc(ev.event_time).isoformat()})
                last_in.pop(p, None)
        out.sort(key=lambda x: -x["seconds"])
        out = out[:limit]

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