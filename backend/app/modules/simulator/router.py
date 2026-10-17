from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.modules.identity.models import User
from app.modules.simulator import scenario, service

router = APIRouter(prefix="/simulator", tags=["Simulator"])


@router.get("/status")
async def status(user: User = Depends(get_current_user)):
    return service.status()


@router.post("/start")
async def start(interval: float = 4.0, resident_ratio: float = 0.8,
                user: User = Depends(get_current_user)):
    return {"success": service.start(interval, resident_ratio), "status": service.status()}


@router.post("/stop")
async def stop(user: User = Depends(get_current_user)):
    return {"success": service.stop(), "status": service.status()}


@router.post("/tick")
async def tick(user: User = Depends(get_current_user)):
    await service._tick()
    return service.status()


@router.get("/inside")
async def inside(user: User = Depends(get_current_user)):
    return await service.inside_report()


@router.get("/durations")
async def durations(limit: int = 30, user: User = Depends(get_current_user)):
    return await service.durations_report(limit)


# ---------------------------------------------------------------------------
# سناریوی آزمایشی (پاکسازی + ساخت + گام‌به‌گام + دستی)
# ---------------------------------------------------------------------------
class ManualEventIn(BaseModel):
    plate_raw: str
    direction: str = "IN"
    gate_code: str | None = None


@router.post("/scenario/setup")
async def scenario_setup(user: User = Depends(get_current_user)):
    """پاکسازی کامل داده‌ها (به‌جز ادمین/تنظیمات/زیرساخت) + ساخت سناریوی آموزشی."""
    return await scenario.setup_scenario()


@router.get("/scenario/state")
async def scenario_state(user: User = Depends(get_current_user)):
    return await scenario.scenario_state()


@router.post("/scenario/step")
async def scenario_step(user: User = Depends(get_current_user)):
    """اجرای گام بعدی سناریو با توضیح کامل."""
    return await scenario.next_step()


@router.post("/scenario/reset")
async def scenario_reset(user: User = Depends(get_current_user)):
    """بازنشانی نشانگر گام‌ها (بدون تغییر داده‌ها)."""
    return scenario.reset_steps()


@router.post("/scenario/manual")
async def scenario_manual(body: ManualEventIn, user: User = Depends(get_current_user)):
    """رویداد دستی — پلاک تایپی یا کشویی + جهت."""
    return await scenario.manual_event(body.plate_raw, body.direction, body.gate_code)