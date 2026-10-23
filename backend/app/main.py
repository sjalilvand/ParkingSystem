import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppException
from app.db.session import engine
from app.realtime.manager import manager
from app.realtime.router import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    manager.set_loop(asyncio.get_running_loop())
    # §۲ — اسکیمای شبیه‌ساز پیش از سرو دادن درخواست‌ها (idempotent).
    # بدون این، /simulator/* روی DB خالیِ تازه‌ساخته 500 می‌دهد (no such table).
    # خطا بوت را نمی‌شکند — فقط لاگ می‌شود (سامانهٔ اصلی مستقل از شبیه‌ساز است).
    from loguru import logger

    from app.db.sim_session import ensure_sim_schema, sim_db_label
    try:
        await ensure_sim_schema()
        logger.info(f"[lifespan] simulator schema ready — {sim_db_label()}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[lifespan] simulator schema ensure FAILED (simulator may 500): {exc}")
    # p0005: اطمینان از partial بودن ایندکس نشست باز روی SQLite (ورود دوبارهٔ پلاک بعد از خروج)
    try:
        async with engine.begin() as conn:
            if conn.dialect.name == "sqlite":
                sql = (await conn.execute(text(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND name='uq_open_session_plate'"
                ))).scalar()
                if sql and "WHERE" not in (sql or "").upper():
                    await conn.execute(text("DROP INDEX uq_open_session_plate"))
                    await conn.execute(text(
                        "CREATE UNIQUE INDEX uq_open_session_plate ON parking_sessions (plate_normalized) "
                        "WHERE status = 'OPEN'"))
    except Exception:
        pass
    # الحاقیه §۴: زمان‌بند همگام‌سازی روزانهٔ Google Sheets (۰۳:۰۰ تهران)
    sync_task = None
    if settings.VEHICLE_SYNC_SCHEDULER and settings.GOOGLE_SHEETS_ENABLED:
        sync_task = asyncio.create_task(_vehicle_sync_scheduler_loop())
    yield
    if sync_task:
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    await engine.dispose()


async def _vehicle_sync_scheduler_loop():
    """حلقهٔ زمان‌بندی: روزانه ساعت ۰۳:۰۰ به وقت تهران اجرای sync خودروها.
    هر خطا فقط لاگ می‌شود — جریان اصلی سامانه هرگز متوقف نمی‌شود."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from loguru import logger

    tz = ZoneInfo("Asia/Tehran")
    logger.info("Google Sheets sync scheduler armed (daily 03:00 Tehran)")
    while True:
        try:
            now = datetime.now(tz)
            run_at = now.replace(hour=max(0, min(23, settings.VEHICLE_SYNC_HOUR)),
                                 minute=0, second=0, microsecond=0)
            if run_at <= now:
                run_at += timedelta(days=1)
            await asyncio.sleep((run_at - now).total_seconds())
            from app.db.session import AsyncSessionLocal
            from app.modules.vehicle_sync.service import VehicleSyncService
            async with AsyncSessionLocal() as db:
                result = await VehicleSyncService(db).run(trigger="SCHEDULED")
                logger.info(f"vehicle_sync scheduled run: {result.get('status')} stats={result.get('stats')}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"vehicle_sync scheduler error (retry in 10min): {exc}")
            await asyncio.sleep(600)


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    debug=settings.APP_DEBUG,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Duration-Ms"] = str(duration_ms)
    return response


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {"code": exc.code, "message": exc.message, "details": exc.details},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {"code": "VALIDATION_ERROR", "message": "داده‌های ورودی نامعتبر است", "details": details},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.get("/health/live", tags=["Health"])
async def health_live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
async def health_ready():
    return {"status": "ok"}


@app.get("/health/database", tags=["Health"])
async def health_database():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": True}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "error", "database": False, "detail": str(exc)})


app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(ws_router)

# الحاقیه §۴ — روترهای همگام‌سازی/انطباق (هر endpoint خودش احراز هویت دارد)
from app.modules.vehicle_sync.router import router as vehicle_sync_router  # noqa: E402
app.include_router(vehicle_sync_router, prefix=settings.API_V1_PREFIX)

# صفحه تست پلاک‌خوان — http://localhost:8000/plate-test/
import pathlib

from fastapi.staticfiles import StaticFiles

_plate_test_dir = pathlib.Path(__file__).parent / "modules" / "plate_ocr" / "static"
if _plate_test_dir.exists():
    app.mount("/plate-test", StaticFiles(directory=str(_plate_test_dir), html=True),
              name="plate-test")