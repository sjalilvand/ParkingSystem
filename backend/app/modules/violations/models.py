from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class ViolationType(Base, TimestampMixin):
    __tablename__ = "violation_types"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(128))
    default_penalty_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    requires_image: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Violation(Base, TimestampMixin):
    __tablename__ = "violations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True, index=True)
    plate_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    violation_type_id: Mapped[str] = mapped_column(ForeignKey("violation_types.id"))
    parking_space_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    gate_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    penalty_amount: Mapped[int] = mapped_column(BigInteger, default=0)
    registered_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="REGISTERED", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    client_ref: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    image_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class ViolationAppeal(Base, TimestampMixin):
    __tablename__ = "violation_appeals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    violation_id: Mapped[str] = mapped_column(ForeignKey("violations.id"), index=True)
    submitted_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="SUBMITTED")
    review_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)