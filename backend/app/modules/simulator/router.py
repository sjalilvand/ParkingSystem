from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.modules.identity.models import User
from app.modules.simulator import service

router = APIRouter(prefix="/simulator", tags=["Simulator"])


@router.get("/status")
async def status(user: User = Depends(get_current_user)):
    return service.status()


@router.post("/start")
async def start(interval: float = 4.0, resident_ratio: float = 0.6,
                user: User = Depends(get_current_user)):
    return {"success": service.start(interval, resident_ratio), "status": service.status()}


@router.post("/stop")
async def stop(user: User = Depends(get_current_user)):
    return {"success": service.stop(), "status": service.status()}


@router.post("/tick")
async def tick(user: User = Depends(get_current_user)):
    await service._tick()
    return service.status()