import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.modules.complexes.models import Complex, Tower  # noqa: E402
from app.modules.parking.models import ParkingSpace  # noqa: E402

TOWERS = [("T-A", "برج A"), ("T-B", "برج B"), ("T-C", "برج C")]
FLOORS = [-1, -2]


async def seed_parking_map():
    async with AsyncSessionLocal() as db:
        comp = (await db.execute(select(Complex).where(Complex.code == "C1"))).scalar_one_or_none()
        if comp is None:
            comp = Complex(code="C1", name="مجتمع نمونه", address="تهران")
            db.add(comp)
            await db.flush()

        for code, name in TOWERS:
            tower = (await db.execute(select(Tower).where(Tower.code == code))).scalar_one_or_none()
            if tower is None:
                tower = Tower(complex_id=comp.id, code=code, name=name, floor_count=10)
                db.add(tower)
                await db.flush()
                print(f">>> tower created: {name}")

            letter = code.split("-")[1]
            for floor in FLOORS:
                space_code = f"{letter}-B{abs(floor)}-1"
                dup = (await db.execute(select(ParkingSpace).where(ParkingSpace.code == space_code))).scalar_one_or_none()
                if dup is None:
                    db.add(ParkingSpace(complex_id=comp.id, tower_id=tower.id,
                                        code=space_code, number="1", floor=floor,
                                        zone=letter, parking_type="PRIVATE"))
                    print(f">>> space created: {space_code}")

        # پارکینگ دفنی (بدون برج — زیر مجموعه برج‌ها)
        for floor in FLOORS:
            for n in (1, 2):
                space_code = f"D-B{abs(floor)}-{n}"
                dup = (await db.execute(select(ParkingSpace).where(ParkingSpace.code == space_code))).scalar_one_or_none()
                if dup is None:
                    db.add(ParkingSpace(complex_id=comp.id, tower_id=None,
                                        code=space_code, number=str(n), floor=floor,
                                        zone="D", parking_type="PRIVATE"))
                    print(f">>> buried space created: {space_code}")

        await db.commit()
    print("OK - parking map seeded (A/B/C + buried)")


if __name__ == "__main__":
    asyncio.run(seed_parking_map())