from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, new_uuid


class Complex(Base, TimestampMixin):
    __tablename__ = "complexes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(String(256), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Tehran")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    towers: Mapped[list["Tower"]] = relationship(back_populates="complex", lazy="selectin")


class Tower(Base, TimestampMixin):
    __tablename__ = "towers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    complex_id: Mapped[str] = mapped_column(ForeignKey("complexes.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    floor_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    complex: Mapped[Complex] = relationship(back_populates="towers")
    units: Mapped[list["Unit"]] = relationship(back_populates="tower", lazy="selectin")


class Unit(Base, TimestampMixin):
    __tablename__ = "units"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tower_id: Mapped[str] = mapped_column(ForeignKey("towers.id"), index=True)
    unit_number: Mapped[str] = mapped_column(String(16))
    floor_number: Mapped[int] = mapped_column(Integer, default=0)
    area: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    tower: Mapped[Tower] = relationship(back_populates="units")