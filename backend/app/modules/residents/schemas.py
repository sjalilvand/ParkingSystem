from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class PersonCreate(BaseModel):
    national_code: str | None = None
    first_name: str
    last_name: str
    mobile: str | None = None
    phone: str | None = None
    person_type: str = "OWNER"


class PersonUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    mobile: str | None = None
    phone: str | None = None
    person_type: str | None = None
    is_active: bool | None = None
    photo_file_id: str | None = None


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    national_code: str | None = None
    first_name: str
    last_name: str
    mobile: str | None = None
    person_type: str
    is_active: bool
    photo_file_id: str | None = None


class OccupancyCreate(BaseModel):
    person_id: str
    occupancy_type: str = "OWNER"
    start_date: date = Field(default_factory=date.today)
    is_primary: bool = False


class OccupancyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    unit_id: str
    person_id: str
    occupancy_type: str
    start_date: date
    end_date: date | None = None
    is_primary: bool
    status: str