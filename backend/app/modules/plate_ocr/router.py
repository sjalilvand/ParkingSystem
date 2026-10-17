"""API پلاک‌خوان — آپلود تصویر و دریافت پلاک‌های خوانده‌شده.

احراز هویت (هم‌الگو با ماژول camera):
  * هدر X-API-Key یا پارامتر api_key (کلید گیت — برای تست/ادغام ماشین‌ها)
  * هدر Authorization: Bearer <JWT>

endpoint ها:
  GET  /api/v1/plate-ocr/status      وضعیت موتور و قابلیت‌ها
  POST /api/v1/plate-ocr/read        تحلیل تصویر (multipart: file)
  GET  /api/v1/plate-ocr/test-page   صفحه تست (ریدایرکت به /plate-test/)
"""
from __future__ import annotations

import secrets
from functools import partial

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException, ForbiddenError, UnauthorizedError
from app.core.permissions import user_is_admin, user_permission_codes
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.plate_ocr.engine import capabilities, get_reader

router = APIRouter(prefix="/plate-ocr", tags=["Plate OCR"])

LOOKUP_PERMISSIONS = {"vehicles.view", "gate.manual_access"}


# ---------------------------------------------------------------------------
# احراز هویت
# ---------------------------------------------------------------------------
def _api_key_ok(x_api_key: str | None, api_key: str | None) -> bool:
    for v in (x_api_key, api_key):
        if v and secrets.compare_digest(v, settings.GATE_API_KEY):
            return True
    return False


async def _current_user_from_bearer(authorization: str | None,
                                    db: AsyncSession) -> User | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    from app.core.security import decode_token
    try:
        payload = decode_token(authorization.replace("Bearer ", "", 1).strip())
    except Exception:
        raise UnauthorizedError("توکن نامعتبر است")
    if payload.get("type") != "access":
        raise UnauthorizedError("نوع توکن نامعتبر است")
    user = await db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise UnauthorizedError("کاربر یافت نشد یا غیرفعال است")
    return user


async def _authenticate(db: AsyncSession, x_api_key: str | None,
                        authorization: str | None, api_key: str | None) -> User | None:
    """کلید گیت → None (سیستم معتمد)؛ وگرنه کاربر JWT."""
    if _api_key_ok(x_api_key, api_key):
        return None
    user = await _current_user_from_bearer(authorization, db)
    if user is None:
        raise UnauthorizedError("احراز هویت لازم است — Bearer token یا X-API-Key")
    return user


# ---------------------------------------------------------------------------
# endpoint ها
# ---------------------------------------------------------------------------
@router.get("/status")
async def status():
    """وضعیت موتور پلاک‌خوان — کدام بک‌اندها نصب/موجود هستند."""
    caps = capabilities(settings.PLATE_OCR_MODELS_DIR)
    ocr_ready = caps["easyocr"] or (caps["crnn_weights"] and caps["torch"])
    return {
        "success": True,
        "ready": ocr_ready,
        "models_dir": settings.PLATE_OCR_MODELS_DIR,
        "capabilities": caps,
        "install_hint": None if ocr_ready else
        "cd backend && pip install -r requirements-ocr.txt  (بار اول مدل‌های EasyOCR دانلود می‌شود)",
    }


@router.post("/read")
async def read_plate(
    file: UploadFile = File(...),
    lookup: bool = Query(default=False, description="جستجوی پلاک در خودروهای ثبت‌شده"),
    min_conf: float = Query(default=0.25, ge=0.05, le=0.95),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
    api_key: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """خواندن پلاک از تصویر آپلودشده (jpg/png/webp/bmp)."""
    user = await _authenticate(db, x_api_key, authorization, api_key)

    # بررسی نوع فایل
    filename = (file.filename or "").lower()
    if filename and not filename.endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp")):
        raise AppException("فرمت فایل پشتیبانی نمی‌شود — jpg/png/webp/bmp",
                           details={"filename": file.filename})

    data = await file.read()
    if not data:
        raise AppException("فایل خالی است")
    max_bytes = settings.PLATE_OCR_MAX_IMAGE_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise AppException(f"حجم تصویر بیش از {settings.PLATE_OCR_MAX_IMAGE_MB}MB است")
    if file.content_type and not file.content_type.startswith("image/"):
        raise AppException("فایل باید تصویر باشد", details={"content_type": file.content_type})

    buf = np.frombuffer(data, dtype=np.uint8)
    bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if bgr is None:
        raise AppException("تصویر قابل خواندن نیست")

    reader = get_reader(settings.PLATE_OCR_MODELS_DIR)
    # OCR سنگین است → اجرا در threadpool تا event-loop بلاک نشود
    import anyio
    result = await anyio.to_thread.run_sync(
        partial(reader.read_image, bgr, min_conf=min_conf)
    )

    vehicles = []
    if lookup and result.get("best"):
        sys_plate = result["best"].get("system")
        if sys_plate:
            # مجوز: کلید گیت = معتمد؛ کاربر JWT نیازمند مجوز خودرو/گیت
            if user is not None:
                perms = set(await user_permission_codes(db, user))
                if not (perms & LOOKUP_PERMISSIONS) and not await user_is_admin(db, user):
                    raise ForbiddenError("برای جستجوی خودرو مجوز لازم است (vehicles.view)")
            vehicles = await _lookup_vehicles(db, sys_plate)

    return {
        "success": result["success"],
        "best": result["best"],
        "plates": result["plates"],
        "vehicles": vehicles,
        "engine": result["engine"],
        "elapsed_ms": result["elapsed_ms"],
        "annotated_b64": result["annotated_b64"],
    }


@router.get("/test-page", include_in_schema=False)
async def test_page():
    return RedirectResponse(url="/plate-test/")


# ---------------------------------------------------------------------------
# جستجوی خودرو بر اساس پلاک نرمال‌شده سیستم
# ---------------------------------------------------------------------------
async def _lookup_vehicles(db: AsyncSession, system_plate: str) -> list[dict]:
    from app.modules.vehicles.models import Vehicle

    rows = (await db.execute(
        select(Vehicle)
        .where(Vehicle.plate_normalized == system_plate)
        .where(Vehicle.is_active.is_(True))
        .limit(5)
    )).scalars().all()
    return [{
        "vehicle_id": v.id,
        "plate_normalized": v.plate_normalized,
        "plate_raw": v.plate_raw,
        "plate_type": v.plate_type,
        "vehicle_type": v.vehicle_type,
        "brand": v.brand,
        "model": v.model,
        "color": v.color,
        "unit_id": v.unit_id,
    } for v in rows]
