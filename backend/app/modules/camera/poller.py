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
import threading
import time
import uuid
from pathlib import Path

from loguru import logger

from app.core.config import settings

try:  # وابستگی‌های OCR اختیاری‌اند
    import cv2
    HAS_CV2 = True
except ImportError:  # pragma: no cover
    cv2 = None
    HAS_CV2 = False

from app.modules.camera.config_store import SIDES, cached_cfg

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

_last_emit: dict[str, float] = {}   # dedupe: کلید پلاک نرمال → زمان آخرین ارسال


# ---------------------------------------------------------------------------
# گیرندهٔ فریم — اتصال پایدار RTSP در thread جدا
# ---------------------------------------------------------------------------
class FrameGrabber(threading.Thread):
    def __init__(self, side: str, rtsp: str):
        super().__init__(daemon=True, name=f"cam-{side}")
        self.side = side
        self.rtsp = rtsp
        self._frame = None
        self._ts = 0.0
        self.connected = False
        self.reconnects = 0
        self._stop_evt = threading.Event()

    def run(self) -> None:  # noqa: C901 — حلقهٔ مقاوم
        cap = None
        fails = 0
        while not self._stop_evt.is_set():
            if cap is None:
                try:
                    cap = cv2.VideoCapture(self.rtsp, cv2.CAP_FFMPEG)
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
                    cap.release()
                    cap = None
                    self._stop_evt.wait(4.0)
                    continue
                self.connected = True
                fails = 0
                logger.info(f"[camera:{self.side}] RTSP متصل شد")
            ok, frame = cap.read()
            if not ok:
                self.connected = False
                fails += 1
                self._set_error("خواندن فریم قطع شد — اتصال دوباره…")
                if fails >= 3:
                    cap.release()
                    cap = None
                    self.reconnects += 1
                self._stop_evt.wait(1.0)
                continue
            fails = 0
            with _frame_lock:
                self._frame = frame
                self._ts = time.time()

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
    best = result.get("best") or {}
    plates = result.get("plates") or []
    if not plates:
        st["last_error"] = None
        return
    # کاندیداها به ترتیب رتبه — اولین معتبرِ بالای آستانه
    chosen = None
    for item in plates:
        if item.get("system") and item.get("confidence", 0) >= settings.CAMERA_MIN_CONF:
            chosen = item
            break
    if chosen is None:
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
_worker_id = str(uuid.uuid4())


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


async def poller_loop() -> None:
    logger.info("[camera-poller] حلقهٔ دوربین شروع شد")
    STATUS["running"] = True
    STATUS["started_at"] = time.time()
    STATUS["ocr_ready"] = HAS_CV2
    last_leader_check = 0.0
    try:
        while True:
            try:
                now = time.monotonic()
                if now - last_leader_check > 10:
                    STATUS["leader"] = await _try_leader()
                    last_leader_check = now
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
