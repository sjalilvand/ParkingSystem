"""گارد ظرفیت محوطه (سند §۹/§۱۱ — REQ-09-03/REQ-11-05).
تفکیک صریح: ظرفیت اعلامی (پیکربندی) در برابر حضور فیزیکی تأییدشده (occupancyهای OCCUPIED)."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.parking.models import ParkingOccupancy


def yard_capacity_decision(declared: int | None, confirmed: int) -> tuple[bool, str]:
    """خالص و قابل تست. None/0 = بدون محدودیت."""
    if declared is None or declared <= 0:
        return True, "OK"
    if confirmed >= declared:
        return False, "YARD_CAPACITY_FULL"
    return True, "OK"


async def count_confirmed_occupancy(db: AsyncSession) -> int:
    res = await db.execute(
        select(func.count()).select_from(ParkingOccupancy)
        .where(ParkingOccupancy.status == "OCCUPIED")
    )
    return int(res.scalar() or 0)


async def check_yard_capacity(db: AsyncSession, settings) -> tuple[bool, str]:
    declared = getattr(settings, "YARD_CAPACITY_TOTAL", None)
    if declared is None or declared <= 0:
        return True, "OK"
    confirmed = await count_confirmed_occupancy(db)
    return yard_capacity_decision(declared, confirmed)
