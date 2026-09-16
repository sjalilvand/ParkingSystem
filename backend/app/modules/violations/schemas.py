from pydantic import BaseModel, Field


class ViolationCreate(BaseModel):
    plate_raw: str
    violation_type_code: str
    description: str | None = None
    parking_space_id: str | None = None
    client_ref: str | None = Field(default=None, max_length=64)