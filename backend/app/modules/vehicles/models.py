from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class Vehicle(Base, TimestampMixin):
    __tablename__ = "vehicles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_person_id: Mapped[str | None] = mapped_column(ForeignKey("persons.id"), nullable=True, index=True)
    unit_id: Mapped[str | None] = mapped_column(ForeignKey("units.id"), nullable=True, index=True)
    plate_raw: Mapped[str] = mapped_column(String(64))
    plate_normalized: Mapped[str] = mapped_column(String(32), index=True)
    plate_letter: Mapped[str | None] = mapped_column(String(4), nullable=True)
    plate_province_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    plate_province: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plate_city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plate_type: Mapped[str] = mapped_column(String(16), default="PERSONAL")
    vehicle_type: Mapped[str] = mapped_column(String(16), default="CAR")
    brand: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class AccessPermit(Base, TimestampMixin):
    __tablename__ = "access_permits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    plate_normalized: Mapped[str] = mapped_column(String(32), index=True)
    host_unit_id: Mapped[str | None] = mapped_column(ForeignKey("units.id"), nullable=True)
    permit_type: Mapped[str] = mapped_column(String(24), default="PERMANENT")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    allowed_days: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_from_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    allowed_until_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    max_entries: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_entries: Mapped[int] = mapped_column(Integer, default=0)
    allowed_gate_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    issued_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class VehicleRestriction(Base, TimestampMixin):
    __tablename__ = "vehicle_restrictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    plate_normalized: Mapped[str] = mapped_column(String(32), index=True)
    restriction_type: Mapped[str] = mapped_column(String(24), default="BANNED")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)