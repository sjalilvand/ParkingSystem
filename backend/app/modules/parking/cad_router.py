from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.parking.cad_models import CadParkingSpot

router = APIRouter(prefix="/cad-parking", tags=["CadParking"])

VALID_STATUS = ("free", "occupied", "reserved", "disabled", "maintenance")


class ImportRequest(BaseModel):
    parking_spots: list[Any]


@router.post("/import")
async def import_spots(body: ImportRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """درج انبوه جایگاه‌های DXF — بهینه، تحمل خطای تکی، فیلتر آیتم نامعتبر."""
    created, updated, skipped = 0, 0, 0
    errors = []

    dicts = [(i, s) for i, s in enumerate(body.parking_spots) if isinstance(s, dict)]
    skipped += len(body.parking_spots) - len(dicts)

    codes = []
    for _i, s in dicts:
        c = str(s.get("parking_id") or s.get("parking_code") or "").strip()
        if c:
            codes.append(c)

    existing_map: dict[str, CadParkingSpot] = {}
    if codes:
        rows = (await db.execute(
            select(CadParkingSpot).where(CadParkingSpot.parking_code.in_(codes))
        )).scalars().all()
        for r in rows:
            existing_map[r.parking_code] = r

    for idx, spot in dicts:
        try:
            code = str(spot.get("parking_id") or spot.get("parking_code") or "").strip()
            if not code:
                skipped += 1
                continue

            poly = spot.get("polygon") or []
            center = spot.get("center") or {}
            cx = center.get("x")
            cy = center.get("y")
            if (cx is None or cy is None) and len(poly) >= 3:
                try:
                    cx = sum(p["x"] for p in poly) / len(poly)
                    cy = sum(p["y"] for p in poly) / len(poly)
                except Exception:
                    cx = cy = None

            values = {
                "display_name": spot.get("display_name") or f"پارکینگ {code}",
                "source_drawing": spot.get("source_drawing"),
                "source_layer": spot.get("source_layer"),
                "source_entity_handle": spot.get("source_entity_handle") or spot.get("label_entity_handle"),
                "polygon_json": poly,
                "center_x": cx, "center_y": cy,
                "area": spot.get("area_dxf_unit2") or spot.get("area"),
                "rotation": spot.get("rotation_degree") or 0,
                "parking_type": spot.get("parking_type"),
                "confidence": spot.get("confidence"),
                "notes": str(spot.get("notes") or "")[:250],
            }

            existing = existing_map.get(code)
            if existing:
                for k, v in values.items():
                    if v is not None:
                        setattr(existing, k, v)
                updated += 1
            else:
                db.add(CadParkingSpot(parking_code=code, **values))
                created += 1
        except Exception as exc:
            skipped += 1
            errors.append({"index": idx, "error": str(exc)[:200]})

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        return {"success": False, "created": 0, "updated": 0,
                "skipped": len(body.parking_spots),
                "errors": [{"index": -1, "error": str(exc)[:300]}]}

    return {"success": True, "created": created, "updated": updated,
            "skipped": skipped, "errors": errors[:20]}


@router.get("")
async def list_spots(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(CadParkingSpot).order_by(CadParkingSpot.parking_code)
    )).scalars().all()
    return [{
        "id": r.id, "parking_code": r.parking_code, "display_name": r.display_name,
        "polygon_json": r.polygon_json, "center_x": r.center_x, "center_y": r.center_y,
        "area": r.area, "status": r.status, "parking_type": r.parking_type,
        "confidence": r.confidence, "source_layer": r.source_layer,
        "source_entity_handle": r.source_entity_handle, "is_active": r.is_active,
        "notes": r.notes,
    } for r in rows]


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    # نکته: GROUP BY برای PostgreSQL اجباری است (علت 500 قبلی)
    rows = (await db.execute(
        select(CadParkingSpot.status, func.count())
        .group_by(CadParkingSpot.status)
    )).all()
    by_status = {s: c for s, c in rows}
    return {"total": sum(by_status.values()), "by_status": by_status}


@router.delete("/all")
async def delete_all(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(delete(CadParkingSpot))
    await db.commit()
    return {"success": True, "deleted": result.rowcount}


@router.patch("/{spot_id}")
async def update_spot(spot_id: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(CadParkingSpot, spot_id)
    if not obj:
        raise NotFoundError("جایگاه یافت نشد")
    if "status" in body:
        if body["status"] not in VALID_STATUS:
            raise NotFoundError("وضعیت نامعتبر")
        obj.status = body["status"]
    if "parking_code" in body and body["parking_code"]:
        obj.parking_code = body["parking_code"]
    if "display_name" in body:
        obj.display_name = body["display_name"]
    if "notes" in body:
        obj.notes = body["notes"]
    if "is_active" in body:
        obj.is_active = bool(body["is_active"])
    await db.commit()
    return {"success": True}


@router.delete("/{spot_id}")
async def delete_spot(spot_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(CadParkingSpot, spot_id)
    if not obj:
        raise NotFoundError("جایگاه یافت نشد")
    await db.delete(obj)
    await db.commit()
    return {"success": True}