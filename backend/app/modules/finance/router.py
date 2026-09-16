import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import Case, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.audit import write_audit
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.access_control.models import ParkingSession
from app.modules.finance.models import Charge, FinancialAdjustment, Payment, PaymentAllocation, Tariff
from app.modules.identity.models import User
from app.modules.violations.models import Violation
from app.shared.plate import normalize_plate

router = APIRouter(tags=["Finance"])


class TariffCreate(BaseModel):
    title: str
    free_minutes: int = 0
    hourly_amount: int = 0
    daily_max_amount: int | None = None
    priority: int = 0


class PaymentCreate(BaseModel):
    plate_raw: str | None = None
    vehicle_id: str | None = None
    amount: int = Field(gt=0)
    payment_method: str = "CASH"
    reference_number: str | None = None
    notes: str | None = None


@router.get("/tariffs")
async def list_tariffs(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Tariff).order_by(Tariff.priority.desc()))
    return [{
        "id": t.id, "title": t.title, "free_minutes": t.free_minutes,
        "hourly_amount": t.hourly_amount, "daily_max_amount": t.daily_max_amount,
        "priority": t.priority, "status": t.status,
    } for t in result.scalars().all()]


@router.post("/tariffs")
async def create_tariff(body: TariffCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = Tariff(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"id": obj.id, "title": obj.title, "status": obj.status}


@router.post("/tariffs/{tariff_id}/activate")
async def activate_tariff(tariff_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(Tariff, tariff_id)
    if not obj:
        raise NotFoundError("تعرفه یافت نشد")
    obj.status = "ACTIVE"
    await db.commit()
    return {"success": True}


@router.get("/charges")
async def list_charges(status: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Charge)
    if status:
        query = query.where(Charge.status == status)
    result = await db.execute(query.order_by(Charge.created_at.desc()).limit(200))
    return [{
        "id": c.id, "parking_session_id": c.parking_session_id, "violation_id": c.violation_id,
        "charge_type": c.charge_type, "amount": c.amount, "status": c.status,
        "description": c.description,
    } for c in result.scalars().all()]


@router.get("/debts")
async def list_debts(plate: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """بدهی‌های پرداخت‌نشده با زمینه (پلاک). فیلتر پلاک اختیاری."""
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
        items.append({
            "charge_id": c.id, "charge_type": c.charge_type, "amount": c.amount,
            "plate": plate_map.get(c.parking_session_id or ""), "violation_id": c.violation_id,
            "description": c.description,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })
        total += c.amount
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
        type_priority: Case = case((Charge.charge_type == "PARKING", 0), else_=1)
        query = query.order_by(type_priority, Charge.created_at.asc())
    else:
        query = query.order_by(Charge.created_at.asc())
    return query


@router.post("/payments")
async def create_payment(body: PaymentCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    # Idempotency (سند بخش ۱۳): reference تکراری => همان پاسخ قبلی
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

    payment = Payment(
        reference_number=reference, vehicle_id=vehicle_id, plate_normalized=plate_norm,
        amount=body.amount, payment_method=body.payment_method,
        paid_at=datetime.now(timezone.utc), operator_id=user.id if user else None,
        notes=body.notes,
    )
    db.add(payment)
    await db.flush()

    remaining = body.amount
    allocations = []
    unpaid = (await db.execute(_build_allocation_query(plate_norm))).scalars().all()
    for charge in unpaid:
        if remaining <= 0:
            break
        allocated = min(remaining, charge.amount)
        db.add(PaymentAllocation(payment_id=payment.id, charge_id=charge.id, amount=allocated))
        allocations.append({"charge_id": charge.id, "amount": allocated, "charge_type": charge.charge_type})
        if allocated >= charge.amount:
            charge.status = "PAID"
        remaining -= allocated

    if user:
        await write_audit(db, user_id=user.id, action="PAYMENT_CREATE", module="finance",
                          entity_type="payment", entity_id=payment.id,
                          new_values={"amount": body.amount, "reference": reference})
    await db.commit()
    await db.refresh(payment)
    return {"id": payment.id, "reference_number": payment.reference_number, "amount": payment.amount,
            "allocations": allocations, "remaining_credit": remaining, "duplicate": False}


@router.get("/payments/{payment_id}")
async def get_payment(payment_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
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
async def create_adjustment(body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
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
async def approve_adjustment(adj_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    obj = await db.get(FinancialAdjustment, adj_id)
    if not obj:
        raise NotFoundError("اصلاحیه یافت نشد")
    obj.status = "APPROVED"
    obj.approved_by = user.id if user else None
    obj.approved_at = datetime.now(timezone.utc)
    if obj.entity_type == "CHARGE":
        charge = await db.get(Charge, obj.entity_id)
        if charge and charge.status == "UNPAID" and obj.amount >= charge.amount:
            charge.status = "PAID"
    if user:
        await write_audit(db, user_id=user.id, action="ADJUSTMENT_APPROVE", module="finance",
                          entity_type="financial_adjustment", entity_id=obj.id)
    await db.commit()
    return {"success": True}