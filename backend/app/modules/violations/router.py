from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.audit import write_audit
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.finance.models import Charge
from app.modules.identity.models import User
from app.modules.vehicles.models import Vehicle
from app.modules.violations.models import Violation, ViolationAppeal, ViolationType
from app.shared.plate import normalize_plate

router = APIRouter(prefix="/violations", tags=["Violations"])


class ViolationCreate(BaseModel):
    plate_raw: str
    violation_type_code: str
    description: str | None = None
    parking_space_id: str | None = None
    client_ref: str | None = None
    image_file_id: str | None = None


@router.get("/types")
async def list_types(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(ViolationType).where(ViolationType.is_active.is_(True)))
    return [{"id": t.id, "code": t.code, "title": t.title,
             "default_penalty_amount": t.default_penalty_amount} for t in result.scalars().all()]


@router.post("/types")
async def create_type(body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = ViolationType(code=body["code"], title=body["title"],
                        default_penalty_amount=int(body.get("default_penalty_amount", 0)))
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "code": obj.code}


@router.get("")
async def list_violations(status: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Violation)
    if status:
        query = query.where(Violation.status == status)
    result = await db.execute(query.order_by(Violation.created_at.desc()).limit(200))
    return [{
        "id": v.id, "plate_normalized": v.plate_normalized, "violation_type_id": v.violation_type_id,
        "occurred_at": v.occurred_at.isoformat(), "penalty_amount": v.penalty_amount, "status": v.status,
        "client_ref": v.client_ref, "image_file_id": v.image_file_id,
    } for v in result.scalars().all()]


@router.post("")
async def create_violation(body: ViolationCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if body.client_ref:
        existing = (await db.execute(
            select(Violation).where(Violation.client_ref == body.client_ref)
        )).scalar_one_or_none()
        if existing:
            return {"id": existing.id, "status": existing.status,
                    "penalty_amount": existing.penalty_amount,
                    "image_file_id": existing.image_file_id, "duplicate": True}

    vtype = (await db.execute(
        select(ViolationType).where(ViolationType.code == body.violation_type_code)
    )).scalar_one_or_none()
    if not vtype:
        raise NotFoundError("نوع تخلف یافت نشد")

    plate_norm = normalize_plate(body.plate_raw)
    vehicle = None
    if plate_norm:
        vehicle = (await db.execute(
            select(Vehicle).where(Vehicle.plate_normalized == plate_norm)
        )).scalars().first()

    obj = Violation(
        vehicle_id=vehicle.id if vehicle else None,
        plate_normalized=plate_norm,
        violation_type_id=vtype.id, parking_space_id=body.parking_space_id,
        occurred_at=datetime.now(timezone.utc), description=body.description,
        penalty_amount=vtype.default_penalty_amount, registered_by=user.id if user else None,
        client_ref=body.client_ref, image_file_id=body.image_file_id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "status": obj.status, "penalty_amount": obj.penalty_amount,
            "image_file_id": obj.image_file_id, "duplicate": False}


@router.post("/{violation_id}/confirm")
async def confirm_violation(violation_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Violation, violation_id)
    if not obj:
        raise NotFoundError("تخلف یافت نشد")
    obj.status = "CONFIRMED"
    obj.reviewed_by = user.id if user else None
    obj.reviewed_at = datetime.now(timezone.utc)

    existing_charge = (await db.execute(
        select(Charge).where(Charge.violation_id == obj.id)
    )).scalars().first()
    if existing_charge is None and obj.penalty_amount > 0:
        db.add(Charge(violation_id=obj.id, charge_type="VIOLATION",
                      amount=obj.penalty_amount, description=f"VIOLATION penalty {obj.id[:8]}"))

    if user:
        await write_audit(db, user_id=user.id, action="VIOLATION_CONFIRM", module="violations",
                          entity_type="violation", entity_id=obj.id)
    await db.commit()
    return {"success": True, "status": obj.status}


@router.post("/{violation_id}/cancel")
async def cancel_violation(violation_id: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Violation, violation_id)
    if not obj:
        raise NotFoundError("تخلف یافت نشد")
    obj.status = "CANCELLED"
    obj.reviewed_by = user.id if user else None
    obj.reviewed_at = datetime.now(timezone.utc)
    if user:
        await write_audit(db, user_id=user.id, action="VIOLATION_CANCEL", module="violations",
                          entity_type="violation", entity_id=obj.id, reason=body.get("reason"))
    await db.commit()
    return {"success": True}


@router.post("/{violation_id}/appeals")
async def create_appeal(violation_id: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = ViolationAppeal(violation_id=violation_id, description=body.get("description"),
                          submitted_by=user.id if user else None)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "status": obj.status}


@router.post("/appeals/{appeal_id}/review")
async def review_appeal(appeal_id: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(ViolationAppeal, appeal_id)
    if not obj:
        raise NotFoundError("اعتراض یافت نشد")
    obj.status = body.get("result", "REJECTED").upper()
    obj.review_result = body.get("note")
    obj.reviewed_by = user.id if user else None
    obj.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"success": True, "status": obj.status}