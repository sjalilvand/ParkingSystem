from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class PlateRecognitionEvent(Base):
    __tablename__ = "plate_recognition_events"
    __table_args__ = (UniqueConstraint("device_id", "source_event_id", name="uq_plate_dev_src"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    gate_id: Mapped[str] = mapped_column(ForeignKey("gates.id"), index=True)
    device_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(8), default="IN")
    plate_raw: Mapped[str] = mapped_column(String(64))
    plate_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    full_image_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    plate_image_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_event_id: Mapped[str] = mapped_column(String(64), index=True)
    processing_status: Mapped[str] = mapped_column(String(16), default="PROCESSED")
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AccessEvent(Base, TimestampMixin):
    __tablename__ = "access_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    plate_recognition_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    gate_id: Mapped[str] = mapped_column(ForeignKey("gates.id"), index=True)
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    plate_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(24), index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    permit_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    decision_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operator_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    offline_created: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ParkingSession(Base, TimestampMixin):
    __tablename__ = "parking_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    plate_normalized: Mapped[str] = mapped_column(String(32), index=True)
    entry_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    exit_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    entry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    tariff_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    base_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    discount_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    penalty_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    final_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    payment_status: Mapped[str] = mapped_column(String(16), default="UNPAID", index=True)