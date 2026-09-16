import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import AppException, NotFoundError
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.vehicles.models import AccessPermit, Vehicle
from app.modules.vehicles.schemas import PermitCheckRequest, PermitCreate, PermitOut
from app.modules.vehicles.service import VehicleService, permit_time_valid
from app.shared.plate import normalize_plate

router = APIRouter(prefix="/permits", tags=["Permits"])


@router.get("")
async def list_permits(status: str | None = None, page: int = 1, page_size: int = 20, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(AccessPermit)
    if status:
        query = query.where(AccessPermit.status == status)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(query.order_by(AccessPermit.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    items = [PermitOut.model_validate(p).model_dump() for p in result.scalars().all()]
    total_items = total or 0
    return {"items": items, "page": page, "page_size": page_size, "total_items": total_items, "total_pages": (total_items + page_size - 1) // page_size}


@router.post("")
async def create_permit(body: PermitCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    data = body.model_dump()
    plate_raw = data.pop("plate_raw", None)
    allowed_days = data.pop("allowed_days", None)

    plate_norm = None
    if plate_raw:
        plate_norm = normalize_plate(plate_raw)
    elif data.get("vehicle_id"):
        vehicle = await db.get(Vehicle, data["vehicle_id"])
        plate_norm = vehicle.plate_normalized if vehicle else None
    if not plate_norm:
        raise AppException("پلاک یا خودرو باید مشخص شود", details={"code": "PLATE_REQUIRED"})

    obj = AccessPermit(
        plate_normalized=plate_norm,
        allowed_days=json.dumps(allowed_days) if allowed_days is not None else None,
        issued_by=user.id if user else None,
        **data,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return PermitOut.model_validate(obj).model_dump()


@router.get("/{permit_id}")
async def get_permit(permit_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(AccessPermit, permit_id)
    if not obj:
        raise NotFoundError("مجوز یافت نشد")
    return PermitOut.model_validate(obj).model_dump()


@router.post("/{permit_id}/activate")
async def activate_permit(permit_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(AccessPermit, permit_id)
    if not obj:
        raise NotFoundError("مجوز یافت نشد")
    obj.status = "ACTIVE"
    await db.commit()
    return {"success": True}


@router.post("/{permit_id}/revoke")
async def revoke_permit(permit_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(AccessPermit, permit_id)
    if not obj:
        raise NotFoundError("مجوز یافت نشد")
    obj.status = "REVOKED"
    await db.commit()
    return {"success": True}


@router.post("/check")
async def check_permit(body: PermitCheckRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    normalized = normalize_plate(body.plate_raw)
    now = datetime.now(timezone.utc)
    if not normalized:
        return {"plate_normalized": None, "vehicle_found": False, "permit_found": False,
                "restricted": False, "reason": "PLATE_NOT_READABLE"}

    vehicle = await VehicleService.get_by_plate(db, body.plate_raw)
    permit, reason = await VehicleService.find_active_permit(db, normalized, body.gate_id, now)
    restriction = await VehicleService.has_active_restriction(db, normalized, now)

    final_reason = "PLATE_RESTRICTED" if restriction else (reason if permit is None else "OK")
    return {
        "plate_normalized": normalized,
        "vehicle_found": vehicle is not None,
        "permit_found": permit is not None,
        "permit_id": permit.id if permit else None,
        "time_valid": permit_time_valid(permit, now)[0] if permit else False,
        "restricted": restriction is not None,
        "reason": final_reason,
    }