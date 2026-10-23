"""ورود انبوه جایگاه‌های CAD از JSON — بدون نیاز به HTTP/توکن.

کاربرد (داخل کانتینر backend، پس از git pull که فایل JSON را داخل تصویر می‌آورد):
    python -m scripts.import_cad_spots [مسیر-JSON]

پیش‌فرض: docs/cad/parking_spots_import.json (خروجی واقعی DXF کارفرما:
۸۴ جای بلوک A طبقه ‎-۲‎ + ۳۰ جای سطحی + مرز سایت + ۳ فوت‌پرینت برج)
منطق همان POST /cad-parking/import است (upsert بر اساس parking_code).
"""
import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_JSON = Path(__file__).resolve().parents[1] / "docs" / "cad" / "parking_spots_import.json"

VALID_STATUS = ("free", "occupied", "reserved", "disabled", "maintenance", "context")


async def main(path: Path) -> None:
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.modules.parking.cad_models import CadParkingSpot

    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw["parking_spots"] if isinstance(raw, dict) else raw
    items = [s for s in items if isinstance(s, dict) and (s.get("parking_id") or s.get("parking_code"))]
    print(f"json: {path} — {len(items)} item(s)")

    created = updated = skipped = 0
    async with AsyncSessionLocal() as db:
        codes = [str(s.get("parking_id") or s.get("parking_code")).strip() for s in items]
        existing = {}
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

    print(f"created={created} updated={updated} skipped={skipped} — DONE")
    await __import__("app.db.session", fromlist=["engine"]).engine.dispose()


if __name__ == "__main__":
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_JSON
    if not p.exists():
        print(f"json not found: {p}")
        sys.exit(1)
    asyncio.run(main(p))
