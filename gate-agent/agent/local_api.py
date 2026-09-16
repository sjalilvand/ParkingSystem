from fastapi import FastAPI
from pydantic import BaseModel

from agent.central_client import central
from agent.config import settings
from agent.database import db
from agent.handler import handle_plate_event
from agent.sync import refresh_snapshot, upload_pending

app = FastAPI(title="Gate Agent Local API", docs_url="/local/docs")


class SimulateRequest(BaseModel):
    plate_raw: str
    direction: str = "IN"
    source_event_id: str | None = None


@app.get("/local/v1/status")
async def status():
    snap = await db.get_snapshot()
    live_online = await central.check_online()
    return {
        "online": live_online,
        "pending_count": await db.pending_count(),
        "has_snapshot": snap is not None,
        "snapshot_version": (snap or {}).get("version"),
        "gate_code": settings.GATE_CODE,
        "agent_version": settings.AGENT_VERSION,
    }


@app.get("/local/v1/events")
async def events():
    return await db.recent_events()


@app.get("/local/v1/snapshot")
async def snapshot():
    return await db.get_snapshot()


@app.post("/local/v1/simulate/plate")
async def simulate_plate(body: SimulateRequest):
    return await handle_plate_event(body.plate_raw, body.source_event_id, body.direction)


@app.post("/local/v1/sync-now")
async def sync_now():
    sent = await upload_pending()
    refreshed = await refresh_snapshot()
    return {"success": True, "sent": sent, "snapshot_refreshed": refreshed,
            "pending_left": await db.pending_count()}