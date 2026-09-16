import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.modules.base_data.models import PlateRegion  # noqa: E402
from app.modules.vehicles.models import Vehicle  # noqa: E402


async def main():
    async with AsyncSessionLocal() as db:
        regions = (await db.execute(select(PlateRegion))).scalars().all()
        by_code: dict[str, list] = {}
        for r in regions:
            by_code.setdefault(r.plate_code, []).append(r)

        vehicles = (await db.execute(
            select(Vehicle).where(Vehicle.plate_province.is_(None))
        )).scalars().all()
        fixed = 0
        for v in vehicles:
            if not v.plate_letter or not v.plate_province_code:
                continue
            letter = v.plate_letter.strip()
            for r in by_code.get(v.plate_province_code, []):
                if letter in (r.letters or "").split():
                    v.plate_province = r.province
                    v.plate_city = r.city
                    fixed += 1
                    break
        await db.commit()
        print(f">>> backfill done: {fixed} vehicle(s) updated (of {len(vehicles)} candidates)")


if __name__ == "__main__":
    asyncio.run(main())