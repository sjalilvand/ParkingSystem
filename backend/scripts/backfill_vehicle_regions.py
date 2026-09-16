import asyncio, re, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

_DIG = str.maketrans("\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669", "01234567890123456789")


def norm_letter(s):
    s = str(s).replace("\u0640", "").replace("\u0643", "\u06a9").replace("\u064a", "\u06cc").replace("\u0649", "\u06cc")
    return re.sub(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069]", "", s).strip()


async def main():
    from scripts._dbpick import pick_database, activate
    url, _t = await pick_database()
    activate(url)
    print(f">>> USING: {url}")

    from sqlalchemy import select, func
    from app.db.session import AsyncSessionLocal
    from app.modules.base_data.models import PlateRegion
    from app.modules.vehicles.models import Vehicle

    async with AsyncSessionLocal() as db:
        regions = (await db.execute(select(PlateRegion))).scalars().all()
        by_code = {}
        for r in regions:
            toks = {norm_letter(t) for t in (r.letters or "").split()}
            by_code.setdefault(r.plate_code, []).append((toks, r.province, r.city))

        candidates = (await db.execute(
            select(Vehicle).where(Vehicle.plate_province.is_(None)))).scalars().all()
        fixed = missing = 0
        for v in candidates:
            if not v.plate_letter or not v.plate_province_code:
                missing += 1
                continue
            ln = norm_letter(str(v.plate_letter).translate(_DIG))
            for toks, prov, city in by_code.get(v.plate_province_code, []):
                if ln in toks:
                    v.plate_province, v.plate_city = prov, city
                    fixed += 1
                    break
            else:
                missing += 1
        await db.commit()
        remaining = await db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.plate_province.is_(None)))
        print(f">>> backfill: fixed={fixed} | no-letter/code={missing} | still NULL={remaining}")


if __name__ == "__main__":
    asyncio.run(main())