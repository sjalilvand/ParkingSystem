from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class VehicleBrand(Base, TimestampMixin):
    __tablename__ = "vehicle_brands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name_fa: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name_en: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str] = mapped_column(String(8), default="IR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class VehicleColor(Base, TimestampMixin):
    __tablename__ = "vehicle_colors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name_fa: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    hex_code: Mapped[str] = mapped_column(String(9), default="#9E9E9E")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PlateRegion(Base, TimestampMixin):
    __tablename__ = "plate_regions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    plate_code: Mapped[str] = mapped_column(String(4), index=True)
    province: Mapped[str] = mapped_column(String(64))
    city: Mapped[str] = mapped_column(String(64))
    letters: Mapped[str | None] = mapped_column(Text, nullable=True)