from pydantic import BaseModel, ConfigDict


class ComplexCreate(BaseModel):
    code: str
    name: str
    address: str | None = None


class TowerCreate(BaseModel):
    complex_id: str
    code: str
    name: str
    floor_count: int = 0


class TowerUpdate(BaseModel):
    name: str | None = None
    floor_count: int | None = None
    is_active: bool | None = None


class UnitCreate(BaseModel):
    tower_id: str
    unit_number: str
    floor_number: int = 0
    area: int | None = None


class UnitUpdate(BaseModel):
    unit_number: str | None = None
    floor_number: int | None = None
    status: str | None = None
    is_active: bool | None = None


class TowerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    complex_id: str
    code: str
    name: str
    floor_count: int
    is_active: bool


class UnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tower_id: str
    unit_number: str
    floor_number: int
    status: str
    is_active: bool


class ComplexOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    address: str | None = None
    is_active: bool