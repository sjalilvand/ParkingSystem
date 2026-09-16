from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.complexes.models import Tower, Unit
from app.modules.parking.models import ParkingAssignment, ParkingSpace


async def find_assigned_space(db: AsyncSession, vehicle) -> ParkingSpace | None:
    if vehicle is None:
        return None
    result = await db.execute(
        select(ParkingSpace)
        .join(ParkingAssignment, ParkingAssignment.parking_space_id == ParkingSpace.id)
        .where(
            ParkingAssignment.vehicle_id == vehicle.id,
            ParkingAssignment.status == "ACTIVE",
        )
        .limit(1)
    )
    return result.scalars().first()


async def vehicle_unit_info(db: AsyncSession, vehicle) -> dict | None:
    if vehicle is None or not vehicle.unit_id:
        return None
    unit = await db.get(Unit, vehicle.unit_id)
    if not unit:
        return None
    tower = await db.get(Tower, unit.tower_id)
    return {"tower": tower.name if tower else None, "unit_number": unit.unit_number}