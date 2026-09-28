import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, "/app")

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.modules.vehicles.models import AccessPermit, Vehicle


async def main():
    async with AsyncSessionLocal() as db:
        vehicles = (await db.execute(select(Vehicle))).scalars().all()
        existing = set((await db.execute(select(AccessPermit.plate_normalized))).scalars().all())
        added = 0
        for v in vehicles:
            if v.plate_normalized in existing:
                continue
            db.add(AccessPermit(vehicle_id=v.id, plate_normalized=v.plate_normalized,
                                permit_type="PERMANENT", status="ACTIVE"))
            added += 1
        await db.commit()
        print(f"[permits] vehicles={len(vehicles)} added_permits={added}")


asyncio.run(main())