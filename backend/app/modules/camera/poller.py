"""حلقهٔ دوربین‌های گیت — سناریو B: دوربین RTSP معمولی + موتور OCR داخلی بک‌اند.

معماری:
  * برای هر دوربین فعال یک thread گیرندهٔ فریم (FrameGrabber) RTSP را باز نگه
    می‌دارد و همیشه «آخرین فریم» را در بافر دارد (drain کردن بافر RTSP).
  * حلقهٔ async هر poll_interval ثانیه آخرین فریم را به موتور پلاک‌خوان
    (EasyOCR داخلی کانتینر) می‌دهد؛ پلاک معتبر → رویداد گیت (تصمیم/اعلان/راهبند).
  * با --workers 2 فقط یک worker رهبر می‌شود (قفل Redis؛ نبود Redis → تک‌worker).
  * هیچ خطایی حلقه را نمی‌بندد — همهٔ خطاها در STATUS برای پنل گیت دیده می‌شوند.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from app.core.config import settings

try:  # وابستگی‌های OCR اختیاری‌اند
    import cv2
    HAS_CV2 = True
except ImportError:  # pragma: no cover
    cv2 = None
    HAS_CV2 = False

from app.modules.camera.config_store import SIDES, cached_cfg, mask_rtsp

STATUS: dict = {
    "running": False,
    "leader": False,
    "ocr_ready": False,
    "started_at": None,
    "sides": {},
}

_grabbers: dict[str, "FrameGrabber"] = {}
_cfg_sig: str = ""          # امضای پیکربندی — تغییر آن گیرنده‌ها را بازسازی می‌کند
_task: asyncio.Task | None = None
_frame_lock = threading.Lock()
_warmup_done = threading.Event()

_last_emit: dict[str, float] = {}        # dedupe رویداد گیت: کلید پلاک → زمان آخرین ثبت
_last_emit_review: dict[str, float] = {} # dedupe جدا برای ردیف‌های کم‌اطمینان بازبینی


# ---------------------------------------------------------------------------
# منبع HTTP — گرفتن JPEG از دوربین بدون RTSP
#   دوربین شهاب/های‌سیلیکون این پروژه روی RTSP استریم H265 می‌دهد که در
#   کانتینر ناپایدار است؛ ولی /jpgimage/1/image.jpg (HTTP) همیشه JPEG واقعی
#   می‌دهد — این مسیر بدون codec/سشن RTSP کار می‌کند و برای گیت کافی است.
# ---------------------------------------------------------------------------
def _is_http(url: str) -> bool:
    return bool((url or "").lower().startswith(("http://", "https://")))


_auth_cache: dict = {}      # base-url → httpx.Auth که قبلاً جواب داده


def _fetch_jpeg_sync(url: str, timeout: float = 6.0) -> bytes | None:
    """یک فریم JPEG از آدرس HTTP دوربین — با زنجیرهٔ احراز (کش‌شده → Basic → Digest → بدون احراز).

    فقط پاسخِ واقعاً JPEG (امضای FFD8 و >۳KB) پذیرفته می‌شود — صفحات خطای
    HTML/متنی دوربین رد می‌شوند. خروجی None = همهٔ تلاش‌ها ناموفق.
    """
    import httpx
    from urllib.parse import urlsplit, urlunsplit

    try:
        p = urlsplit((url or "").strip())
        if p.scheme not in ("http", "https"):
            return None
        target = urlunsplit((p.scheme, p.netloc, p.path or "/", p.query, ""))
    except Exception:  # noqa: BLE001
        return None
    key = f"{p.scheme}://{p.netloc}{p.path}"

    auths: list = []
    if p.username:
        u, pw = p.username, p.password or ""
        cached = _auth_cache.get(key)
        if cached is not None:
            auths.append(cached)                 # همان که قبلاً جواب داده — سریع
        auths += [httpx.BasicAuth(u, pw), httpx.DigestAuth(u, pw), None]
    else:
        auths = [None]

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as cl:
            for a in auths:
                try:
                    r = cl.get(target, auth=a)
                except Exception:  # noqa: BLE001
                    continue
                if (r.status_code == 200 and len(r.content) > 3000
                        and r.content[:2] == b"\xff\xd8"):
                    if a is not None:
                        _auth_cache[key] = a
                    return r.content
    except Exception:  # noqa: BLE001
        return None
    return None


# ---------------------------------------------------------------------------
# گیرندهٔ فریم — اتصال پایدار RTSP در thread جدا
# ---------------------------------------------------------------------------
class FrameGrabber(threading.Thread):
    def __init__(self, side: str, rtsp: str):
        super().__init__(daemon=True, name=f"cam-{side}")
        self.side = side
        self.rtsp = rtsp
        self.http_mode = _is_http(rtsp)   # آدرس HTTP/JPEG — بدون RTSP
        self._frame = None
        self._ts = 0.0
        self.connected = False
        self.reconnects = 0
        self._size_logged = False
        self._stop_evt = threading.Event()

    def run(self) -> None:  # noqa: C901 — حلقهٔ مقاوم
        if self.http_mode:
            self._run_http()
            return
        cap = None
        fails = 0
        while not self._stop_evt.is_set():
            if cap is None:
                try:
                    # timeout در سطح FFmpeg — اتصال مرده معلق نمی‌ماند و سریع
                    # تشخیص داده می‌شود (پیش‌فرض: بی‌نهایت → قطع‌وصلی نامرئی)
                    cap = cv2.VideoCapture()
                    try:
                        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                                int(settings.CAMERA_CONNECT_TIMEOUT * 1000))
                        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                                int(settings.CAMERA_READ_TIMEOUT * 1000))
                    except Exception:
                        pass
                    cap.open(self.rtsp, cv2.CAP_FFMPEG)
                    try:
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    except Exception:
                        pass
                except Exception as exc:
                    self._set_error(f"بازکردن RTSP ناموفق: {type(exc).__name__}")
                    cap = None
                    self._stop_evt.wait(4.0)
                    continue
                if not cap.isOpened():
                    self.connected = False
                    self.reconnects += 1
                    self._set_error(f"دوربین در دسترس نیست (تلاش {self.reconnects})")
                    # لاگ پرسرخت — تا در docker logs «دلیلی» دیده شود نه سکوت
                    if self.reconnects == 1 or self.reconnects % 10 == 0:
                        logger.warning(f"[camera:{self.side}] RTSP باز نشد "
                                       f"(تلاش {self.reconnects}) — {mask_rtsp(self.rtsp)}")
                    cap.release()
                    cap = None
                    self._stop_evt.wait(4.0)
                    continue
                self.connected = True
                fails = 0
                self._set_error(None)
                suffix = f" (اتصال دوباره #{self.reconnects})" if self.reconnects else ""
                logger.info(f"[camera:{self.side}] RTSP متصل شد{suffix}")
            ok, frame = cap.read()
            if not ok:
                self.connected = False
                fails += 1
                self._set_error("خواندن فریم قطع شد — اتصال دوباره…")
                if fails >= 2:
                    # دو خوانش ناموفق پشت‌سرهم = استریم مرده — اتصال از نو
                    cap.release()
                    cap = None
                    self.reconnects += 1
                    self._stop_evt.wait(2.0)
                else:
                    # خطای گذرا — با همان اتصال ادامه بده
                    self._stop_evt.wait(1.0)
                continue
            fails = 0
            if not self._size_logged:
                self._size_logged = True
                h, w = frame.shape[:2]
                logger.info(f"[camera:{self.side}] فریم اول: {w}×{h}")
            with _frame_lock:
                self._frame = frame
                self._ts = time.time()

    def _run_http(self) -> None:
        """حالت HTTP — ~۱ فریم بر ثانیه JPEG از دوربین (بدون RTSP، بدون codec)."""
        import numpy as np
        while not self._stop_evt.is_set():
            jpg = _fetch_jpeg_sync(self.rtsp)
            if jpg is None:
                self.connected = False
                self.reconnects += 1
                self._set_error("گرفتن تصویر HTTP ناموفق — آدرس/رمز دوربین را بررسی کنید")
                if self.reconnects == 1 or self.reconnects % 5 == 0:
                    logger.warning(f"[camera:{self.side}] HTTP snapshot ناموفق "
                                   f"(تلاش {self.reconnects}) — {mask_rtsp(self.rtsp)}")
                self._stop_evt.wait(2.0)
                continue
            frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                self._set_error("تصویر HTTP قابل decode نیست")
                self._stop_evt.wait(1.0)
                continue
            self.connected = True
            self.reconnects = 0
            self._set_error(None)
            if not self._size_logged:
                self._size_logged = True
                h, w = frame.shape[:2]
                logger.info(f"[camera:{self.side}] HTTP snapshot فعال — فریم {w}×{h}")
            with _frame_lock:
                self._frame = frame
                self._ts = time.time()
            self._stop_evt.wait(1.0)

    def latest(self) -> tuple:
        with _frame_lock:
            if self._frame is None:
                return None, 0.0
            return self._frame.copy(), self._ts

    def _set_error(self, msg: str) -> None:
        STATUS["sides"].setdefault(self.side, {})["last_error"] = msg

    def stop(self) -> None:
        self._stop_evt.set()


# ---------------------------------------------------------------------------
# وضعیت
# ---------------------------------------------------------------------------
def _side_status(side: str) -> dict:
    return STATUS["sides"].setdefault(side, {
        "enabled": False, "connected": False, "has_frame": False,
        "last_frame_ts": None, "last_ocr_ts": None, "last_ocr_ms": None,
        "last_plate": None, "last_plate_fa": None, "last_conf": None,
        "events_sent": 0, "last_error": None,
        "low_conf_skipped": 0, "last_skipped": None,
        "frames_scanned": 0,
    })


def status_snapshot() -> dict:
    """نسخهٔ JSON-شدنی وضعیت برای پنل گیت."""
    for side in SIDES:
        g = _grabbers.get(side)
        st = _side_status(side)
        if g is not None:
            st["connected"] = g.connected
            st["reconnects"] = g.reconnects
            _, ts = g.latest()
            st["has_frame"] = ts > 0
            st["last_frame_ts"] = ts if ts else None
    return {
        **STATUS,
        "ocr_installed": HAS_CV2,
        "poll_interval": cached_cfg().get("poll_interval"),
        "sides": {k: dict(v) for k, v in STATUS["sides"].items()},
    }


# ---------------------------------------------------------------------------
# OCR یک فریم + ساخت رویداد
# ---------------------------------------------------------------------------
def _ocr_sync(bgr) -> dict:
    from app.modules.plate_ocr.engine import get_reader
    reader = get_reader(settings.PLATE_OCR_MODELS_DIR)
    return reader.read_image(bgr, min_conf=settings.CAMERA_MIN_CONF, fast_mode=True)


def _norm_key(plate: str) -> str:
    """کلید dedupe — نرمالِ سیستم اگر ممکن باشد؛ وگرنه فقط ارقام/حروف."""
    try:
        from app.shared.plate import normalize_plate
        n = normalize_plate(plate)
        if n:
            return n
    except Exception:
        pass
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return "".join(ch for ch in (plate or "").translate(table).upper()
                   if ("A" <= ch <= "Z") or ("0" <= ch <= "9"))


def _should_emit(key: str) -> bool:
    now = time.monotonic()
    prev = _last_emit.get(key)
    if prev and (now - prev) < settings.CAMERA_DEDUPE_TTL:
        return False
    _last_emit[key] = now
    # پاکسازی کلیدهای قدیمی (جلوگیری از رشد بی‌حد)
    if len(_last_emit) > 500:
        cutoff = now - max(60.0, settings.CAMERA_DEDUPE_TTL * 4)
        for k in [k for k, v in _last_emit.items() if v < cutoff]:
            _last_emit.pop(k, None)
    return True


def _should_emit_review(key: str) -> bool:
    """dedupe مستقل برای ردیف‌های کم‌اطمینان — نباید با رویداد اصلی تداخل کند:
    اگر یک نگاه اولیهٔ کم‌اطمینان، dedupe رویداد اصلی را پر می‌کرد، خوانش
    خوبِ چند ثانیه بعد مسدود می‌شد و رویداد گیت از دست می‌رفت."""
    now = time.monotonic()
    prev = _last_emit_review.get(key)
    if prev and (now - prev) < settings.CAMERA_DEDUPE_TTL:
        return False
    _last_emit_review[key] = now
    if len(_last_emit_review) > 500:
        cutoff = now - max(60.0, settings.CAMERA_DEDUPE_TTL * 4)
        for k in [k for k, v in _last_emit_review.items() if v < cutoff]:
            _last_emit_review.pop(k, None)
    return True


def _save_capture(side: str, bgr, plate_text: str | None) -> str | None:
    try:
        out_dir = Path(settings.CAMERA_SNAPSHOT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        tag = _norm_key(plate_text) or "unknown"
        p = out_dir / f"cam-{side}-{tag}-{int(time.time())}.jpg"
        cv2.imwrite(str(p), bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        # نگه‌داری حداکثر ۲۰۰ فایل
        files = sorted(out_dir.glob("cam-*.jpg"))
        for old in files[:-200]:
            try:
                old.unlink()
            except OSError:
                pass
        return str(p)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[camera:{side}] save capture FAILED: {exc}")
        return None


async def _upload_event_images(db, side: str, bgr, chosen: dict) -> tuple:
    """آپلود عکس کامل + برش پلاک در MinIO و ساخت FileRecord — best-effort.

    خروجی (full_image_file_id, plate_image_file_id) و به ردیف
    PlateRecognitionEvent وصل می‌شود تا عکس هر عبور در جدول رویدادها دیده
    شود. هر خطا فقط لاگ می‌شود — ثبت رویداد گیت هرگز به خاطر عکس متوقف
    نمی‌شود. FileRecord در همان sessionِ رویداد flush می‌شود تا همه‌چیز
    یک‌جا commit شود.
    """
    try:
        import anyio
        from app.core.system_models import FileRecord
        from app.integrations import storage

        ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return None, None
        full_bytes = buf.tobytes()

        crop_bytes = None
        box = chosen.get("box")
        if box and len(box) == 4:
            h, w = bgr.shape[:2]
            x1, y1, x2, y2 = [int(v) for v in box]
            px = max(8, int((x2 - x1) * 0.15))
            py = max(8, int((y2 - y1) * 0.30))
            x1, y1 = max(0, x1 - px), max(0, y1 - py)
            x2, y2 = min(w, x2 + px), min(h, y2 + py)
            if x2 > x1 and y2 > y1:
                okc, cbuf = cv2.imencode(".jpg", bgr[y1:y2, x1:x2],
                                         [cv2.IMWRITE_JPEG_QUALITY, 90])
                if okc:
                    crop_bytes = cbuf.tobytes()

        tag = chosen.get("system") or "unknown"

        def _put() -> tuple:
            info = storage.upload_bytes(
                full_bytes, prefix="gate-captures",
                original_name=f"cam-{side}-{tag}.jpg", content_type="image/jpeg")
            info2 = None
            if crop_bytes:
                info2 = storage.upload_bytes(
                    crop_bytes, prefix="gate-captures-plates",
                    original_name=f"cam-{side}-{tag}-plate.jpg", content_type="image/jpeg")
            return info, info2

        info, info2 = await anyio.to_thread.run_sync(_put)

        rec1 = FileRecord(bucket=info["bucket"], object_key=info["object_key"],
                          original_name=f"cam-{side}-{tag}.jpg",
                          content_type="image/jpeg", size=info["size"],
                          checksum=info["checksum"])
        db.add(rec1)
        rec2 = None
        if info2 is not None:
            rec2 = FileRecord(bucket=info2["bucket"], object_key=info2["object_key"],
                              original_name=f"cam-{side}-{tag}-plate.jpg",
                              content_type="image/jpeg", size=info2["size"],
                              checksum=info2["checksum"])
            db.add(rec2)
        await db.flush()
        return rec1.id, (rec2.id if rec2 is not None else None)
    except Exception as exc:  # noqa: BLE001 — عکس حیاتی نیست؛ رویداد هست
        logger.warning(f"[camera:{side}] آپلود عکس رویداد ناموفق "
                       f"(رویداد بدون عکس ثبت می‌شود): {type(exc).__name__}: {exc}")
        return None, None


async def _record_review_event(side: str, gate_code: str, bgr, cand: dict) -> None:
    """پلاک قالب‌معتبرِ کم‌اطمینان → ردیف NEEDS_REVIEW با عکس (بدون تصمیم/راهبند).

    «هر ماشین که رد می‌شود» حتی اگر خوانش زیر آستانه باشد از جدول پلاک‌خوانی
    حذف نمی‌شود — اپراتور در صفحهٔ «بازبینی پلاک» عکس را می‌بیند و تأیید/اصلاح
    می‌کند. هیچ رویداد AccessEvent و هیچ فرمان راهبندی ساخته نمی‌شود.
    """
    st = _side_status(side)
    try:
        from sqlalchemy import select as _select
        from app.db.session import AsyncSessionLocal
        from app.modules.access_control.models import Gate, PlateRecognitionEvent
        from app.shared.plate import normalize_plate
        async with AsyncSessionLocal() as db:
            gate = (await db.execute(
                _select(Gate).where(Gate.code == gate_code))).scalar_one_or_none()
            if gate is None:
                logger.warning(f"[camera:{side}] دروازهٔ {gate_code} نیست — "
                               f"خوانش کم‌اطمینان فقط در آمار ماند")
                return
            full_id, plate_id = await _upload_event_images(db, side, bgr, cand)
            now = datetime.now(timezone.utc)
            db.add(PlateRecognitionEvent(
                gate_id=gate.id, direction=side,
                plate_raw=cand["system"],
                plate_normalized=normalize_plate(cand["system"]) or None,
                confidence=round(float(cand.get("confidence") or 0), 3),
                captured_at=now, received_at=now,
                source_event_id=f"cam-{uuid.uuid4()}",
                review_status="NEEDS_REVIEW",
                raw_payload={"side": side, "raw_read": cand.get("raw"),
                             "method": cand.get("method"),
                             "low_conf_review": True},
                full_image_file_id=full_id, plate_image_file_id=plate_id,
            ))
            await db.commit()
        st["review_events"] = int(st.get("review_events") or 0) + 1
        logger.info(f"[camera:{side}] plate={cand['system']} "
                    f"conf={cand.get('confidence')} کم‌اطمینان → "
                    f"NEEDS_REVIEW ذخیره شد (عکس: {bool(full_id)})")
    except Exception as exc:  # noqa: BLE001
        st["last_error"] = f"ثبت بازبینی ناموفق: {type(exc).__name__}: {exc}"
        logger.warning(f"[camera:{side}] review-event FAILED: {exc}")


async def _process_frame(side: str, gate_code: str, direction: str, bgr) -> None:
    st = _side_status(side)
    import anyio
    try:
        result = await anyio.to_thread.run_sync(_ocr_sync, bgr)
    except Exception as exc:  # noqa: BLE001
        st["last_error"] = f"خطای OCR: {type(exc).__name__}: {exc}"
        return
    st["last_ocr_ts"] = time.time()
    st["last_ocr_ms"] = result.get("elapsed_ms")
    st["frames_scanned"] = int(st.get("frames_scanned") or 0) + 1
    try:  # آخرین فریم بررسی‌شده — برای پاسخ به «چرا عکس/پلاکی ثبت نمی‌شود؟»
        out_dir = Path(settings.CAMERA_SNAPSHOT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_dir / f"cam-{side}-latest.jpg"), bgr,
                    [cv2.IMWRITE_JPEG_QUALITY, 80])
    except Exception:  # noqa: BLE001 — عیب‌یابی حیاتی نیست
        pass
    best = result.get("best") or {}
    plates = result.get("plates") or []
    if not plates:
        st["last_error"] = None
        return
    # کاندیداها به ترتیب رتبه — اولین «معتبرِ قالبی» بالای آستانه.
    #  valid=False یعنی متن OCR اصلاً قالب پلاک ایران نیست (خیال OCR) —
    #  هرگز رویداد گیت نمی‌سازد؛ این همان منشأ پلاک‌های از خوددراوده بود.
    chosen = None
    for item in plates:
        if (item.get("valid") and item.get("system")
                and item.get("confidence", 0) >= settings.CAMERA_MIN_CONF):
            chosen = item
            break
    if chosen is None:
        # آمار خوانش‌های ردشده — در poller-status برای عیب‌یابی دیده می‌شود
        skipped = next((p for p in plates if p.get("system") and p.get("valid")), None)
        if skipped:
            st["low_conf_skipped"] = int(st.get("low_conf_skipped") or 0) + 1
            st["last_skipped"] = {"system": skipped.get("system"),
                                  "confidence": skipped.get("confidence")}
        # پلاک قالب‌معتبرِ بین LOWCONF_MIN و آستانه → ردیف بازبینی با عکس —
        # هیچ تصمیمی/راهبندی ندارد؛ «هر ماشین ردشده» در جدول می‌ماند
        if settings.CAMERA_LOWCONF_REVIEW:
            cand = next((p for p in plates if p.get("valid") and p.get("system")
                         and p.get("confidence", 0) >= settings.CAMERA_LOWCONF_MIN), None)
            if cand:
                rkey = _norm_key(cand["system"])
                if rkey and _should_emit_review(rkey):
                    await _record_review_event(side, gate_code, bgr, cand)
        st["last_error"] = None
        return
    key = _norm_key(chosen["system"])
    if not key or not _should_emit(key):
        return
    _save_capture(side, bgr, chosen["system"])
    from app.db.session import AsyncSessionLocal
    from app.modules.camera.events import emit_plate_event
    try:
        async with AsyncSessionLocal() as db:
            # عکس کامل + برش پلاک → MinIO → وصل به ردیف رویداد
            full_id, plate_id = await _upload_event_images(db, side, bgr, chosen)
            res = await emit_plate_event(
                db,
                gate_code=gate_code,
                direction=direction,
                plate_raw=chosen["system"],
                confidence=round(float(chosen.get("confidence") or 0) * 100, 1),
                source="camera-poller",
                raw_payload={"side": side, "raw_read": chosen.get("raw"),
                             "persian": chosen.get("persian"),
                             "method": chosen.get("method")},
                full_image_file_id=full_id,
                plate_image_file_id=plate_id,
            )
            await db.commit()
        st["last_plate"] = chosen.get("system")
        st["last_plate_fa"] = chosen.get("persian")
        st["last_conf"] = chosen.get("confidence")
        st["events_sent"] = int(st.get("events_sent") or 0) + 1
        st["last_error"] = None
        logger.info(f"[camera:{side}] plate={chosen['system']} → "
                    f"{res.get('decision')} / {res.get('barrier_action')}")
    except Exception as exc:  # noqa: BLE001
        st["last_error"] = f"ثبت رویداد ناموفق: {type(exc).__name__}: {exc}"
        logger.warning(f"[camera:{side}] emit FAILED: {exc}")


# ---------------------------------------------------------------------------
# رهبری (workers>1 → فقط یک worker دوربین‌ها را می‌خواند)
# ---------------------------------------------------------------------------
_LEADER_KEY = "parkingsystem:camera-poller-leader"
_REDIS_STATUS_KEY = "parkingsystem:camera-poller-status"
_worker_id = str(uuid.uuid4())

# کلاینت پایدار Redis برای انتشار وضعیت رهبر (بازسازی در خطا + backoff ۳۰ ثانیه)
_status_redis = None
_status_redis_backoff = 0.0


def _get_status_redis():
    global _status_redis, _status_redis_backoff
    if _status_redis is not None:
        return _status_redis
    if time.monotonic() < _status_redis_backoff:
        return None                      # خطای اخیر — تا ۳۰ ثانیه دوباره تلاش نکن
    try:
        import redis.asyncio as aioredis
        _status_redis = aioredis.from_url(settings.REDIS_URL, socket_timeout=2)
        return _status_redis
    except Exception:  # noqa: BLE001
        _status_redis_backoff = time.monotonic() + 30
        return None


async def _publish_status() -> None:
    """رهبر وضعیت واقعی دوربین‌ها را در Redis می‌نویسد (TTL ۱۰ ثانیه).

    با uvicorn --workers 2 فقط workerِ رهبر گیرندهٔ دوربین را دارد؛ اگر
    درخواست poller-status به worker دیگر برسد، بدون این انتشار وضعیتِ
    محلیِ او همه‌جا «قطع/غیرفعال» نشان داده می‌شد — همان خطای
    «دوربین‌ها آنلاین نیستند» در پنل گیت.
    """
    global _status_redis, _status_redis_backoff
    r = _get_status_redis()
    if r is None:
        return
    try:
        await r.set(_REDIS_STATUS_KEY, json.dumps(status_snapshot()), ex=10)
    except Exception:  # noqa: BLE001 — Redis موقتاً در دسترس نیست؛ بی‌سرعت ادامه
        try:
            await r.aclose()
        except Exception:  # noqa: BLE001
            pass
        _status_redis = None
        _status_redis_backoff = time.monotonic() + 30


async def status_for_api() -> dict:
    """وضعیت برای API — اول وضعیت منتشرشدهٔ رهبر از Redis، بعد وضعیت محلی."""
    r = _get_status_redis()
    if r is not None:
        try:
            raw = await r.get(_REDIS_STATUS_KEY)
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict) and data.get("sides"):
                    data["source"] = "leader-redis"
                    return data
        except Exception:  # noqa: BLE001 — Redis در دسترس نیست؛ وضعیت محلی
            pass
    return status_snapshot()


async def _try_leader() -> bool:
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, socket_timeout=2)
        try:
            got = await r.set(_LEADER_KEY, _worker_id, nx=True, ex=15)
            if got:
                return True
            cur = await r.get(_LEADER_KEY)
            if cur and cur.decode() == _worker_id:
                await r.expire(_LEADER_KEY, 15)
                return True
            return False
        finally:
            await r.aclose()
    except Exception:  # noqa: BLE001 — نبود Redis: تک‌کارگر فرض می‌شود
        return True


# ---------------------------------------------------------------------------
# حلقهٔ اصلی
# ---------------------------------------------------------------------------
def _cfg_signature() -> str:
    cfg = cached_cfg()
    parts = []
    for side in SIDES:
        s = cfg.get(side) or {}
        parts.append(f"{side}:{'on' if s.get('enabled') else 'off'}:{s.get('rtsp', '')}:"
                     f"{s.get('gate_code', '')}:{s.get('direction', '')}")
    parts.append(f"iv={cfg.get('poll_interval')}")
    parts.append(f"ocr={cfg.get('ocr')}")
    return "|".join(parts)


def _rebuild_grabbers() -> None:
    global _cfg_sig
    cfg = cached_cfg()
    for side in SIDES:
        s = cfg.get(side) or {}
        old = _grabbers.get(side)
        want = bool(s.get("enabled") and s.get("rtsp"))
        if old and (not want or old.rtsp != s.get("rtsp")):
            old.stop()
            _grabbers.pop(side, None)
            st = _side_status(side)
            st.update({"connected": False, "has_frame": False})
        if not want:
            # لاگ «دلیل» — تا در docker logs معلوم باشد چرا این طرف بی‌کار است
            reason = ("آدرس دوربین ذخیره نشده" if not s.get("rtsp")
                      else "دوربین غیرفعال است (کلید «فعال» خاموش)")
            logger.info(f"[camera:{side}] غیرفعال — {reason}")
        if want and side not in _grabbers:
            g = FrameGrabber(side, s["rtsp"])
            g.start()
            _grabbers[side] = g
            st = _side_status(side)
            st["enabled"] = True
    _cfg_sig = _cfg_signature()


def gate_for(side: str, s: dict) -> tuple[str, str]:
    """(gate_code, direction) — پیش‌فرض: IN → GATE-IN-01/IN و OUT → GATE-OUT-01/OUT."""
    return (s.get("gate_code") or f"GATE-{side}-01",
            s.get("direction") or side)


async def _reload_cfg() -> None:
    """بارگیری پیکربندی دوربین‌ها از DB در همین worker.

    کش پیکربندی per-process است و PUT /config فقط کشِ workerِ پرس‌وشه‌شده
    را به‌روز می‌کند. با --workers 2 اگر workerِ رهبر هیچ‌وقت /camera/config
    یا /stream را پاسخ نداده باشد، کشش برای همیشه خالی می‌ماند ⇒
    cached_cfg() همه‌چیز را «غیرفعال» می‌بیند و poller بی‌صدا هیچ کاری
    نمی‌کند (عکس زنده از مسیر fallback می‌آید اما پلاک هیچ‌وقت خوانده
    نمی‌شود — بدون حتی یک خط لاگ). برای همین حلقه، پیکربندی را خودش
    هر ۱۵ ثانیه از DB تازه می‌کند.
    """
    from app.db.session import AsyncSessionLocal
    from app.modules.camera import config_store
    async with AsyncSessionLocal() as db:
        await config_store.refresh_config_cache(db)


async def poller_loop() -> None:
    logger.info("[camera-poller] حلقهٔ دوربین شروع شد")
    STATUS["running"] = True
    STATUS["started_at"] = time.time()
    STATUS["ocr_ready"] = HAS_CV2
    last_leader_check = 0.0
    last_hb = 0.0
    last_pub = 0.0
    last_cfg = 0.0
    # بار اول: پیکربندی باید در همین worker از DB بارگیری شود —
    # نبود آن یعنی poller بی‌صدا بی‌کار می‌ماند
    try:
        await _reload_cfg()
    except Exception as exc:  # noqa: BLE001 — حلقه هر ۱۵ ثانیه دوباره تلاش می‌کند
        logger.warning(f"[camera-poller] بارگیری اولیهٔ پیکربندی ناموفق: "
                       f"{type(exc).__name__}: {exc}")
    try:
        while True:
            try:
                now = time.monotonic()
                # پیکربندی هر ۱۵ ثانیه از DB — تغییر تنظیمات در UI (که شاید
                # در worker دیگر ذخیره شده باشد) حداکثر ۱۵ ثانیه بعد به
                # poller این worker هم می‌رسد
                if now - last_cfg > 15.0:
                    last_cfg = now
                    try:
                        await _reload_cfg()
                    except Exception as exc:  # noqa: BLE001 — خطا حلقه را نمی‌بندد
                        logger.warning(f"[camera-poller] بارگیری پیکربندی ناموفق: "
                                       f"{type(exc).__name__}: {exc}")
                if now - last_leader_check > 10:
                    STATUS["leader"] = await _try_leader()
                    last_leader_check = now
                # انتشار وضعیت در Redis — هر ۲ ثانیه (TTL ۱۰ ثانیه)؛ تا
                # poller-status روی هر workerی وضعیت واقعی رهبر را بدهد
                if STATUS["leader"] and (now - last_pub) > 2.0:
                    last_pub = now
                    await _publish_status()
                # ضربان هر ۵ دقیقه — در لاگ مشخص است که حلقه زنده است
                if now - last_hb > 300:
                    last_hb = now
                    for hb_side in SIDES:
                        hb_st = STATUS["sides"].get(hb_side) or {}
                        if not hb_st.get("enabled"):
                            continue
                        hb_g = _grabbers.get(hb_side)
                        logger.info(f"[camera:{hb_side}] heartbeat "
                                    f"connected={getattr(hb_g, 'connected', None)} "
                                    f"reconnects={getattr(hb_g, 'reconnects', 0)} "
                                    f"last_plate={hb_st.get('last_plate')} "
                                    f"conf={hb_st.get('last_conf')} "
                                    f"events={hb_st.get('events_sent')} "
                                    f"low_conf_skipped={hb_st.get('low_conf_skipped', 0)}")
                if not STATUS["leader"]:
                    await asyncio.sleep(5)
                    continue

                sig = _cfg_signature()
                if sig != _cfg_sig:
                    _rebuild_grabbers()

                cfg = cached_cfg()
                interval = float(cfg.get("poll_interval") or settings.CAMERA_POLL_INTERVAL)
                for side in SIDES:
                    s = cfg.get(side) or {}
                    st = _side_status(side)
                    st["enabled"] = bool(s.get("enabled") and s.get("rtsp"))
                    if not st["enabled"]:
                        continue
                    g = _grabbers.get(side)
                    if g is None:
                        continue
                    frame, ts = g.latest()
                    if frame is None:
                        continue
                    # فقط فریم تازه (۱.۵×فاصلهٔ poll)
                    if ts and (time.time() - ts) > max(15.0, interval * 1.5):
                        continue
                    last_ocr = st.get("last_ocr_ts") or 0
                    if (time.time() - last_ocr) < interval:
                        continue
                    if cfg.get("ocr", True) and HAS_CV2:
                        gate_code, direction = gate_for(side, s)
                        await _process_frame(side, gate_code, direction, frame)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — هیچ خطایی حلقه را نمی‌بندد
                logger.warning(f"[camera-poller] loop error (retry in 5s): "
                               f"{type(exc).__name__}: {exc}")
                await asyncio.sleep(5)
                continue
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        logger.info("[camera-poller] متوقف شد")
        raise
    finally:
        STATUS["running"] = False
        STATUS["leader"] = False


def start() -> asyncio.Task | None:
    """شروع حلقه در lifespan — بدون cv2 یا با CAMERA_POLL_ENABLED=False بی‌اثر."""
    global _task
    if _task is not None and not _task.done():
        return _task
    if not settings.CAMERA_POLL_ENABLED:
        logger.info("[camera-poller] غیرفعال (CAMERA_POLL_ENABLED=false)")
        return None
    if not HAS_CV2:
        logger.info("[camera-poller] غیرفعال — opencv نصب نیست (INSTALL_OCR=true لازم است)")
        return None
    _task = asyncio.get_running_loop().create_task(poller_loop())
    return _task


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    for g in list(_grabbers.values()):
        g.stop()
    _grabbers.clear()
