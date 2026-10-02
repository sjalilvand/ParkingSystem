"""مدل‌های پیکربندی و قوانین (موج ۵a) — مطابق migration p0003."""
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class VehicleGroup(Base, TimestampMixin):
    __tablename__ = "vehicle_groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    membership_kind: Mapped[str] = mapped_column(String(32), default="NONRESIDENT_YARD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    default_tariff_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class EntryExitRule(Base, TimestampMixin):
    __tablename__ = "entry_exit_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    direction: Mapped[str] = mapped_column(String(8), default="ANY")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    condition_mode: Mapped[str] = mapped_column(String(4), default="ALL")
    conditions: Mapped[list] = mapped_column(JSON)
    actions: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="DRAFT")
    effective_from: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class AppSettingHistory(Base):
    __tablename__ = "app_settings_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(String(64), index=True)
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    changed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReceiptTemplate(Base, TimestampMixin):
    __tablename__ = "receipt_templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    paper_width_mm: Mapped[int] = mapped_column(Integer, default=80)
    sections: Mapped[list] = mapped_column(JSON)
    header_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    footer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    show_trial_badge: Mapped[bool] = mapped_column(Boolean, default=False)


class BoxSetting(Base, TimestampMixin):
    __tablename__ = "box_settings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    side: Mapped[str] = mapped_column(String(4), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    buttons: Mapped[list] = mapped_column(JSON)
    messages: Mapped[dict] = mapped_column(JSON)
    font_scale: Mapped[float] = mapped_column(Float, default=1.0)
    colors: Mapped[dict] = mapped_column(JSON, default=dict)
