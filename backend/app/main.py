import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
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
    yield
    await engine.dispose()


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