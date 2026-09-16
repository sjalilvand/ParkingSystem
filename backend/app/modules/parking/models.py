from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class ParkingSpace(Base, TimestampMixin):
    __tablename__ = "parking_spaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    complex_id: Mapped[str | None] = mapped_column(ForeignKey("complexes.id"), nullable=True, index=True)
    tower_id: Mapped[str | None] = mapped_column(ForeignKey("towers.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    floor: Mapped[int] = mapped_column(Integer, default=0)
    zone: Mapped[str | None] = mapped_column(String(16), nullable=True)
    parking_type: Mapped[str] = mapped_column(String(16), default="PRIVATE")
    map_x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    map_y: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="FREE", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ParkingAssignment(Base, TimestampMixin):
    __tablename__ = "parking_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    parking_space_id: Mapped[str] = mapped_column(ForeignKey("parking_spaces.id"), index=True)
    unit_id: Mapped[str | None] = mapped_column(ForeignKey("units.id"), nullable=True, index=True)
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    assignment_type: Mapped[str] = mapped_column(String(16), default="PERMANENT")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)


class ParkingOccupancy(Base, TimestampMixin):
    __tablename__ = "parking_occupancies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    parking_space_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    vehicle_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    access_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    occupied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    vacated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="GATE")
    status: Mapped[str] = mapped_column(String(16), default="OCCUPIED", index=True)