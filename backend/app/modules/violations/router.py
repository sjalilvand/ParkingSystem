from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.audit import write_audit
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_any_permission
from app.db.session import get_db
from app.modules.finance.models import Charge
from app.modules.identity.models import User
from app.modules.vehicles.models import Vehicle
from app.modules.violations.models import Violation, ViolationAppeal, ViolationType
from app.modules.violations.service import (
    appeal_result_valid,
    can_transition,
    voidable_charge_status,
)
from app.shared.plate import normalize_plate

router = APIRouter(prefix="/violations", tags=["Violations"])


def _perm(*codes: str):
    """F9: کنترل مجوز لایه API — با ENFORCE_VIOLATIONS_PERMISSIONS قابل تعلیق."""
    if not getattr(settings, "ENFORCE_VIOLATIONS_PERMISSIONS", True):
        return get_current_user
    return require_any_permission(*codes)


class ViolationTypeCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    title: str
    default_penalty_amount: int = Field(default=0, ge=0)
    requires_image: bool = False


class ViolationCreate(BaseModel):
    plate_raw: str = Field(min_length=2, max_length=64)
    violation_type_code: str
    description: str | None = None
    parking_space_id: str | None = None
    client_ref: str | None = None
    image_file_id: str | None = None


async def _void_unpaid_charge(db: AsyncSession, violation_id: str, reason: str, user_id: str | None) -> bool:
    """F19 (§۱۴/§۱۵): ابطال مستند شارژِ تسویه‌نشدهٔ تخلف. شارژ پرداخت‌شده ابطال نمیشود."""
    charge = (await db.execute(
        select(Charge).where(Charge.violation_id == violation_id)
    )).scalars().first()
    if charge is None:
        return False
    if not voidable_charge_status(charge.status):
        return False
    charge.status = "VOIDED"
    if user_id:
        await write_audit(db, user_id=user_id, action="CHARGE_VOID", module="finance",
                          entity_type="charge", entity_id=charge.id, reason=reason)
    return True


@router.get("/types")
async def list_types(db: AsyncSession = Depends(get_db), user: User = Depends(_perm("violations.view"))):
    result = await db.execute(select(ViolationType).where(ViolationType.is_active.is_(True)))
    return [{"id": t.id, "code": t.code, "title": t.title,
             "default_penalty_amount": t.default_penalty_amount,
             "requires_image": t.requires_image} for t in result.scalars().all()]


@router.post("/types")
async def create_type(body: ViolationTypeCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("violations.review"))):
    obj = ViolationType(code=body.code, title=body.title,
                        default_penalty_amount=body.default_penalty_amount,
                        requires_image=body.requires_image)
    db.add(obj)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("کد نوع تخلف تکراری است")
    await db.refresh(obj)
    return {"id": obj.id, "code": obj.code}


@router.get("")
async def list_violations(status: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("violations.view"))):
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
async def create_violation(body: ViolationCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("violations.create"))):
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

    # F21 (§و): تخلف نیازمند تصویر، بدون تصویر ثبت نمیشود
    if vtype.requires_image and not body.image_file_id:
        raise HTTPException(status_code=422, detail="REQUIRED_IMAGE_MISSING")

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
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (await db.execute(
            select(Violation).where(Violation.client_ref == body.client_ref)
        )).scalar_one_or_none() if body.client_ref else None
        if existing is not None:
            return {"id": existing.id, "status": existing.status,
                    "penalty_amount": existing.penalty_amount,
                    "image_file_id": existing.image_file_id, "duplicate": True,
                    "warnings": ["CONCURRENT_CONFLICT"]}
        raise
    await db.refresh(obj)
    return {"id": obj.id, "status": obj.status, "penalty_amount": obj.penalty_amount,
            "image_file_id": obj.image_file_id, "duplicate": False}


@router.post("/{violation_id}/confirm")
async def confirm_violation(violation_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("violations.review"))):
    obj = await db.get(Violation, violation_id)
    if not obj:
        raise NotFoundError("تخلف یافت نشد")
    if obj.status == "CONFIRMED":
        return {"success": True, "status": obj.status, "duplicate": True}
    if not can_transition(obj.status, "CONFIRMED"):
        raise ConflictError(f"انتقال وضعیت {obj.status} -> CONFIRMED مجاز نیست")

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
    return {"success": True, "status": obj.status, "duplicate": False}


@router.post("/{violation_id}/cancel")
async def cancel_violation(violation_id: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("violations.review"))):
    obj = await db.get(Violation, violation_id)
    if not obj:
        raise NotFoundError("تخلف یافت نشد")
    if obj.status == "CANCELLED":
        return {"success": True, "status": obj.status, "duplicate": True}
    if not can_transition(obj.status, "CANCELLED"):
        raise ConflictError(f"انتقال وضعیت {obj.status} -> CANCELLED مجاز نیست")

    obj.status = "CANCELLED"
    obj.reviewed_by = user.id if user else None
    obj.reviewed_at = datetime.now(timezone.utc)

    # F19 (§۱۴/§۱۵): ابطال مستند بدهی قطعیِ تخلفِ لغوشده
    voided = await _void_unpaid_charge(db, obj.id, "VIOLATION_CANCELLED", user.id if user else None)
    charged_paid = False
    if not voided:
        charge = (await db.execute(
            select(Charge).where(Charge.violation_id == obj.id)
        )).scalars().first()
        charged_paid = (charge is not None and charge.status == "PAID")

    if user:
        await write_audit(db, user_id=user.id, action="VIOLATION_CANCEL", module="violations",
                          entity_type="violation", entity_id=obj.id, reason=body.get("reason"))
    await db.commit()
    return {"success": True, "status": obj.status, "charge_voided": voided,
            "paid_charge_needs_refund": charged_paid}


@router.post("/{violation_id}/appeals")
async def create_appeal(violation_id: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj_v = await db.get(Violation, violation_id)
    if not obj_v:
        raise NotFoundError("تخلف یافت نشد")
    # F20: اعتراض فقط برای تخلف ثبت‌شده یا تأییدشده معنا دارد
    if obj_v.status not in ("REGISTERED", "CONFIRMED"):
        raise ConflictError(f"برای تخلف در وضعیت {obj_v.status} امکان اعتراض نیست")
    obj = ViolationAppeal(violation_id=violation_id, description=body.get("description"),
                          submitted_by=user.id if user else None)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "status": obj.status}


@router.post("/appeals/{appeal_id}/review")
async def review_appeal(appeal_id: str, body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("violations.review"))):
    obj = await db.get(ViolationAppeal, appeal_id)
    if not obj:
        raise NotFoundError("اعتراض یافت نشد")
    if obj.status != "SUBMITTED":
        raise ConflictError("این اعتراض قبلاً تعیین تکلیف شده است")
    result = (body.get("result") or "").upper()
    # F20: نتیجه فقط ACCEPTED یا REJECTED
    if not appeal_result_valid(result):
        raise HTTPException(status_code=422, detail="INVALID_APPEAL_RESULT")

    obj.status = result
    obj.review_result = body.get("note")
    obj.reviewed_by = user.id if user else None
    obj.reviewed_at = datetime.now(timezone.utc)

    charge_voided = False
    if result == "ACCEPTED":
        v = await db.get(Violation, obj.violation_id)
        if v and v.status in ("REGISTERED", "CONFIRMED"):
            v.status = "CANCELLED"
            v.reviewed_by = user.id if user else None
            v.reviewed_at = datetime.now(timezone.utc)
            charge_voided = await _void_unpaid_charge(db, v.id, "APPEAL_ACCEPTED", user.id if user else None)

    if user:
        await write_audit(db, user_id=user.id, action="VIOLATION_APPEAL_REVIEW", module="violations",
                          entity_type="violation_appeal", entity_id=obj.id,
                          new_values={"result": result, "charge_voided": charge_voided})
    await db.commit()
    return {"success": True, "status": obj.status, "charge_voided": charge_voided}
