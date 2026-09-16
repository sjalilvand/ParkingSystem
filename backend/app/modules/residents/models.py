from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, new_uuid


class Person(Base, TimestampMixin):
    __tablename__ = "persons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    national_code: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True, index=True)
    first_name: Mapped[str] = mapped_column(String(64), default="")
    last_name: Mapped[str] = mapped_column(String(64), default="")
    mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    person_type: Mapped[str] = mapped_column(String(16), default="OWNER")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    photo_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    occupancies: Mapped[list["UnitOccupancy"]] = relationship(back_populates="person", lazy="selectin")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class UnitOccupancy(Base, TimestampMixin):
    __tablename__ = "unit_occupancies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id"), index=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("persons.id"), index=True)
    occupancy_type: Mapped[str] = mapped_column(String(16), default="OWNER")
    start_date: Mapped[date] = mapped_column(Date, default=date.today)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")

    person: Mapped[Person] = relationship(back_populates="occupancies")