import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

# مهم: همه ماژول‌های مدل باید import شوند تا SQLAlchemy بتواند
# کلیدهای خارجی (persons, units, complexes, ...) را resolve کند
for _mod in [
    "app.modules.identity.models",
    "app.modules.complexes.models",
    "app.modules.residents.models",
    "app.modules.vehicles.models",
    "app.modules.parking.models",
    "app.modules.devices.models",
    "app.modules.access_control.models",
    "app.core.system_models",
]:
    try:
        __import__(_mod)  # noqa: E402
    except ModuleNotFoundError:
        pass

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.modules.access_control.models import AccessEvent, ParkingSession  # noqa: E402
from app.modules.parking.models import ParkingAssignment, ParkingOccupancy  # noqa: E402
from app.modules.vehicles.models import AccessPermit, Vehicle  # noqa: E402


async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Vehicle).order_by(Vehicle.created_at.asc()))
        vehicles = result.scalars().all()
        seen: dict[str, Vehicle] = {}
        removed = 0
        kept_dupes = 0
        for v in vehicles:
            if v.plate_normalized in seen:
                perms = (await db.execute(select(AccessPermit).where(AccessPermit.vehicle_id == v.id))).scalars().all()
                events = (await db.execute(select(AccessEvent).where(AccessEvent.vehicle_id == v.id))).scalars().all()
                occs = (await db.execute(select(ParkingOccupancy).where(ParkingOccupancy.vehicle_id == v.id))).scalars().all()
                assigns = (await db.execute(select(ParkingAssignment).where(ParkingAssignment.vehicle_id == v.id))).scalars().all()
                sessions = (await db.execute(select(ParkingSession).where(ParkingSession.vehicle_id == v.id))).scalars().all()
                if not any([perms, events, occs, assigns, sessions]):
                    await db.delete(v)
                    removed += 1
                    print(f">>> حذف تکراری: {v.plate_normalized} (id={v.id[:8]}...) — نسخه اصلی حفظ شد")
                else:
                    kept_dupes += 1
                    print(f">>> تکراری دارای ارجاع، حفظ شد: {v.plate_normalized} (id={v.id[:8]}...)")
            else:
                seen[v.plate_normalized] = v
        await db.commit()
        print(f"OK — {removed} رکورد حذف شد، {kept_dupes} رکورد تکراری دارای ارجاع حفظ شد")


if __name__ == "__main__":
    asyncio.run(main())