"""الحاقیه §۴ — مدل‌های همگام‌سازی Google Sheets (شیت خودروها).

اصل غیرتخریبی: sync فقط فیلدهای هویتی/اطلاعاتی مجاز خودرو را می‌سازد/به‌روز
می‌کند؛ هیچ‌گاه بدهی (charges/payments)، محدودیت داخلی (vehicle_restrictions)،
سابقهٔ تردد یا مجوزهای داخلی را حذف یا بازنویسی نمی‌کند. هر تعارض به صف
VehicleSyncConflict می‌رود و فقط با تأیید انسانی تعیین تکلیف می‌شود.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class VehicleExternalRef(Base, TimestampMixin):
    """نگاشت کلید مبدأ (source_system + external_vehicle_id) → خودروی سامانه."""
    __tablename__ = "vehicle_external_refs"
    __table_args__ = (UniqueConstraint("source_system", "external_vehicle_id",
                                       name="uq_ext_ref_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), index=True)
    source_system: Mapped[str] = mapped_column(String(64), default="OPS", index=True)
    external_vehicle_id: Mapped[str] = mapped_column(String(128), index=True)
    external_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VehicleSyncRun(Base, TimestampMixin):
    __tablename__ = "vehicle_sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    trigger: Mapped[str] = mapped_column(String(16), default="MANUAL")  # MANUAL | SCHEDULED
    status: Mapped[str] = mapped_column(String(16), default="RUNNING", index=True)  # RUNNING | SUCCESS | PARTIAL | FAILED
    spreadsheet_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    worksheet: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_valid: Mapped[int] = mapped_column(Integer, default=0)
    rows_created: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    conflicts_count: Mapped[int] = mapped_column(Integer, default=0)
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class VehicleSyncConflict(Base, TimestampMixin):
    __tablename__ = "vehicle_sync_conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_vehicle_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    conflict_type: Mapped[str] = mapped_column(String(32), index=True)
    # INVALID_PLATE | INVALID_DATE | MISSING_REQUIRED | DUPLICATE_KEY |
    # PLATE_MISMATCH | PERMIT_CHANGE | ROW_ERROR
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    incoming: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    current: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    # PENDING | RESOLVED_APPLIED | RESOLVED_SKIPPED
    resolved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
