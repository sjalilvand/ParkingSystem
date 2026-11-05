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
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
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
_last_open: dict = {}  # side -> آخرین زمان بازکردن اتصال RTSP جدید (fallback)
OPEN_COOLDOWN = 6.0    # ثانیه — حداقل فاصلهٔ بازکردن اتصال جدید برای هر سمت


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
    """گرفتن یک فریم — HTTP snapshot (بدون codec) یا RTSP با OpenCV؛ بلاک‌کننده."""
    if poller._is_http(rtsp):
        jpg = poller._fetch_jpeg_sync(rtsp, timeout=settings.CAMERA_CONNECT_TIMEOUT)
        if jpg is None:
            raise _exc("گرفتن تصویر از دوربین HTTP ناموفق بود — آدرس/رمز را بررسی کنید",
                       "CAMERA_UNREACHABLE", 502)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(jpg)
        if out_path.stat().st_size < 3000:
            raise _exc("فریم دریافتی نامعتبر است", "CAMERA_BAD_FRAME", 502)
        return
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


# ---------------------------------------------------------------------------
# تشخیص خودکار مسیر RTSP — دوربین‌های ایرانی/OEM (شهاب، FullHan، های‌سیلیکون، …)
#   دوربین‌های غیر هایک‌ویژن/داهوا معمولاً مسیر stream متفاوتی دارند؛ اگر آدرس
#   ثبت‌شده باز نشد، مسیرهای رایج برندها با همان اعتبارنامه امتحان می‌شوند.
# ---------------------------------------------------------------------------
RTSP_PROBE_PATHS = [
    "",                                      # بدون مسیر (stream پیش‌فرض برخی OEMها)
    "/stream0",                              # FullHan / شهاب / عمومی — main stream
    "/stream1",                              # FullHan / عمومی — sub stream
    "/11",                                   # OEM چینی (۱۱ = کانال۱/جریان اصلی) — رایج‌ترین فرمت دوربین‌های ۱۰۸۰p چینی
    "/12",                                   # OEM چینی — کانال۱/جریان فرعی
    "/0",                                    # OEM — جریان اصلی
    "/1/cif",                                # OEM / V380
    "/h264/ch1/main/av_stream",               # HiSilicon / EZVIZ / Tiandy
    "/Streaming/Channels/101",                # Hikvision / HiWatch
    "/cam/realmonitor?channel=1&subtype=0",   # Dahua / Imou
    "/cam/realmonitor",                       # XMEye (قالب ساده)
    "/live/ch00_0",                           # Ambarella / V380
    "/live/ch0",                              # V380
    "/media/video1",                          # Uniview
    "/onvif1",                                # YOOSEE/OEM — جریان اصلی
    "/onvif2",                                # YOOSEE/OEM — جریان فرعی
    "/ch0_0.h264",                            # Xiaomi / برخی OEM
    "/live0.264",                             # OEM
    "/live1.264",                             # OEM
    "/h264_stream",                           # OEM
    "/av0_0",                                 # JVT
    "/cam1/h264",                             # OEM
    "/ucast/11",                              # OEM / V380
    "/h264/ch1/sub/av_stream",                # HiSilicon — جریان فرعی
    "/h264/ch1/main_av_stream",               # غلط تایپی رایج (زیرخط به‌جای اسلش) — همان HiSilicon
    "/h264/ch1/sub_av_stream",                # غلط تایپی رایج — جریان فرعی
    "/1/1",                                   # Tiandy (قالب جدید)
    "/LiveMedia/ch1/stream1",                 # Huawei — جریان اصلی
    "/LiveMedia/ch1/stream0",                 # Huawei — جریان دوم
    "/1/h264major",                           # مسیرهای ONVIF-native دوربین شهاب IM20A02Y06 — جریان اصلی
    "/1/h264minor",                           # مسیرهای ONVIF-native دوربین شهاب — جریان فرعی
]

# استریم MJPEG روی HTTP (اگر RTSP اصلاً فعال نباشد) — cv2/ffmpeg هر دو را می‌خوانند
HTTP_MJPEG_PATHS = [
    "/videostream.cgi",        # OEM کلاسیک
    "/mjpg/video.mjpg",
    "/videostream.asf",        # ASF روی HTTP
]

# پورت‌های رایج سرویس ONVIF برای کشف خودکار نشانی استریم
ONVIF_PORTS = (80, 8899, 8080, 8999)  # 8999 = پورت ONVIF دوربین‌های شهاب (صفحهٔ PORT تنظیمات دوربین)


def _rtsp_base(rtsp: str) -> tuple[str, str, str]:
    """(پایهٔ rtsp://user:pass@host:port، کاربر، رمز) از URL ثبت‌شده."""
    from urllib.parse import urlsplit
    try:
        p = urlsplit(rtsp.strip())
        userinfo = p.username or ""
        if p.password:
            userinfo += f":{p.password}"
        base = "rtsp://"
        if userinfo:
            base += userinfo + "@"
        base += p.hostname or ""
        if p.port:
            base += f":{p.port}"
        return base, p.username or "", p.password or ""
    except Exception:  # noqa: BLE001
        return rtsp.rstrip("/"), "", ""


def _open_rtsp_once(url: str, timeout_ms: int = 4000) -> bool:
    """یک تلاش باز کردن + خواندن یک فریم با timeout کوتاه (برای probe)."""
    cap = cv2.VideoCapture()
    try:
        try:
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)
        except Exception:  # noqa: BLE001 — نسخه‌های قدیمی OpenCV این props را ندارند
            pass
        if not cap.open(url, cv2.CAP_FFMPEG):
            return False
        ok, frame = cap.read()
        return bool(ok and frame is not None and frame.size > 0)
    except Exception:  # noqa: BLE001
        return False
    finally:
        try:
            cap.release()
        except Exception:  # noqa: BLE001
            pass


def _onvif_stream_uri(host: str, user: str, pw: str,
                      timeout: float = 4.0) -> tuple[str | None, list[str]]:
    """کشف خودکار نشانی استریم از سرویس ONVIF دوربین (GetProfiles → GetStreamUri).
    اگر دوربین ONVIF داشته باشد، مسیر/پورت دقیق را خودش می‌گوید — حتی اگر
    پورت RTSP غیر از 554 باشد.
    خروجی: (URI با اعتبارنامهٔ تزریق‌شده یا None، گزارش تلاش‌ها بدون رمز)"""
    import base64
    import hashlib
    import os as _os
    import re
    from datetime import datetime, timezone
    from urllib.parse import quote, urlsplit

    import httpx

    notes: list[str] = []
    combos: list[tuple[str, str]] = []
    if user:
        combos.append((user, pw))
    for c in (("admin", "admin"), ("admin", "")):
        if c not in combos:
            combos.append(c)

    def _sec(u: str, p: str, digest_mode: bool) -> str:
        nonce = _os.urandom(16)
        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if digest_mode:
            pwd_xml = ('<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/'
                       'oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
                       + base64.b64encode(
                           hashlib.sha1(nonce + created.encode() + p.encode()).digest()
                       ).decode() + "</wsse:Password>")
        else:
            pwd_xml = ('<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/'
                       'oasis-200401-wss-username-token-profile-1.0#PasswordText">'
                       + p + "</wsse:Password>")
        return (
            '<s:Header><wsse:Security s:mustUnderstand="1" xmlns:wsse='
            '"http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
            f"<wsse:UsernameToken><wsse:Username>{u}</wsse:Username>{pwd_xml}"
            '<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/'
            'oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
            + base64.b64encode(nonce).decode() + "</wsse:Nonce>"
            '<wsu:Created xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/'
            'oasis-200401-wss-wssecurity-utility-1.0.xsd">' + created + "</wsu:Created>"
            "</wsse:UsernameToken></wsse:Security></s:Header>"
        )

    def _call(url: str, sec_xml: str, body: str) -> str:
        xml = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
               'xmlns:tt="http://www.onvif.org/ver10/schema">'
               + sec_xml + body + "</s:Envelope>")
        r = httpx.post(url, content=xml.encode(),
                       headers={"Content-Type": "application/soap+xml; charset=utf-8"},
                       timeout=timeout)
        return r.text if r.status_code == 200 else ""

    for port in ONVIF_PORTS:
        url = f"http://{host}:{port}/onvif/device_service"
        for u, p in combos:
            for digest_mode in (True, False):
                try:
                    prof = _call(url, _sec(u, p, digest_mode),
                                 '<s:Body><GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>'
                                 "</s:Body>")
                    if "GetProfilesResponse" not in prof:
                        continue
                    m = re.search(r'<(?:\w+:)?Profiles[^>]*\btoken="([^"]+)"', prof)
                    if not m:
                        continue
                    stream = _call(url, _sec(u, p, digest_mode),
                                   '<s:Body><GetStreamUri xmlns="http://www.onvif.org/ver10/media/wsdl">'
                                   "<StreamSetup><Stream xmlns=\"http://www.onvif.org/ver10/schema\">"
                                   "RTP-Unicast</Stream><Transport xmlns=\"http://www.onvif.org/ver10/schema\">"
                                   "<Protocol>RTSP</Protocol></Transport></StreamSetup>"
                                   f"<ProfileToken>{m.group(1)}</ProfileToken></GetStreamUri></s:Body>")
                    m2 = re.search(r"<(?:\w+:)?Uri>([^<]+)</(?:\w+:)?Uri>", stream)
                    if not m2:
                        continue
                    uri = m2.group(1).strip()
                    if "@" not in uri and uri.lower().startswith("rtsp://"):
                        # تزریق اعتبارنامه در URI برگشتهٔ دوربین
                        parts = urlsplit(uri)
                        uri = f"rtsp://{quote(u)}:{quote(p)}@{parts.netloc}{parts.path}"
                        if parts.query:
                            uri += "?" + parts.query
                    notes.append(f"ONVIF پورت {port} → نشانی استریم گرفته شد ✔")
                    return uri, notes
                except Exception:  # noqa: BLE001 — پورت بعدی/ترکیب بعدی
                    continue
        notes.append(f"ONVIF پورت {port} → پاسخ نداد")
    return None, notes


def _probe_rtsp_sync(rtsp: str) -> tuple[str | None, list[str]]:
    """مسیرهای رایج برندها را با همان user/pass امتحان می‌کند؛ در صورت شکست:
    ۱) ترکیب‌های پیش‌فرض OEM (admin:admin / admin بدون رمز)
    ۲) استریم MJPEG روی HTTP
    ۳) کشف خودکار ONVIF (نشانی را از خود دوربین می‌پرسد)
    خروجی: (اولین URL کار کرده یا None، فهرست «مسیر → نتیجه» بدون رمز برای عیب‌یابی)"""
    from urllib.parse import quote
    base, user, pw = _rtsp_base(rtsp)
    # host[:port] بدون اعتبارنامه و بدون scheme — چه با رمز چه بدون رمز
    host = base.split("@")[-1]
    if host.startswith("rtsp://"):
        host = host[len("rtsp://"):]
    http_user = user or "admin"
    http_pw = pw or "admin"
    tried: list[str] = ["(آدرس ثبت‌شده) → باز نشد"]

    def _try(url: str) -> tuple[str, bool]:
        shown = url.split("@")[-1] if "@" in url else url   # رمز در گزارش نمی‌آید
        return shown, _open_rtsp_once(url)

    candidates = [base + p for p in RTSP_PROBE_PATHS]
    if user:
        # قالب XiongMai/xmeye — اعتبارنامه داخل query (دو امضای رایج)
        candidates.append(f"{base}/user={user}_password={pw}_channel=1_stream=0.sdp")
        candidates.append(
            f"{base}/user={quote(user)}&password={quote(pw)}&channel=1&stream=0.sdp?real_stream")
    else:
        # آدرس بدون رمز — پیش‌فرض‌های رایج OEMها (روی ۵ مسیر پرتکرار)
        host_part = base[len("rtsp://"):]
        for cred in ("admin:admin@", "admin:@"):
            for p in RTSP_PROBE_PATHS[1:6]:
                candidates.append(f"rtsp://{cred}{host_part}{p}")

    # استریم MJPEG روی HTTP (اگر RTSP غیرفعال/غیرموجود باشد) — روی پورت ۸۰، بدون پورت RTSP
    http_host = host.split(":")[0]
    for p in HTTP_MJPEG_PATHS:
        sep = "&" if "?" in p else "?"
        candidates.append(f"http://{http_host}{p}{sep}user={quote(http_user)}&pwd={quote(http_pw)}")
        candidates.append(f"http://{http_host}{p}")

    seen = {rtsp.strip()}
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        shown, ok = _try(c)
        if ok:
            tried.append(f"{shown} → کار کرد ✔")
            return c, tried
        tried.append(f"{shown} → باز نشد")

    # آخرین راه: پرسیدن خودِ دوربین از طریق ONVIF
    try:
        onvif_host = host.split(":")[0]
        uri, notes = _onvif_stream_uri(onvif_host, user, pw)
        tried.extend(notes)
        if uri:
            shown, ok = _try(uri)
            if ok:
                tried.append("ONVIF URI → کار کرد ✔")
                return uri, tried
            tried.append("ONVIF URI → باز نشد")
    except Exception:  # noqa: BLE001
        tried.append("ONVIF → خطا")
    return None, tried


def _no_pass(url: str) -> str:
    """URL بدون رمز برای نمایش در پیام UI."""
    return config_store.mask_rtsp(url or "")


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
            rtsp_str = config_store.fix_rtsp_typo(raw.strip())
            norm[side] = {"rtsp": rtsp_str, "enabled": bool(rtsp_str),
                          "name": norm[side].get("name") or ""}
        elif isinstance(raw, dict):
            prev = norm[side]
            rtsp = config_store.fix_rtsp_typo(str(raw.get("rtsp") or "").strip())
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

    import anyio
    t0 = time.perf_counter()
    out = Path(settings.CAMERA_SNAPSHOT_DIR) / f"cam-test-{side}.jpg"
    # اگر poller برای همین سمت گیرندهٔ زنده دارد، از فریمِ همان استفاده کن —
    # بازکردن اتصال RTSP جدید هنگام کار poller باعث می‌شود برخی دوربین‌ها
    # (از جمله شهاب/های‌سیلیکون) سشن فعال را بیندازند = قطع‌وصلی.
    live = _grabber_frame(side)
    if live is not None:
        try:
            import cv2 as _cv
            out.parent.mkdir(parents=True, exist_ok=True)
            if _cv.imwrite(str(out), live[0], [cv2.IMWRITE_JPEG_QUALITY, 88]):
                ms = round((time.perf_counter() - t0) * 1000)
                return {
                    "success": True, "side": side, "latency_ms": ms,
                    "message": (f"اتصال موفق — از جریان زندهٔ فعال خوانده شد "
                                f"({ms} میلی‌ثانیه، بدون اتصال جدید)"),
                    "frame_url": f"/api/v1/camera/test-frame/{side}?t={int(time.time())}",
                }
        except Exception:  # noqa: BLE001 — مسیر عادی را امتحان کن
            pass
    try:
        await asyncio.wait_for(
            anyio.to_thread.run_sync(_capture_frame_sync, rtsp, out),
            timeout=settings.CAMERA_CONNECT_TIMEOUT + 10)
    except Exception as first_exc:  # noqa: BLE001
        # آدرس HTTP — probe RTSP معنا ندارد؛ پیام شفاف مستقیم
        if poller._is_http(rtsp):
            first_msg = getattr(first_exc, "message", None) or str(first_exc)
            raise _exc(
                f"دوربین HTTP در دسترس نیست — آدرس و رمز را بررسی کنید. ({first_msg})",
                "CAMERA_UNREACHABLE", 502)
        # تشخیص خودکار مسیر — دوربین‌های غیرهایک‌ویژن (مثل شهاب) مسیر دیگری دارند
        found: str | None = None
        tried: list[str] = []
        try:
            found, tried = await asyncio.wait_for(
                anyio.to_thread.run_sync(_probe_rtsp_sync, rtsp),
                timeout=settings.CAMERA_CONNECT_TIMEOUT + 40)
        except Exception:  # noqa: BLE001
            found, tried = None, []
        if found:
            try:
                await asyncio.wait_for(
                    anyio.to_thread.run_sync(_capture_frame_sync, found, out),
                    timeout=settings.CAMERA_CONNECT_TIMEOUT + 10)
            except Exception:  # noqa: BLE001
                found = None
        if found:
            ms = round((time.perf_counter() - t0) * 1000)
            return {
                "success": True, "side": side, "latency_ms": ms,
                "suggested_rtsp": found,
                "message": ("آدرس ثبت‌شده باز نشد، ولی مسیر درست دوربین خودکار شناسایی شد ✔\n"
                            f"{_no_pass(found)}\n"
                            "ذخیره کنید تا خواندن خودکار با همین مسیر شروع شود."),
                "frame_url": f"/api/v1/camera/test-frame/{side}?t={int(time.time())}",
            }
        first_msg = getattr(first_exc, "message", None) or str(first_exc)
        raise _exc(
            f"اتصال RTSP باز نشد — رمز دوربین یا مسیر stream را بررسی کنید. ({first_msg})",
            "CAMERA_UNREACHABLE", 502, {"tried": tried})
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

    # انتخاب کاندیدا (همان منطق poller — فقط خوانشِ قالب‌معتبر) + ثبت رویداد اختیاری
    chosen = None
    for item in (result.get("plates") or []):
        if (item.get("valid") and item.get("system")
                and item.get("confidence", 0) >= (min_conf or settings.CAMERA_MIN_CONF)):
            chosen = item
            break
    resp["chosen"] = chosen
    if auto_emit and chosen:
        # همان dedupe گیت با poller مشترک است — فریم ثابت ۶۰ ثانیه‌ای چند
        # بار رویداد نمی‌سازد (قبلاً هر کلیک یک رویدادِ تکراری می‌ساخت)
        key = poller._norm_key(chosen["system"])
        if key and not poller._should_emit(key):
            resp["event_dropped"] = "رویداد تکراری — در بازهٔ dedupe ثبت نشد"
        else:
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
# استریم زندهٔ MJPEG — نمایش «آنلاین» واقعی در پنل گیت
#   * فریم‌ها از گیرندهٔ poller (worker رهبر) می‌آیند؛
#   * اگر این worker گیرنده ندارد (uvicorn --workers 2 → فقط رهبر گیرنده دارد)
#     و دوربین HTTP است، مستقیم از دوربین گرفته می‌شود — در نتیجه استریم از
#     هر worker درست کار می‌کند و تصویر «فریز/تکراری» نمی‌شود.
#   * سقف هر اتصال: STREAM_MAX_SECONDS — بعد از آن مرورگر با onError به
#     حالت snapshot برمی‌گردد (fallback در CameraBox).
# ---------------------------------------------------------------------------
STREAM_MAX_SECONDS = 900.0   # سقف هر اتصال استریم (۱۵ دقیقه)
STREAM_FPS = 2.0             # حداکثر نرخ ارسال فریم به مرورگر
STREAM_IDLE_LIMIT = 40       # نبودِ فریم متوالی → بستن استریم (خطا به مرورگر)


def _cfg_loaded() -> bool:
    return bool(config_store._cfg_cache)


@router.get("/stream/{side}")
async def stream_mjpeg(side: str,
                       x_api_key: str | None = Header(default=None, alias="X-API-Key"),
                       authorization: str | None = Header(default=None),
                       api_key: str | None = Query(default=None),
                       db: AsyncSession = Depends(get_db)):
    """استریم MJPEG زنده — <img src="/api/v1/camera/stream/IN?api_key=...">."""
    await _authenticate(db, x_api_key, authorization, api_key)
    side = side.upper()
    if side not in config_store.SIDES:
        raise NotFoundError("side باید IN یا OUT باشد")
    cfg = config_store.cached_cfg() if _cfg_loaded() else await config_store.refresh_config_cache(db)
    cam = cfg.get(side) or {}
    url = cam.get("rtsp") or ""
    if not url:
        raise NotFoundError(f"دوربین {side} پیکربندی نشده است — از «تنظیمات دوربین» پنل گیت تنظیم کنید")

    boundary = b"campframe"
    interval = 1.0 / STREAM_FPS

    async def gen():
        import anyio as _anyio
        t0 = time.monotonic()
        last_ts = 0.0
        idle = 0
        yield b"--" + boundary + b"\r\n"
        while True:
            if time.monotonic() - t0 > STREAM_MAX_SECONDS:
                break
            jpg = None
            g = poller._grabbers.get(side)
            if g is not None and HAS_CV2:
                frame, ts = g.latest()
                if frame is not None and ts and ts != last_ts:
                    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ok:
                        jpg = buf.tobytes()
                        last_ts = ts
            if jpg is None and poller._is_http(url):
                # این worker گیرندهٔ زنده ندارد — عکس مستقیم از دوربین (HTTP)
                try:
                    jpg = await _anyio.to_thread.run_sync(
                        poller._fetch_jpeg_sync, url, 6.0)
                except Exception:  # noqa: BLE001
                    jpg = None
            if jpg is None:
                idle += 1
                if idle > STREAM_IDLE_LIMIT:
                    break       # مرورگر onError می‌گیرد → fallback به snapshot
                await asyncio.sleep(0.5)
                continue
            idle = 0
            yield (b"--" + boundary + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                   + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
            await asyncio.sleep(interval)

    return StreamingResponse(
        gen(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary.decode()}",
        headers={"Cache-Control": "no-store, private", "X-Accel-Buffering": "no"},
    )


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

    # ۱٫۲) دوربین HTTP بدون گیرندهٔ زنده — این worker غیرِرهبر است
    #     (uvicorn --workers 2 و گیرندهٔ poller فقط در worker رهبر است).
    #     قبلاً همین‌جا «فایل کهنهٔ کش‌شده» برگردانده می‌شد ⇒ تصویرِ همیشه یکسان!
    #     عکس HTTP یک GET ساده است؛ سشنی نمی‌بندد — مستقیم و تازه می‌گیریم.
    if poller._is_http(cam["rtsp"]):
        import anyio as _anyio
        jpg = await _anyio.to_thread.run_sync(
            poller._fetch_jpeg_sync, cam["rtsp"], 6.0)
        if jpg:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(jpg)
            _cache[side] = {"path": str(out), "ts": now}
            return FileResponse(str(out), media_type="image/jpeg")
        raise _exc("دوربین HTTP در دسترس نیست — آدرس/رمز دوربین را بررسی کنید",
                   "CAMERA_UNREACHABLE", 502)

    # ۱٫۵) خنکیٔ بازکردن اتصال — بازکردن مکرر RTSP (هر ۲-۳ ثانیه) دوربین‌های
    #     OEM/های‌سیلیکون را به افتادنِ سشن‌های فعال وا می‌دارد = حلقهٔ قطع‌وصلی.
    #     در بازهٔ خنکی، آخرین فریم موجود (حتی کهنه) برگردانده می‌شود —
    #     تصویر یخ‌زده بهتر از خطا است و به دوربین فشار نمی‌آید.
    last_open = _last_open.get(side, 0.0)
    if (now - last_open) < OPEN_COOLDOWN and out.exists():
        return FileResponse(str(out), media_type="image/jpeg")
    _last_open[side] = now

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
