import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.modules.base_data.models import PlateRegion  # noqa: E402

# مسیر CSV در ریشه پروژه (کنار پوشه‌های backend/frontend)
CSV_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "IranPlates_Full.csv",
    Path(__file__).resolve().parents[1] / "IranPlates_Full.csv",
]


def find_csv() -> Path:
    for p in CSV_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "IranPlates_Full.csv یافت نشد — فایل را در ریشه پروژه (D:\\Projects\\ParkingSystem) قرار دهید"
    )


def parse_rows(csv_path: Path):
    """پارس CSV با جداکننده | یا , یا ; — حذف ستون id عددی و هدر."""
    text = csv_path.read_text(encoding="utf-8-sig")
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        sep = "|" if "|" in line else (";" if ";" in line else ",")
        parts = [p.strip() for p in line.split(sep)]
        parts = [p for p in parts if p]
        if not parts:
            continue
        # حذف هدر (اگر ستون دوم عددی نیست)
        if parts[1] if len(parts) > 1 else "":
            if not parts[1].isdigit():
                continue
        # حذف ستون id عددی ابتدای خط
        if len(parts) >= 5 and parts[0].isdigit():
            parts = parts[1:]
        if len(parts) < 4:
            continue
        code, province, city, letters = parts[0], parts[1], parts[2], parts[3]
        if not code.isdigit() or len(code) > 2:
            continue
        rows.append((code, province, city, letters))
    return rows


async def seed_plate_regions():
    csv_path = find_csv()
    print(f">>> خواندن CSV: {csv_path}")
    rows = parse_rows(csv_path)
    print(f">>> ردیف‌های معتبر: {len(rows)}")

    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(func.count()).select_from(PlateRegion))
        if existing and existing >= len(rows):
            print(f"OK - plate_regions already seeded ({existing}) — skip")
            return

        added = 0
        for code, province, city, letters in rows:
            dup = (await db.execute(select(PlateRegion).where(
                PlateRegion.plate_code == code,
                PlateRegion.city == city,
                PlateRegion.letters == letters,
            ))).scalar_one_or_none()
            if dup is None:
                db.add(PlateRegion(plate_code=code, province=province,
                                   city=city, letters=letters))
                added += 1
        await db.commit()

    total = (await AsyncSessionLocal().execute(
        select(func.count()).select_from(PlateRegion))).scalar()
    print(f"OK - plate_regions seeded: added={added}, total={total}")


if __name__ == "__main__":
    asyncio.run(seed_plate_regions())