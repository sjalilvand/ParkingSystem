import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import case, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.audit import write_audit
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_any_permission
from app.db.session import get_db
from app.modules.access_control.models import ParkingSession
from app.modules.finance.models import Charge, FinancialAdjustment, Payment, PaymentAllocation, Tariff
from app.modules.finance.service import (
    allocate_payment_amounts,
    calculate_amounts,
    charge_outstanding,
    initial_tariff_status,
)
from app.modules.identity.models import User
from app.modules.violations.models import Violation
from app.shared.plate import normalize_plate

router = APIRouter(tags=["Finance"])


def _perm(*codes: str):
    """F9: کنترل مجوز در لایه API (بخش ۸ سند) — با ENFORCE_FINANCE_PERMISSIONS قابل تعلیق.
    ADMIN همیشه مجاز است؛ کاربر فعلی مستقر فقط admin است، پس رفتار فعلی حفظ می‌شود."""
    if not getattr(settings, "ENFORCE_FINANCE_PERMISSIONS", True):
        return get_current_user
    return require_any_permission(*codes)


class TariffCreate(BaseModel):
    title: str
    free_minutes: int = Field(default=0, ge=0)
    hourly_amount: int = Field(default=0, ge=0)
    daily_max_amount: int | None = Field(default=None, gt=0)
    night_amount: int | None = Field(default=None, gt=0)
    vehicle_category: str | None = None
    permit_category: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    priority: int = 0


class PaymentCreate(BaseModel):
    plate_raw: str | None = None
    vehicle_id: str | None = None
    amount: int = Field(gt=0)
    payment_method: str = "CASH"
    reference_number: str | None = None
    notes: str | None = None


class TariffPreviewRequest(BaseModel):
    """پیش‌نمایش محاسبه قبل از فعال‌سازی (§۲۳). تعرفه را ذخیره نمی‌کند."""
    duration_seconds: int = Field(ge=0)
    tariff: TariffCreate | None = None
    tariff_id: str | None = None


@router.get("/tariffs")
async def list_tariffs(db: AsyncSession = Depends(get_db), user: User = Depends(_perm("finance.view"))):
    result = await db.execute(select(Tariff).order_by(Tariff.priority.desc()))
    return [{
        "id": t.id, "title": t.title, "free_minutes": t.free_minutes,
        "hourly_amount": t.hourly_amount, "daily_max_amount": t.daily_max_amount,
        "night_amount": t.night_amount, "valid_from": t.valid_from.isoformat() if t.valid_from else None,
        "valid_until": t.valid_until.isoformat() if t.valid_until else None,
        "priority": t.priority, "status": t.status,
        "approved_by": t.approved_by, "approved_at": t.approved_at.isoformat() if t.approved_at else None,
    } for t in result.scalars().all()]


@router.post("/tariffs")
async def create_tariff(body: TariffCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("finance.manage"))):
    # F8: با سیاست تصویب، تعرفه جدید DRAFT است و تا تأیید در محاسبه مالی دخالت نمی‌کند.
    data = body.model_dump()
    data["status"] = initial_tariff_status(bool(getattr(settings, "TARIFF_REQUIRE_APPROVAL", True)))
    obj = Tariff(**data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    if user:
        await write_audit(db, user_id=user.id, action="TARIFF_CREATE", module="finance",
                          entity_type="tariff", entity_id=obj.id,
                          new_values={"title": obj.title, "status": obj.status})
        await db.commit()
    return {"id": obj.id, "title": obj.title, "status": obj.status}


@router.post("/tariffs/preview")
async def preview_tariff(body: TariffPreviewRequest, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("finance.view"))):
    """§۲۳: پیش‌نمایش محاسبه بدون ذخیره‌سازی — قبل از فعال‌سازی."""
    tariff = None
    source = "ACTIVE_TARIFF"
    if body.tariff_id:
        tariff = await db.get(Tariff, body.tariff_id)
        if not tariff:
            raise NotFoundError("تعرفه یافت نشد")
        source = f"TARIFF:{body.tariff_id}(status={tariff.status})"
    elif body.tariff is not None:
        tariff = Tariff(**body.tariff.model_dump())
        source = "AD_HOC"
    amounts = calculate_amounts(tariff, body.duration_seconds)
    return {"source": source, "duration_seconds": body.duration_seconds, **amounts,
            "note": "قواعد گردکردن/سقف/شب نیازمند تصویب (docs/pending-decisions.md D2-D4)"}


@router.post("/tariffs/{tariff_id}/activate")
async def activate_tariff(tariff_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("finance.manage"))):
    obj = await db.get(Tariff, tariff_id)
    if not obj:
        raise NotFoundError("تعرفه یافت نشد")
    # F8: فعال‌سازی انحصاری — فقط یک تعرفه ACTIVE در هر لحظه (تراکنش واحد)
    others = (await db.execute(select(Tariff).where(Tariff.status == "ACTIVE"))).scalars().all()
    for t in others:
        t.status = "INACTIVE"
    obj.status = "ACTIVE"
    obj.approved_by = user.id if user else None
    obj.approved_at = datetime.now(timezone.utc)
    if user:
        await write_audit(db, user_id=user.id, action="TARIFF_ACTIVATE", module="finance",
                          entity_type="tariff", entity_id=obj.id,
                          new_values={"title": obj.title, "deactivated": [t.id for t in others]})
    await db.commit()
    return {"success": True, "activated": obj.id, "deactivated_count": len(others)}


@router.get("/charges")
async def list_charges(status: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("finance.view"))):
    query = select(Charge)
    if status:
        query = query.where(Charge.status == status)
    result = await db.execute(query.order_by(Charge.created_at.desc()).limit(200))
    return [{
        "id": c.id, "parking_session_id": c.parking_session_id, "violation_id": c.violation_id,
        "charge_type": c.charge_type, "amount": c.amount, "paid_amount": c.paid_amount,
        "outstanding": charge_outstanding(c), "status": c.status, "description": c.description,
    } for c in result.scalars().all()]


@router.get("/debts")
async def list_debts(plate: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("finance.view"))):
    """بدهی‌های واقعی (مانده = amount - paid_amount — F16) با زمینه پلاک."""
    query = select(Charge).where(Charge.status == "UNPAID")

    plate_norm = None
    if plate:
        plate_norm = normalize_plate(plate)
        session_subq = select(ParkingSession.id).where(ParkingSession.plate_normalized == plate_norm)
        violation_subq = select(Violation.id).where(Violation.plate_normalized == plate_norm)
        query = query.where(or_(
            Charge.parking_session_id.in_(session_subq),
            Charge.violation_id.in_(violation_subq),
        ))

    charges = (await db.execute(query.order_by(Charge.created_at.asc()).limit(500))).scalars().all()

    session_ids = {c.parking_session_id for c in charges if c.parking_session_id}
    plate_map: dict[str, str | None] = {}
    if session_ids:
        sessions = (await db.execute(
            select(ParkingSession).where(ParkingSession.id.in_(session_ids))
        )).scalars().all()
        plate_map = {s.id: s.plate_normalized for s in sessions}

    items = []
    total = 0
    for c in charges:
        outstanding = charge_outstanding(c)
        if outstanding <= 0:
            continue  # کاملاً تسویه‌شده (پرداخت جزئی ثبت شده ولی وضعیت هنوز UNPAID)
        items.append({
            "charge_id": c.id, "charge_type": c.charge_type, "amount": c.amount,
            "paid_amount": c.paid_amount, "outstanding": outstanding,
            "plate": plate_map.get(c.parking_session_id or ""), "violation_id": c.violation_id,
            "description": c.description,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
        total += outstanding
    return {"items": items, "total_unpaid": total, "count": len(items)}


def _build_allocation_query(plate_norm: str | None):
    """بدهی‌های هدف پرداخت: در صورت وجود پلاک فقط همان پلاک؛ PARKING اول سپس بقیه."""
    query = select(Charge).where(Charge.status == "UNPAID")
    if plate_norm:
        session_subq = select(ParkingSession.id).where(ParkingSession.plate_normalized == plate_norm)
        violation_subq = select(Violation.id).where(Violation.plate_normalized == plate_norm)
        query = query.where(or_(
            Charge.parking_session_id.in_(session_subq),
            Charge.violation_id.in_(violation_subq),
        ))
        type_priority = case((Charge.charge_type == "PARKING", 0), else_=1)
        query = query.order_by(type_priority, Charge.created_at.asc())
    else:
        query = query.order_by(Charge.created_at.asc())
    return query


@router.post("/payments")
async def create_payment(body: PaymentCreate, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("finance.pay", "finance.manage"))):
    # Idempotency (§۱۴): reference تکراری => همان پاسخ قبلی
    if body.reference_number:
        existing = (await db.execute(
            select(Payment).where(Payment.reference_number == body.reference_number)
        )).scalar_one_or_none()
        if existing:
            return {"id": existing.id, "reference_number": existing.reference_number,
                    "amount": existing.amount, "duplicate": True}

    reference = body.reference_number or f"PAY-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"

    plate_norm = None
    vehicle_id = body.vehicle_id
    if body.plate_raw:
        plate_norm = normalize_plate(body.plate_raw)
        if not vehicle_id:
            from app.modules.vehicles.models import Vehicle
            v = (await db.execute(select(Vehicle).where(Vehicle.plate_normalized == plate_norm))).scalars().first()
            vehicle_id = v.id if v else None

    plate_norm2 = plate_norm
    vehicle_id2 = vehicle_id

    async def _do():
        payment = Payment(
            reference_number=reference, vehicle_id=vehicle_id2, plate_normalized=plate_norm2,
            amount=body.amount, payment_method=body.payment_method,
            paid_at=datetime.now(timezone.utc), operator_id=user.id if user else None,
            notes=body.notes,
        )
        db.add(payment)
        # F24: کل عملیات (flush→allocations→audit→commit) درون یک try — تداخل همزمان => duplicate
        try:
            await db.flush()
            unpaid = (await db.execute(_build_allocation_query(plate_norm2))).scalars().all()
            allocs, remaining = allocate_payment_amounts(unpaid, body.amount)
            allocations = []
            for charge, alloc in allocs:
                db.add(PaymentAllocation(payment_id=payment.id, charge_id=charge.id, amount=alloc))
                charge.paid_amount = int(charge.paid_amount or 0) + alloc
                if charge_outstanding(charge) <= 0:
                    charge.status = "PAID"
                allocations.append({"charge_id": charge.id, "amount": alloc, "charge_type": charge.charge_type})

            warnings = []
            if not plate_norm2 and not vehicle_id2:
                warnings.append("NO_PLATE_GLOBAL_ALLOCATION")

            if user:
                await write_audit(db, user_id=user.id, action="PAYMENT_CREATE", module="finance",
                                  entity_type="payment", entity_id=payment.id,
                                  new_values={"amount": body.amount, "reference": reference,
                                              "allocations": allocations, "remaining_credit": remaining})
            await db.commit()
            return payment, allocations, remaining, warnings
        except IntegrityError:
            await db.rollback()
            dup = (await db.execute(
                select(Payment).where(Payment.reference_number == reference)
            )).scalar_one_or_none()
            if dup is not None:
                return "DUP", dup, None, None
            raise

    result = await _do()
    if isinstance(result, tuple) and result and result[0] == "DUP":
        _, dup, _, _ = result
        return {"id": dup.id, "reference_number": dup.reference_number,
                "amount": dup.amount, "duplicate": True, "warnings": ["CONCURRENT_CONFLICT"]}

    payment, allocations, remaining, warnings = result
    await db.refresh(payment)
    return {"id": payment.id, "reference_number": payment.reference_number, "amount": payment.amount,
            "allocations": allocations, "remaining_credit": remaining, "duplicate": False,
            "warnings": warnings}

@router.get("/payments/{payment_id}")
async def get_payment(payment_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("finance.view"))):
    obj = await db.get(Payment, payment_id)
    if not obj:
        raise NotFoundError("پرداخت یافت نشد")
    allocs = (await db.execute(
        select(PaymentAllocation).where(PaymentAllocation.payment_id == payment_id)
    )).scalars().all()
    return {"id": obj.id, "reference_number": obj.reference_number, "amount": obj.amount,
            "status": obj.payment_status,
            "paid_at": obj.paid_at.isoformat() if obj.paid_at else None,
            "allocations": [{"charge_id": a.charge_id, "amount": a.amount} for a in allocs]}


@router.post("/financial-adjustments")
async def create_adjustment(body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("finance.manage"))):
    obj = FinancialAdjustment(
        entity_type=body.get("entity_type", "CHARGE"), entity_id=body["entity_id"],
        adjustment_type=body.get("adjustment_type", "WAIVER"), amount=int(body["amount"]),
        reason=body.get("reason"), requested_by=user.id if user else None,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "status": obj.status}


@router.post("/financial-adjustments/{adj_id}/approve")
async def approve_adjustment(adj_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(_perm("finance.manage"))):
    obj = await db.get(FinancialAdjustment, adj_id)
    if not obj:
        raise NotFoundError("اصلاحیه یافت نشد")
    if obj.status != "PENDING":
        raise ConflictError("این اصلاحیه قبلاً تعیین تکلیف شده است")
    # D9 (§۲۳): تفکیک تأییدکننده از درخواست‌دهنده — فعلاً هشدار، مسدودسازی پس از تصویب D9
    self_approval = (obj.requested_by and user.id and obj.requested_by == user.id)
    obj.status = "APPROVED"
    obj.approved_by = user.id if user else None
    obj.approved_at = datetime.now(timezone.utc)
    if obj.entity_type == "CHARGE":
        charge = await db.get(Charge, obj.entity_id)
        if charge and charge.status == "UNPAID":
            # F16: اعتبار (WAIVER/DISCOUNT) به paid_amount اضافه می‌شود؛ کاهش نابهجا ممنوع
            charge.paid_amount = min(charge.amount, int(charge.paid_amount or 0) + int(obj.amount))
            if charge_outstanding(charge) <= 0:
                charge.status = "PAID"
    if user:
        await write_audit(db, user_id=user.id, action="ADJUSTMENT_APPROVE", module="finance",
                          entity_type="financial_adjustment", entity_id=obj.id,
                          new_values={"amount": obj.amount, "self_approval": bool(self_approval)})
    await db.commit()
    return {"success": True, "self_approval": bool(self_approval)}


