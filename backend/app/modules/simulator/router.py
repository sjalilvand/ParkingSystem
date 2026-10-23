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


# ---------------------------------------------------------------------------
# الحاقیه §۲ — کاتالوگ ۲۰ سناریوی الزامی (SIM-01..SIM-20)
# اجرا فقط روی پایگاه‌دادهٔ جداگانهٔ شبیه‌ساز انجام می‌شود.
# ---------------------------------------------------------------------------
from app.core.exceptions import NotFoundError  # noqa: E402
from app.modules.simulator import sim_catalog  # noqa: E402


@router.get("/scenarios")
async def scenarios_list(user: User = Depends(get_current_user)):
    """کاتالوگ کامل: شناسه، عنوان، پیش‌شرط، مراحل، نتیجهٔ مورد انتظار."""
    return {"label": sim_catalog.SIM_LABEL, "items": sim_catalog.catalog_view()}


@router.get("/scenarios/{sid}")
async def scenarios_detail(sid: str, user: User = Depends(get_current_user)):
    items = [s for s in sim_catalog.catalog_view() if s["id"] == sid.upper()]
    if not items:
        raise NotFoundError(f"سناریو {sid} یافت نشد")
    return {"label": sim_catalog.SIM_LABEL, "item": items[0]}


@router.post("/scenarios/{sid}/run")
async def scenarios_run(sid: str, user: User = Depends(get_current_user)):
    """اجرای خودکار سناریو روی DB شبیه‌ساز + داوری PASS/FAIL (برای SIM-20: میدانی)."""
    try:
        return await sim_catalog.run_scenario(sid.upper())
    except KeyError:
        raise NotFoundError(f"سناریو {sid} یافت نشد") from None


@router.get("/isolation")
async def isolation_info(user: User = Depends(get_current_user)):
    """اطلاعات جداسازی: آدرس DB شبیه‌ساز (بدون پسورد) و برچسب الزامی."""
    def _sim_db_safe() -> str:
        from app.db.sim_session import sim_db_label
        return sim_db_label()
    return {
        "label": sim_catalog.SIM_LABEL,
        "sim_database": _sim_db_safe(),
        "separated_from_operational": True,
    }