from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VehicleCreate(BaseModel):
    owner_person_id: str | None = None
    unit_id: str | None = None
    plate_raw: str = Field(min_length=2, max_length=64)
    plate_type: str = "PERSONAL"
    vehicle_type: str = "CAR"
    brand: str | None = None
    model: str | None = None
    color: str | None = None
    year: int | None = None
    notes: str | None = None


class VehicleUpdate(BaseModel):
    vehicle_type: str | None = None
    brand: str | None = None
    model: str | None = None
    color: str | None = None
    year: int | None = None
    is_active: bool | None = None
    notes: str | None = None


class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    owner_person_id: str | None = None
    unit_id: str | None = None
    plate_raw: str
    plate_normalized: str
    plate_letter: str | None = None
    plate_province_code: str | None = None
    plate_province: str | None = None
    plate_city: str | None = None
    plate_type: str
    vehicle_type: str
    brand: str | None = None
    model: str | None = None
    color: str | None = None
    year: int | None = None
    notes: str | None = None
    is_active: bool


class PermitCreate(BaseModel):
    vehicle_id: str | None = None
    plate_raw: str | None = None
    host_unit_id: str | None = None
    permit_type: str = "PERMANENT"
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    allowed_days: list[int] | None = None
    allowed_from_time: str | None = None
    allowed_until_time: str | None = None
    max_entries: int | None = None
    reason: str | None = None


class PermitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    vehicle_id: str | None = None
    plate_normalized: str
    host_unit_id: str | None = None
    permit_type: str
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_entries: int | None = None
    used_entries: int
    status: str
    reason: str | None = None


class PermitCheckRequest(BaseModel):
    plate_raw: str
    gate_id: str | None = None


class RestrictionCreate(BaseModel):
    plate_raw: str
    restriction_type: str = "BANNED"
    reason: str | None = None