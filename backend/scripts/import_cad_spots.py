"""ورود انبوه جایگاه‌های CAD از JSON — بدون نیاز به HTTP/توکن.

کاربرد (داخل کانتینر backend، پس از git pull که فایل JSON را داخل تصویر می‌آورد):
    python -m scripts.import_cad_spots [مسیر-JSON]

پیش‌فرض: docs/cad/parking_spots_import.json (خروجی واقعی DXF کارفرما:
۸۴ جای بلوک A طبقه ‎-۲‎ + ۳۰ جای سطحی + مرز سایت + ۳ فوت‌پرینت برج)
منطق همان POST /cad-parking/import است (upsert بر اساس parking_code).

نکته: bootstrap_prod همین منطق را برای «seed اولیه» صدا می‌زند (فقط وقتی
جدول cad_parking_spots خالی باشد) — پس با اولین بوت، نقشه CAD پر است.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BACKEND_DIR = Path(__file__).resolve().parents[1]

VALID_STATUS = ("free", "occupied", "reserved", "disabled", "maintenance", "context")


def find_default_json() -> Path | None:
    """مسیر پیش‌فرض JSON: داخل کانتینر /app/docs/cad/... یا در نسخهٔ سورس، ریشهٔ repo."""
    for candidate in (BACKEND_DIR / "docs" / "cad" / "parking_spots_import.json",
                      BACKEND_DIR.parent / "docs" / "cad" / "parking_spots_import.json"):
        if candidate.exists():
            return candidate
    return None


async def import_from_json(db, path: Path, purge: bool = False) -> tuple[int, int, int]:
    """Upsert جایگاه‌ها از فایل JSON روی session داده‌شده. خروجی: (created, updated, skipped).

    purge=True: ابتدا «همهٔ» جایگاه‌های موجود حذف می‌شوند — برای جایگزینی کامل نقشه
    (مثلاً مهاجرت از نقشهٔ قدیمی TA_P2 به نقشهٔ واقعی planYARD). وضعیت‌های دستی اپراتور
    هم پاک می‌شوند؛ پس فقط وقتی استفاده شود که جایگزینی کامل مدنظر است.
    """
    from sqlalchemy import delete, select

    from app.modules.parking.cad_models import CadParkingSpot

    if purge:
        n = (await db.execute(delete(CadParkingSpot))).rowcount
        await db.commit()
        print(f"[purge] {n} existing cad spots deleted")

    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw["parking_spots"] if isinstance(raw, dict) else raw
    items = [s for s in items if isinstance(s, dict) and (s.get("parking_id") or s.get("parking_code"))]

    created = updated = skipped = 0
    codes = [str(s.get("parking_id") or s.get("parking_code")).strip() for s in items]
    existing: dict[str, CadParkingSpot] = {}
    rows = (await db.execute(
        select(CadParkingSpot).where(CadParkingSpot.parking_code.in_(codes))
    )).scalars().all()
    for r in rows:
        existing[r.parking_code] = r

    for s in items:
        code = str(s.get("parking_id") or s.get("parking_code")).strip()
        poly = s.get("polygon") or []
        center = s.get("center") or {}
        cx, cy = center.get("x"), center.get("y")
        if (cx is None or cy is None) and len(poly) >= 3:
            try:
                cx = sum(p["x"] for p in poly) / len(poly)
                cy = sum(p["y"] for p in poly) / len(poly)
            except Exception:
                cx = cy = None
        values = {
            "display_name": s.get("display_name") or f"پارکینگ {code}",
            "source_drawing": s.get("source_drawing"),
            "source_layer": s.get("source_layer"),
            "source_entity_handle": s.get("source_entity_handle"),
            "polygon_json": poly,
            "center_x": cx, "center_y": cy,
            "area": s.get("area_dxf_unit2") or s.get("area"),
            "rotation": s.get("rotation_degree") or 0,
            "parking_type": s.get("parking_type"),
            "confidence": s.get("confidence"),
            "notes": str(s.get("notes") or "")[:250],
        }
        # status فقط وقتی در JSON معتبر است پاس داده می‌شود — پس re-import
        # هرگز وضعیتِ (اشغال/آزاد/…) که اپراتور دستی عوض کرده را بازنویسی نمی‌کند.
        if s.get("status") in VALID_STATUS:
            values["status"] = s["status"]

        row = existing.get(code)
        if row is not None:
            for k, v in values.items():
                if v is not None:
                    setattr(row, k, v)
            updated += 1
        else:
            db.add(CadParkingSpot(parking_code=code, **values))
            created += 1
    await db.commit()
    return created, updated, skipped


async def main(path: Path, purge: bool = False) -> None:
    from app.db.session import AsyncSessionLocal, engine

    async with AsyncSessionLocal() as db:
        created, updated, skipped = await import_from_json(db, path, purge=purge)
        print(f"created={created} updated={updated} skipped={skipped} — DONE")
    await engine.dispose()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="ورود انبوه جایگاه‌های CAD از JSON")
    ap.add_argument("path", nargs="?", default=None, help="مسیر JSON (پیش‌فرض: docs/cad/parking_spots_import.json)")
    ap.add_argument("--purge", action="store_true",
                    help="ابتدا همهٔ جایگاه‌های موجود حذف شوند (جایگزینی کامل نقشه)")
    args = ap.parse_args()
    p = Path(args.path) if args.path else (find_default_json() or Path("docs/cad/parking_spots_import.json"))
    if not p.exists():
        print(f"json not found: {p}")
        sys.exit(1)
    asyncio.run(main(p, purge=args.purge))
