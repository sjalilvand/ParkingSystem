from sqlalchemy import JSON, Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class CadParkingSpot(Base, TimestampMixin):
    __tablename__ = "cad_parking_spots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    parking_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_drawing: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_layer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_entity_handle: Mapped[str | None] = mapped_column(String(32), nullable=True)
    polygon_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    center_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    center_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    area: Mapped[float | None] = mapped_column(Float, nullable=True)
    rotation: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(16), default="free", index=True)
    parking_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(String(256), nullable=True)