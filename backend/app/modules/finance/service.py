import math
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access_control.models import ParkingSession
from app.modules.finance.models import Charge, Tariff


def calculate_amounts(tariff: Tariff | None, duration_seconds: int) -> dict:
    """محاسبه خالص مبلغ (ریال/BIGINT) — قابل تست واحد. سقف روزانه اعمال می‌شود."""
    if duration_seconds is None or duration_seconds < 0:
        duration_seconds = 0
    if tariff is None:
        return {"base": 0, "penalty": 0, "discount": 0, "final": 0, "warnings": ["NO_ACTIVE_TARIFF"]}

    free_seconds = (tariff.free_minutes or 0) * 60
    billable = max(0, duration_seconds - free_seconds)
    if billable == 0:
        return {"base": 0, "penalty": 0, "discount": 0, "final": 0, "warnings": []}

    hours = math.ceil(billable / 3600)
    base = hours * (tariff.hourly_amount or 0)

    warnings = []
    if tariff.daily_max_amount:
        total_days = max(1, math.ceil(duration_seconds / 86400))
        cap = tariff.daily_max_amount * total_days
        if base > cap:
            base = cap
            warnings.append("DAILY_CAP_APPLIED")

    return {"base": int(base), "penalty": 0, "discount": 0, "final": int(base), "warnings": warnings}


async def get_active_tariff(db: AsyncSession, now: datetime) -> Tariff | None:
    result = await db.execute(
        select(Tariff).where(Tariff.status == "ACTIVE").order_by(Tariff.priority.desc(), Tariff.created_at.desc())
    )
    for t in result.scalars().all():
        if t.valid_from and now < t.valid_from:
            continue
        if t.valid_until and now > t.valid_until:
            continue
        return t
    return None


async def close_session_amounts(db: AsyncSession, session: ParkingSession) -> dict:
    """بستن مالی نشست: محاسبه مبلغ + ساخت Charge. خروجی شامل warnings."""
    now = datetime.now(timezone.utc)
    duration = max(0, int((now - session.entry_at).total_seconds()))
    session.duration_seconds = duration
    tariff = await get_active_tariff(db, now)
    amounts = calculate_amounts(tariff, duration)
    session.tariff_id = tariff.id if tariff else None
    session.base_amount = amounts["base"]
    session.penalty_amount = amounts["penalty"]
    session.discount_amount = amounts["discount"]
    session.final_amount = amounts["final"]
    if amounts["final"] > 0:
        db.add(Charge(
            parking_session_id=session.id, charge_type="PARKING",
            amount=amounts["final"],
            description=f"PARKING {duration}s tariff={tariff.title if tariff else '-'}",
        ))
    return amounts