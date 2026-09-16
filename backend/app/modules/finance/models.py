from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class Tariff(Base, TimestampMixin):
    __tablename__ = "tariffs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(128))
    vehicle_category: Mapped[str | None] = mapped_column(String(16), nullable=True)
    permit_category: Mapped[str | None] = mapped_column(String(16), nullable=True)
    free_minutes: Mapped[int] = mapped_column(default=0)
    hourly_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    daily_max_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    night_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)


class Charge(Base, TimestampMixin):
    __tablename__ = "charges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    parking_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    violation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    charge_type: Mapped[str] = mapped_column(String(16), default="PARKING")
    amount: Mapped[int] = mapped_column(BigInteger)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="UNPAID", index=True)


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    reference_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    payer_person_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    vehicle_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    plate_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    payment_method: Mapped[str] = mapped_column(String(16), default="CASH")
    payment_status: Mapped[str] = mapped_column(String(16), default="COMPLETED")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operator_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    gateway_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), index=True)
    charge_id: Mapped[str] = mapped_column(ForeignKey("charges.id"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)


class FinancialAdjustment(Base, TimestampMixin):
    __tablename__ = "financial_adjustments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    adjustment_type: Mapped[str] = mapped_column(String(16), default="DISCOUNT")
    amount: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)