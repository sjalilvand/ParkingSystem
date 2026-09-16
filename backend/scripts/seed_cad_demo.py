import asyncio
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.modules.parking.cad_models import CadParkingSpot  # noqa: E402

BASE = (110.53, 103.26)
ROAD = (5.75, 20.62)
_ln = math.hypot(*ROAD)
RD = (ROAD[0] / _ln, ROAD[1] / _ln)
DP = (RD[1], -RD[0])


async def seed_cad_demo():
    # گارد: اگر Migration جا مانده بود، جدول را خودمان می‌سازیم
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        count = (await db.execute(select(CadParkingSpot))).scalars().all()
        if count:
            print(f"OK - cad spots already exist ({len(count)}) — skip")
            return
        for k in range(6):
            c1 = (BASE[0] + RD[0] * k * 2.5, BASE[1] + RD[1] * k * 2.5)
            c2 = (c1[0] + RD[0] * 2.5, c1[1] + RD[1] * 2.5)
            c3 = (c2[0] + DP[0] * 5.0, c2[1] + DP[1] * 5.0)
            c4 = (c1[0] + DP[0] * 5.0, c1[1] + DP[1] * 5.0)
            poly = [{"x": round(c1[0], 3), "y": round(c1[1], 3)},
                    {"x": round(c2[0], 3), "y": round(c2[1], 3)},
                    {"x": round(c3[0], 3), "y": round(c3[1], 3)},
                    {"x": round(c4[0], 3), "y": round(c4[1], 3)}]
            cx = sum(p["x"] for p in poly) / 4
            cy = sum(p["y"] for p in poly) / 4
            db.add(CadParkingSpot(
                parking_code=f"D-{k + 1:02d}", display_name=f"جایگاه رمپ D-{k + 1:02d}",
                source_drawing="A", source_layer="Limit", source_entity_handle="MANUAL",
                polygon_json=poly, center_x=cx, center_y=cy, area=12.5,
                status="free", parking_type="normal", confidence=1.0,
            ))
        await db.commit()
    print("OK - 6 demo cad spots seeded (ramp area)")


if __name__ == "__main__":
    asyncio.run(seed_cad_demo())