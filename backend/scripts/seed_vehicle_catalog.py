"""Seed کاتالوگ خودرو از bama_full_catalog.csv — idempotent (local + container)."""
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.main  # noqa: F401

from sqlalchemy import func, select

from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.modules.base_data.models import VehicleBrand, VehicleModel, VehicleSubModel

CSV_CANDIDATES = [
    Path(__file__).resolve().parents[1] / "app" / "shared" / "data" / "bama_full_catalog.csv",
    Path(__file__).resolve().parents[2] / "bama_full_catalog.csv",
    Path("/app/app/shared/data/bama_full_catalog.csv"),
]


def find_csv():
    for p in CSV_CANDIDATES:
        if p.exists():
            return p
    return None


def parse_line(line):
    line = line.replace("\ufeff", "").strip()
    if not line:
        return None
    sep = "|" if "|" in line else ("," if "," in line else "\t")
    parts = [p.strip().strip('"') for p in line.split(sep)]
    parts = [p for p in parts if p]
    parts = [p for p in parts if not p.startswith("http")]
    while parts and parts[0].isdigit():
        parts.pop(0)
    if len(parts) < 3:
        return None
    brand, model, sub = parts[0], parts[1], parts[2]
    if brand == "برند":
        return None
    return brand, model, sub


async def main():
    csv_path = find_csv()
    if not csv_path:
        print("[X] CSV not found - place bama_full_catalog.csv in app/shared/data/")
        sys.exit(1)
    print(f"[catalog] CSV: {csv_path}")

    async with engine.begin() as conn:
        await conn.run_sync(lambda sc: VehicleModel.__table__.create(sc, checkfirst=True))
        await conn.run_sync(lambda sc: VehicleSubModel.__table__.create(sc, checkfirst=True))
    print("[catalog] tables OK")

    rows, seen = [], set()
    for line in csv_path.read_text(encoding="utf-8-sig").splitlines():
        r = parse_line(line)
        if r and r not in seen:
            seen.add(r)
            rows.append(r)
    print(f"[catalog] parsed rows: {len(rows)}")
    if len(rows) < 100:
        print("[X] too few rows - CSV format issue")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        brand_cache, model_cache = {}, {}
        nb = nm = ns = 0
        for brand, model, sub in rows:
            b = brand_cache.get(brand)
            if b is None:
                b = (await db.execute(select(VehicleBrand).where(
                    VehicleBrand.name_fa == brand))).scalar_one_or_none()
                if b is None:
                    b = VehicleBrand(name_fa=brand, country="IR")
                    db.add(b)
                    await db.flush()
                    nb += 1
                brand_cache[brand] = b
            mkey = (b.id, model)
            mo = model_cache.get(mkey)
            if mo is None:
                mo = (await db.execute(select(VehicleModel).where(
                    VehicleModel.brand_id == b.id, VehicleModel.name == model))).scalar_one_or_none()
                if mo is None:
                    mo = VehicleModel(brand_id=b.id, name=model)
                    db.add(mo)
                    await db.flush()
                    nm += 1
                model_cache[mkey] = mo
            s = (await db.execute(select(VehicleSubModel).where(
                VehicleSubModel.model_id == mo.id, VehicleSubModel.name == sub))).scalar_one_or_none()
            if s is None:
                db.add(VehicleSubModel(model_id=mo.id, name=sub))
                ns += 1
        await db.commit()

    async with AsyncSessionLocal() as db:
        tb = await db.scalar(select(func.count()).select_from(VehicleBrand))
        tm = await db.scalar(select(func.count()).select_from(VehicleModel))
        ts = await db.scalar(select(func.count()).select_from(VehicleSubModel))
    print(f"[catalog] DONE: brands+{nb} models+{nm} submodels+{ns}")
    print(f"[catalog] totals: brands={tb} models={tm} submodels={ts}")


if __name__ == "__main__":
    asyncio.run(main())