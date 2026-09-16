from datetime import datetime

from pydantic import BaseModel, Field


class PlateDetectedRequest(BaseModel):
    gate_code: str
    direction: str = "IN"
    plate_raw: str = Field(min_length=1, max_length=64)
    source_event_id: str = Field(min_length=1, max_length=64)
    device_id: str | None = None
    captured_at: datetime | None = None
    confidence: float | None = None
    raw_payload: dict | None = None
    client_decision: str | None = None


class ManualAccessRequest(BaseModel):
    gate_code: str
    plate_raw: str
    event_type: str = "MANUAL_ENTRY"
    reason: str | None = None


class BarrierOpenRequest(BaseModel):
    gate_code: str
    access_event_id: str | None = None
    reason: str = "OPERATOR_MANUAL_OPEN"


class HeartbeatRequest(BaseModel):
    gate_code: str
    agent_version: str | None = None
    camera_ok: bool = True
    barrier_ok: bool = True
    printer_ok: bool | None = None
    disk_free_mb: int | None = None
    unsynced_count: int = 0


class SyncRequest(BaseModel):
    events: list[PlateDetectedRequest]