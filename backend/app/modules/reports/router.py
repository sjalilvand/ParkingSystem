from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.modules.access_control.models import AccessEvent, ParkingSession
from app.modules.devices.models import Device, Gate
from app.modules.finance.models import Charge
from app.modules.identity.models import User
from app.modules.violations.models import Violation

router = APIRouter(prefix="/reports", tags=["Reports"])

try:
    TEHRAN = ZoneInfo("Asia/Tehran")
except Exception:
    TEHRAN = timezone(timedelta(hours=3, minutes=30))


@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async def count(stmt) -> int:
        return await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    present = await count(select(ParkingSession.id).where(ParkingSession.status == "OPEN"))
    entries_today = await count(select(AccessEvent.id).where(
        AccessEvent.event_time >= today_start,
        AccessEvent.event_type.in_(["ENTRY", "MANUAL_ENTRY"])))
    exits_today = await count(select(AccessEvent.id).where(
        AccessEvent.event_time >= today_start, AccessEvent.event_type == "EXIT"))
    denied_today = await count(select(AccessEvent.id).where(
        AccessEvent.event_time >= today_start,
        AccessEvent.decision.in_(["DENY", "UNKNOWN_PLATE"])))
    violations_today = await count(select(Violation.id).where(Violation.occurred_at >= today_start))
    gates_online = await count(select(Gate.id).where(Gate.status == "ONLINE"))
    gates_total = await count(select(Gate.id))
    devices_error = await count(select(Device.id).where(Device.status == "ERROR"))

    unpaid_total = await db.scalar(
        select(func.coalesce(func.sum(Charge.amount), 0)).where(Charge.status == "UNPAID")) or 0

    return {
        "present_vehicles": present,
        "entries_today": entries_today,
        "exits_today": exits_today,
        "denied_today": denied_today,
        "unpaid_total": int(unpaid_total),
        "violations_today": violations_today,
        "gates_online": gates_online,
        "gates_total": gates_total,
        "devices_error": devices_error,
        "generated_at": now.isoformat(),
    }


@router.get("/hourly-traffic")
async def hourly_traffic(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """ترافیک ساعتی امروز به وقت تهران: ۲۴ باکت (ورود/خروج)."""
    now_teh = datetime.now(TEHRAN)
    day_start_teh = now_teh.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = day_start_teh.astimezone(timezone.utc)

    rows = (await db.execute(
        select(AccessEvent.event_time, AccessEvent.event_type)
        .where(
            AccessEvent.event_time >= start_utc,
            AccessEvent.event_type.in_(["ENTRY", "MANUAL_ENTRY", "EXIT"]),
        )
        .limit(10000)
    )).all()

    buckets = [{"hour": h, "label": f"{h:02d}", "entries": 0, "exits": 0} for h in range(24)]
    for event_time, etype in rows:
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)
        h = event_time.astimezone(TEHRAN).hour
        if etype in ("ENTRY", "MANUAL_ENTRY"):
            buckets[h]["entries"] += 1
        else:
            buckets[h]["exits"] += 1

    return {"date": day_start_teh.date().isoformat(), "timezone": "Asia/Tehran", "items": buckets}


@router.get("/access-events")
async def access_events(page: int = 1, page_size: int = 50, decision: str | None = None,
                        db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(AccessEvent)
    if decision:
        query = query.where(AccessEvent.decision == decision)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    result = await db.execute(
        query.order_by(AccessEvent.event_time.desc()).offset((page - 1) * page_size).limit(page_size))
    items = [{
        "id": e.id, "gate_id": e.gate_id, "plate_normalized": e.plate_normalized,
        "event_type": e.event_type, "decision": e.decision, "decision_reason": e.decision_reason,
        "event_time": e.event_time.isoformat(), "is_manual": e.is_manual,
        "offline_created": e.offline_created, "idempotency_key": e.idempotency_key,
    } for e in result.scalars().all()]
    return {"items": items, "page": page, "page_size": page_size,
            "total_items": total, "total_pages": (total + page_size - 1) // page_size}


@router.get("/current-vehicles")
async def current_vehicles(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(ParkingSession).where(ParkingSession.status == "OPEN")
        .order_by(ParkingSession.entry_at.desc()).limit(500))
    return [{
        "id": s.id, "plate_normalized": s.plate_normalized,
        "entry_at": s.entry_at.isoformat(),
        "duration_seconds": int((now - s.entry_at).total_seconds()),
    } for s in result.scalars().all()]


@router.get("/long-stays")
async def long_stays(min_hours: int = 24, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    threshold = now.timestamp() - min_hours * 3600
    result = await db.execute(
        select(ParkingSession).where(ParkingSession.status == "OPEN").limit(1000))
    items = []
    for s in result.scalars().all():
        if s.entry_at.timestamp() < threshold:
            items.append({"id": s.id, "plate_normalized": s.plate_normalized,
                          "entry_at": s.entry_at.isoformat(),
                          "duration_hours": round((now - s.entry_at).total_seconds() / 3600, 1)})
    return items


@router.get("/devices")
async def devices_report(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    gates = (await db.execute(select(Gate))).scalars().all()
    devices = (await db.execute(select(Device))).scalars().all()
    return {
        "gates": [{"code": g.code, "status": g.status,
                   "last_seen_at": g.last_seen_at.isoformat() if g.last_seen_at else None} for g in gates],
        "devices": [{"type": d.device_type, "status": d.status, "gate_id": d.gate_id} for d in devices],
    }