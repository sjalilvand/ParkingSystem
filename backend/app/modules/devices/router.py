from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.modules.devices.models import Device, Gate
from app.modules.identity.models import User

router = APIRouter(tags=["Devices"])


@router.get("/gates")
async def list_gates(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Gate))
    return [{
        "id": g.id, "code": g.code, "name": g.name, "direction": g.direction,
        "status": g.status,
        "last_seen_at": g.last_seen_at.isoformat() if g.last_seen_at else None,
        "agent_version": g.agent_version,
    } for g in result.scalars().all()]


@router.post("/gates")
async def create_gate(body: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    gate = Gate(code=body["code"], name=body.get("name", body["code"]),
                direction=body.get("direction", "IN"), complex_id=body.get("complex_id"))
    db.add(gate)
    await db.commit()
    await db.refresh(gate)
    return {"id": gate.id, "code": gate.code}


@router.get("/devices")
async def list_devices(gate_id: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Device)
    if gate_id:
        query = query.where(Device.gate_id == gate_id)
    result = await db.execute(query)
    return [{
        "id": d.id, "gate_id": d.gate_id, "device_type": d.device_type,
        "vendor": d.vendor, "model": d.model, "status": d.status,
        "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
    } for d in result.scalars().all()]