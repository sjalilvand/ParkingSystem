from pydantic import BaseModel, ConfigDict


class ParkingSpaceCreate(BaseModel):
    complex_id: str | None = None
    tower_id: str | None = None
    code: str
    number: str | None = None
    floor: int = 0
    zone: str | None = None
    parking_type: str = "PRIVATE"


class ParkingSpaceUpdate(BaseModel):
    status: str | None = None
    zone: str | None = None
    is_active: bool | None = None
    parking_type: str | None = None


class ParkingSpaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    number: str | None = None
    floor: int
    zone: str | None = None
    parking_type: str
    status: str
    is_active: bool


class ParkingAssignmentCreate(BaseModel):
    parking_space_id: str
    unit_id: str | None = None
    vehicle_id: str | None = None
    assignment_type: str = "PERMANENT"