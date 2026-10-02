"""گارد ظرفیت محوطه (§۹/§۱۱ — REQ-09-03/REQ-11-05) — موج ۵i:
منبع ظرفیت: تنظیمات نسخه‌بندی‌شدهٔ DB (طراح: کلید yard_capacity) → متغیر محیطی → نامحدود."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.config_admin.models import AppSetting
from app.modules.parking.models import ParkingOccupancy, ParkingSpace


def yard_capacity_decision(declared: int | None, confirmed: int) -> tuple[bool, str]:
    """خالص و قابل تست. None/0 = بدون محدودیت."""
    if declared is None or declared <= 0:
        return True, "OK"
    if confirmed >= declared:
        return False, "YARD_CAPACITY_FULL"
    return True, "OK"


async def get_declared_yard_capacity(db: AsyncSession) -> tuple[int | None, str]:
    """اولویت: تنظیمات طراح (DB) → env → نامحدود. خروجی: (مقدار، منبع)."""
    try:
        row = (await db.execute(
            select(AppSetting).where(AppSetting.key == "yard_capacity"))).scalar_one_or_none()
        if row and isinstance(row.value, dict):
            v = row.value.get("total")
            if isinstance(v, int) and v > 0:
                return v, "setting"
    except Exception:
        pass
    env_v = getattr(settings, "YARD_CAPACITY_TOTAL", None)
    if env_v and env_v > 0:
        return int(env_v), "env"
    return None, "unlimited"


async def count_yard_spaces(db: AsyncSession) -> int:
    return int(await db.scalar(
        select(func.count()).select_from(ParkingSpace).where(
            ParkingSpace.parking_type == "YARD", ParkingSpace.is_active.is_(True))) or 0)


async def count_confirmed_occupancy(db: AsyncSession) -> int:
    res = await db.execute(
        select(func.count()).select_from(ParkingOccupancy)
        .where(ParkingOccupancy.status == "OCCUPIED"))
    return int(res.scalar() or 0)


async def check_yard_capacity(db: AsyncSession, settings) -> tuple[bool, str]:
    declared, _src = await get_declared_yard_capacity(db)
    if declared is None:
        return True, "OK"
    confirmed = await count_confirmed_occupancy(db)
    return yard_capacity_decision(declared, confirmed)
