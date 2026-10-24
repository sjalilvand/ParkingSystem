"""موج ۷a + الحاقیه §۶ — دوربین‌های گیت: پیکربندی، تست، snapshot و خواندن پلاک.

سناریو A (دوربین ANPR): دوربین خودش پلاک می‌خواند و POST می‌زند به
    /api/v1/gate/events/anpr/{gate}/{direction}  — این ماژول فقط تنظیم/پیش‌نمایش دارد.
سناریو B (دوربین RTSP معمولی): بک‌اند خودش فریم می‌گیرد و با موتور OCR داخلی
    پلاک می‌خواند (poller.py) — endpoint های این فایل تنظیم/تست/اجرای دستی است.

احراز (هم‌الگو با plate-ocr):
  * X-API-Key یا api_key= (کلید گیت) یا Authorization: Bearer <JWT>
"""
from __future__ import annotations

import asyncio
import secrets
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppException, ForbiddenError, NotFoundError, UnauthorizedError
from app.db.session import get_db
from app.modules.camera import config_store, poller

try:
    import cv2
    HAS_CV2 = True
except ImportError:  # pragma: no cover — تصویر Docker سبک بدون OCR
    cv2 = None
    HAS_CV2 = False

router = APIRouter(prefix="/camera", tags=["Camera"])

SNAPSHOT_TTL = 2.0          # ثانیه — کش برای جلوگیری از باز کردن مکرر RTSP
FFMPEG_CANDIDATES = [
    Path("E:/ParkingSystem/tools/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe"),
]

_cache: dict = {}  # side -> {"path": ..., "ts": ...}


# ---------------------------------------------------------------------------
# احراز هویت
# ---------------------------------------------------------------------------
def _api_key_ok(x_api_key: str | None, api_key: str | None) -> bool:
    for v in (x_api_key, api_key):
        if v and secrets.compare_digest(v, settings.GATE_API_KEY):
            return True
    return False


def _exc(message: str, code: str, status: int, details: dict | None = None) -> AppException:
    """AppException با کد/وضعیت مشخص (امضای پایه فقط message/details دارد)."""
    exc = AppException(message, details=details)
    exc.status_code = status
    exc.code = code
    return exc


async def _authenticate(db: AsyncSession, x_api_key: str | None,
                        authorization: str | None, api_key: str | None) -> None:
    """کلید گیت → معتمد؛ وگرنه کاربر JWT باید فعال باشد."""
    if _api_key_ok(x_api_key, api_key):
        return
    if authorization and authorization.startswith("Bearer "):
        from app.core.security import decode_token
        try:
            payload = decode_token(authorization.replace("Bearer ", "", 1).strip())
            if payload.get("type") == "access":
                return
        except Exception:  # noqa: BLE001
            pass
    raise _exc("احراز هویت لازم است — X-API-Key یا Bearer token",
               "CAMERA_AUTH_FAILED", 401)


async def _user_from_bearer(db: AsyncSession, authorization: str | None):
    """کاربر JWT (یا None) — برای بررسی مجوز settings.edit در PUT config."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    from app.core.security import decode_token
    from app.modules.identity.models import User
    try:
        payload = decode_token(authorization.replace("Bearer ", "", 1).strip())
    except Exception:  # noqa: BLE001
        raise UnauthorizedError("توکن نامعتبر است")
    if payload.get("type") != "access":
        raise UnauthorizedError("نوع توکن نامعتبر است")
    user = await db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise UnauthorizedError("کاربر یافت نشد یا غیرفعال است")
    return user


# ---------------------------------------------------------------------------
# گرفتن فریم — ffmpeg (اگر بود) سپس OpenCV
# ---------------------------------------------------------------------------
def _ffmpeg_exe() -> str | None:
    for c in FFMPEG_CANDIDATES:
        if c.exists():
            return str(c)
    return shutil.which("ffmpeg")


def _capture_frame_sync(rtsp: str, out_path: Path) -> None:
    """گرفتن یک فریم با OpenCV — بلاک‌کننده؛ در thread اجرا شود."""
    cap = cv2.VideoCapture(rtsp, cv2.CAP_FFMPEG)
    try:
        if not cap.isOpened():
            raise _exc("دوربین در دسترس نیست — اتصال RTSP باز نشد", "CAMERA_UNREACHABLE", 502)
        deadline = time.monotonic() + settings.CAMERA_CONNECT_TIMEOUT
        frame = None
        # چند فریم اول RTSP اغلب خالی/ناقص‌اند — تا deadline تلاش می‌کنیم
        while time.monotonic() < deadline:
            ok, f = cap.read()
            if ok and f is not None and getattr(f, "size", 0) > 0:
                frame = f
                if frame.shape[0] > 0 and frame.shape[1] > 0:
                    break
            time.sleep(0.05)
        if frame is None:
            raise _exc("فریمی از دوربین دریافت نشد (timeout)", "CAMERA_TIMEOUT", 504)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(out_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            raise _exc("ذخیرهٔ فریم ناموفق بود", "CAMERA_WRITE_FAILED", 500)
        if out_path.stat().st_size < 3000:
            raise _exc("فریم دریافتی نامعتبر است", "CAMERA_BAD_FRAME", 502)
    finally:
        try:
            cap.release()
        except Exception:  # noqa: BLE001
            pass


def _grabber_frame(side: str) -> tuple | None:
    """اگر poller برای این سمت گیرندهٔ زنده دارد، آخرین فریم آن."""
    g = poller._grabbers.get(side)
    if g is None:
        return None
    frame, ts = g.latest()
    if frame is None or not ts or (time.time() - ts) > 5.0:
        return None
    return frame, ts


async def _fresh_frame(side: str, rtsp: str) -> tuple:
    """فریم تازه: اول گیرندهٔ زندهٔ poller، بعد OpenCV در thread."""
    live = _grabber_frame(side)
    if live is not None:
        return live
    if not HAS_CV2:
        raise AppException(
            "OpenCV نصب نیست — در Docker مقدار INSTALL_OCR=true و build مجدد backend لازم است",
            code="OCR_DEPS_MISSING", status_code=503)
    out = Path(settings.CAMERA_SNAPSHOT_DIR) / f"cam-{side}.jpg"
    import anyio
    await anyio.to_thread.run_sync(_capture_frame_sync, rtsp, out)
    import cv2 as _cv
    img = _cv.imread(str(out))
    if img is None:
        raise _exc("خواندن فریم ذخیره‌شده ناموفق بود", "CAMERA_READ_FAILED", 500)
    return img, time.time()


# ---------------------------------------------------------------------------
# endpoint ها — پیکربندی
# ---------------------------------------------------------------------------
@router.get("/config")
async def get_config(x_api_key: str | None = Header(default=None, alias="X-API-Key"),
                     authorization: str | None = Header(default=None),
                     api_key: str | None = Query(default=None),
                     db: AsyncSession = Depends(get_db)):
    await _authenticate(db, x_api_key, authorization, api_key)
    await config_store.refresh_config_cache(db)
    return {"success": True, **config_store.public_cfg()}


@router.put("/config")
async def put_config(body: dict,
                     x_api_key: str | None = Header(default=None, alias="X-API-Key"),
                     authorization: str | None = Header(default=None),
                     api_key: str | None = Query(default=None),
                     db: AsyncSession = Depends(get_db)):
    """ذخیرهٔ پیکربندی — کلید گیت (ادغام ماشین‌ها) یا کاربر با settings.edit."""
    from app.core.audit import write_audit
    from app.core.permissions import user_is_admin, user_permission_codes

    user = None
    if _api_key_ok(x_api_key, api_key):
        user = None          # کلید گیت = معتمد
    else:
        await _authenticate(db, x_api_key, authorization, api_key)
        user = await _user_from_bearer(db, authorization)
        if user is not None:
            perms = set(await user_permission_codes(db, user))
            if "settings.edit" not in perms and not await user_is_admin(db, user):
                raise ForbiddenError("برای تغییر پیکربندی دوربین مجوز لازم است (settings.edit)")

    sides = body.get("sides") if isinstance(body.get("sides"), dict) else body
    norm = config_store.normalize_cfg(None)
    for side in config_store.SIDES:
        raw = sides.get(side)
        if isinstance(raw, str):
            norm[side] = {"rtsp": raw.strip(), "enabled": bool(raw.strip()),
                          "name": norm[side].get("name") or ""}
        elif isinstance(raw, dict):
            prev = norm[side]
            rtsp = str(raw.get("rtsp") or "").strip()
            # *** یعنی رمز قبلی mask شده — دست‌نخورده نگه داشته شود
            if rtsp and "***" in rtsp:
                rtsp = prev.get("rtsp") or ""
            norm[side] = {
                "rtsp": rtsp,
                "enabled": bool(raw.get("enabled", bool(rtsp))),
                "name": str(raw.get("name") or prev.get("name") or ""),
                "gate_code": str(raw.get("gate_code") or prev.get("gate_code") or "").strip(),
                "direction": str(raw.get("direction") or prev.get("direction") or "").strip().upper(),
            }
    if "poll_interval" in body:
        try:
            norm["poll_interval"] = max(3.0, min(120.0, float(body["poll_interval"])))
        except (TypeError, ValueError):
            pass
    if "ocr" in body:
        norm["ocr"] = bool(body["ocr"])

    from app.modules.config_admin.models import AppSetting
    row = (await db.execute(
        select(AppSetting).where(AppSetting.key == config_store.CAMERAS_KEY)
    )).scalar_one_or_none()
    if row:
        row.value = norm
    else:
        row = AppSetting(key=config_store.CAMERAS_KEY, value=norm)
        db.add(row)
    if user is not None:
        await write_audit(db, user_id=user.id, action="CAMERA_CONFIG_UPDATE",
                          module="camera", entity_type="camera", entity_id="config",
                          new_values={"sides": list(config_store.SIDES)})
    await db.commit()
    await config_store.refresh_config_cache(db)
    return {"success": True, **config_store.public_cfg()}


@router.get("/poller-status")
async def poller_status(x_api_key: str | None = Header(default=None, alias="X-API-Key"),
                        authorization: str | None = Header(default=None),
                        api_key: str | None = Query(default=None),
                        db: AsyncSession = Depends(get_db)):
    await _authenticate(db, x_api_key, authorization, api_key)
    st = poller.status_snapshot()
    # زمان‌ها را ISO کن تا در UI قابل نمایش باشد
    for s in st["sides"].values():
        if s.get("last_frame_ts"):
            s["last_frame_iso"] = time.strftime("%Y-%m-%d %H:%M:%S",
                                                time.localtime(s["last_frame_ts"]))
        if s.get("last_ocr_ts"):
            s["last_ocr_iso"] = time.strftime("%Y-%m-%d %H:%M:%S",
                                              time.localtime(s["last_ocr_ts"]))
    return {"success": True, **st}


# ---------------------------------------------------------------------------
# تست اتصال دوربین
# ---------------------------------------------------------------------------
@router.post("/test/{side}")
async def test_camera(side: str,
                      x_api_key: str | None = Header(default=None, alias="X-API-Key"),
                      authorization: str | None = Header(default=None),
                      api_key: str | None = Query(default=None),
                      db: AsyncSession = Depends(get_db)):
    await _authenticate(db, x_api_key, authorization, api_key)
    side = side.upper()
    if side not in config_store.SIDES:
        raise NotFoundError("side باید IN یا OUT باشد")
    cfg = config_store.cached_cfg() if _cfg_loaded() else await config_store.refresh_config_cache(db)
    cam = cfg.get(side) or {}
    rtsp = cam.get("rtsp") or ""
    if not rtsp:
        raise NotFoundError(f"دوربین {side} هنوز پیکربندی نشده است")
    if not rtsp.lower().startswith(("rtsp://", "http://", "https://")):
        raise _exc("آدرس دوربین باید با rtsp:// شروع شود", "BAD_RTSP_URL", 400)
    if not HAS_CV2:
        raise _exc("OpenCV نصب نیست (INSTALL_OCR=true + build مجدد)",
                   "OCR_DEPS_MISSING", 503)

    t0 = time.perf_counter()
    try:
        import anyio
        out = Path(settings.CAMERA_SNAPSHOT_DIR) / f"cam-test-{side}.jpg"
        await asyncio.wait_for(
            anyio.to_thread.run_sync(_capture_frame_sync, rtsp, out),
            timeout=settings.CAMERA_CONNECT_TIMEOUT + 10)
    except AppException:
        raise
    except asyncio.TimeoutError:
        raise _exc("زمان تست به پایان رسید — دوربین پاسخ نداد", "CAMERA_TIMEOUT", 504)
    except Exception as exc:  # noqa: BLE001
        raise _exc(f"تست ناموفق: {type(exc).__name__}: {exc}",
                   "CAMERA_TEST_FAILED", 502)
    ms = round((time.perf_counter() - t0) * 1000)
    return {
        "success": True, "side": side, "latency_ms": ms,
        "message": f"اتصال موفق — فریم گرفته شد ({ms} میلی‌ثانیه)",
        "frame_url": f"/api/v1/camera/test-frame/{side}?t={int(time.time())}",
    }


@router.get("/test-frame/{side}")
async def test_frame(side: str,
                     x_api_key: str | None = Header(default=None, alias="X-API-Key"),
                     authorization: str | None = Header(default=None),
                     api_key: str | None = Query(default=None),
                     db: AsyncSession = Depends(get_db)):
    await _authenticate(db, x_api_key, authorization, api_key)
    side = side.upper()
    p = Path(settings.CAMERA_SNAPSHOT_DIR) / f"cam-test-{side}.jpg"
    if not p.exists():
        raise NotFoundError("فریمی برای نمایش نیست — ابتدا تست اتصال را اجرا کنید")
    return FileResponse(str(p), media_type="image/jpeg")


# ---------------------------------------------------------------------------
# عکس + خواندن پلاک (اجرای دستی همان کاری که poller خودکار می‌کند)
# ---------------------------------------------------------------------------
@router.post("/capture-ocr/{side}")
async def capture_ocr(side: str,
                      auto_emit: bool = Query(default=False,
                                              description="پلاک خوانده‌شده به‌عنوان رویداد گیت ثبت شود؟"),
                      min_conf: float = Query(default=None, ge=0.05, le=0.95),
                      x_api_key: str | None = Header(default=None, alias="X-API-Key"),
                      authorization: str | None = Header(default=None),
                      api_key: str | None = Query(default=None),
                      db: AsyncSession = Depends(get_db)):
    await _authenticate(db, x_api_key, authorization, api_key)
    side = side.upper()
    if side not in config_store.SIDES:
        raise NotFoundError("side باید IN یا OUT باشد")
    if not (HAS_CV2 and poller.HAS_CV2):
        raise _exc("موتور پلاک‌خوان در این نصب فعال نیست", "OCR_DEPS_MISSING", 503,
                   {"install_docker": "INSTALL_OCR=true در .env.prod و build مجدد backend"})
    cfg = config_store.cached_cfg() if _cfg_loaded() else await config_store.refresh_config_cache(db)
    cam = cfg.get(side) or {}
    if not cam.get("rtsp"):
        raise NotFoundError(f"دوربین {side} پیکربندی نشده است")

    bgr, ts = await _fresh_frame(side, cam["rtsp"])

    from app.modules.plate_ocr.engine import get_reader
    reader = get_reader(settings.PLATE_OCR_MODELS_DIR)
    import anyio
    result = await anyio.to_thread.run_sync(
        lambda: reader.read_image(bgr, min_conf=(min_conf or settings.CAMERA_MIN_CONF),
                                  fast_mode=True))

    out = Path(settings.CAMERA_SNAPSHOT_DIR) / f"cam-{side}.jpg"
    try:
        import cv2 as _cv
        out.parent.mkdir(parents=True, exist_ok=True)
        _cv.imwrite(str(out), bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
        _cache[side] = {"path": str(out), "ts": time.time()}
    except Exception:  # noqa: BLE001
        pass

    resp: dict = {
        "success": result.get("success", False),
        "side": side,
        "best": result.get("best"),
        "plates": result.get("plates"),
        "elapsed_ms": result.get("elapsed_ms"),
        "frame_url": f"/api/v1/camera/snapshot/{side}?t={int(time.time())}",
    }

    # انتخاب کاندیدا (همان منطق poller) + ثبت رویداد اختیاری
    chosen = None
    for item in (result.get("plates") or []):
        if item.get("system") and item.get("confidence", 0) >= (min_conf or settings.CAMERA_MIN_CONF):
            chosen = item
            break
    resp["chosen"] = chosen
    if auto_emit and chosen:
        from app.modules.camera.events import emit_plate_event
        gate_code = cam.get("gate_code") or f"GATE-{side}-01"
        direction = cam.get("direction") or side
        try:
            ev = await emit_plate_event(
                db, gate_code=gate_code, direction=direction,
                plate_raw=chosen["system"],
                confidence=round(float(chosen.get("confidence") or 0) * 100, 1),
                source="camera-capture")
            resp["event"] = ev
        except Exception as exc:  # noqa: BLE001
            resp["event_error"] = f"{type(exc).__name__}: {exc}"
    return resp


# ---------------------------------------------------------------------------
# snapshot زنده (پنل گیت) — با کش TTL
# ---------------------------------------------------------------------------
def _cfg_loaded() -> bool:
    return bool(config_store._cfg_cache)


@router.get("/snapshot/{side}")
async def snapshot(side: str,
                   x_api_key: str | None = Header(default=None, alias="X-API-Key"),
                   authorization: str | None = Header(default=None),
                   api_key: str | None = Query(default=None),
                   db: AsyncSession = Depends(get_db)):
    await _authenticate(db, x_api_key, authorization, api_key)
    side = side.upper()
    if side not in config_store.SIDES:
        raise NotFoundError("side باید IN یا OUT باشد")
    cfg = config_store.cached_cfg() if _cfg_loaded() else await config_store.refresh_config_cache(db)
    cam = cfg.get(side) or {}
    if not cam.get("rtsp"):
        raise NotFoundError(f"دوربین {side} پیکربندی نشده است — از «تنظیمات دوربین» پنل گیت تنظیم کنید")

    now = time.time()
    cached = _cache.get(side)
    if cached and (now - cached["ts"]) < SNAPSHOT_TTL and Path(cached["path"]).exists():
        return FileResponse(cached["path"], media_type="image/jpeg")

    out = Path(settings.CAMERA_SNAPSHOT_DIR) / f"cam-{side}.jpg"

    # ۱) فریم زندهٔ poller (اگر در حال اجراست) — بدون باز کردن اتصال جدید
    live = _grabber_frame(side)
    if live is not None:
        import cv2 as _cv
        frame = live[0]
        out.parent.mkdir(parents=True, exist_ok=True)
        if _cv.imwrite(str(out), frame, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            _cache[side] = {"path": str(out), "ts": now}
            return FileResponse(str(out), media_type="image/jpeg")

    # ۲) ffmpeg (روی سرور ویندوزی) — یک فریم سریع
    ff = _ffmpeg_exe()
    if ff:
        rtsp = cam["rtsp"]
        proc = await asyncio.create_subprocess_exec(
            ff, "-y", "-v", "error", "-rtsp_transport", "tcp", "-i", rtsp,
            "-frames:v", "1", "-q:v", "4", str(out),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=12)
        except asyncio.TimeoutError:
            proc.kill()
            raise NotFoundError("timeout گرفتن فریم از دوربین")
        if proc.returncode == 0 and out.exists() and out.stat().st_size >= 3000:
            _cache[side] = {"path": str(out), "ts": now}
            return FileResponse(str(out), media_type="image/jpeg")

    # ۳) OpenCV در thread (مسیر اصلی در کانتینر)
    await anyio_to_thread_capture(side, cam["rtsp"], out)
    _cache[side] = {"path": str(out), "ts": now}
    return FileResponse(str(out), media_type="image/jpeg")


async def anyio_to_thread_capture(side: str, rtsp: str, out: Path) -> None:
    import anyio
    try:
        await asyncio.wait_for(
            anyio.to_thread.run_sync(_capture_frame_sync, rtsp, out),
            timeout=settings.CAMERA_CONNECT_TIMEOUT + 10)
    except AppException as exc:
        # پیام فارسی مناسب پنل
        raise NotFoundError(
            f"دوربین {side} در دسترس نیست: {exc.message if hasattr(exc, 'message') else exc}")
    except asyncio.TimeoutError:
        raise NotFoundError(f"دوربین {side} در دسترس نیست (timeout)")
    except Exception as exc:  # noqa: BLE001
        raise NotFoundError(f"دوربین {side} در دسترس نیست: {type(exc).__name__}")


@router.head("/snapshot/{side}")
async def snapshot_head(side: str):
    """برای preflight سادهٔ UI — بدون محتوا."""
    return JSONResponse(content={}, status_code=200)
