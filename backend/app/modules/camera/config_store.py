"""پیکربندی دوربین‌های گیت — ذخیره در AppSetting «cameras» (نسخه‌بندی‌شده).

قالب ذخیره:
{
  "IN":  {"rtsp": "rtsp://user:pass@ip:554/...", "enabled": true, "name": "ورود"},
  "OUT": {"rtsp": "rtsp://...",                  "enabled": false, "name": "خروج"},
  "poll_interval": 10,        # ثانیه — فاصلهٔ OCR خودکار (اختیاری)
  "ocr": true                 # خواندن پلاک خودکار از فریم دوربین (اختیاری)
}

سازگاری با نسخهٔ قبلی: اگر مقدار هر طرف رشتهٔ ساده (URL) باشد به شکل
{"rtsp": <str>, "enabled": true} نرمال‌سازی می‌شود.
"""
from __future__ import annotations

import asyncio
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

CAMERAS_KEY = "cameras"
SIDES = ("IN", "OUT")

# ---------------------------------------------------------------------------
# پیش‌فرض گیت (سناریو B) — اگر DB هیچ آدرسی نداشته باشد خودکار seed می‌شود.
# این همان ریشهٔ «دوربین تنظیم نشده / هیچ اتفاقی نمی‌افتد» است: کش خالی یعنی
# poller بی‌صدا بی‌کار می‌ماند و پنل گیت همیشه placeholder نشان می‌دهد.
# فقط وقتی seed می‌شود که «هیچ» URL‌ای ذخیره نباشد؛ enabled=false عمدیِ کاربر
# و URLهای دستیِ او هرگز بازنویسی نمی‌شوند.
# ---------------------------------------------------------------------------
DEFAULT_SEED: dict = {
    "IN": {
        "rtsp": "http://admin:admin@192.168.100.230/jpgimage/1/image.jpg",
        "enabled": True, "name": "دوربین ورود",
        "gate_code": "GATE-IN-01", "direction": "IN",
    },
    "OUT": {
        "rtsp": "http://admin:admin@192.168.100.231/jpgimage/1/image.jpg",
        "enabled": True, "name": "دوربین خروج",
        "gate_code": "GATE-OUT-01", "direction": "OUT",
    },
    "poll_interval": 10.0,
    "ocr": True,
}

_seeded_once = False   # در عمر هر فرآیند فقط یک‌بار تلاش کن (ارزان نگه‌داشتن reload)

# کش در-پروسس — با refresh_config_cache پر می‌شود (استارتاپ + بعد از PUT)
_cfg_cache: dict = {}
_cfg_ts: float = 0.0


def fix_rtsp_typo(url: str) -> str:
    """اصلاح خودکار غلط رایج: main_av_stream → main/av_stream (زیرخط به‌جای اسلش).

    مسیر درست دوربین‌های HiSilicon/شهاب «/h264/ch1/main/av_stream» است؛
    نسخهٔ زیرخط‌دار هرگز باز نمی‌شود و دوربین «کاملاً قطع» به نظر می‌رسد.
    """
    return (url or "").replace("_av_stream", "/av_stream").strip()


def _normalize_side(raw) -> dict:
    """نسخهٔ قدیمی (رشته) و نسخهٔ جدید (دیکشنری) هر دو پذیرفته می‌شوند."""
    if isinstance(raw, str):
        rtsp = fix_rtsp_typo(raw.strip())
        return {"rtsp": rtsp, "enabled": bool(rtsp), "name": ""}
    if isinstance(raw, dict):
        rtsp = fix_rtsp_typo(str(raw.get("rtsp") or "").strip())
        return {
            "rtsp": rtsp,
            "enabled": bool(raw.get("enabled", bool(rtsp))),
            "name": str(raw.get("name") or ""),
            "gate_code": str(raw.get("gate_code") or "").strip(),
            "direction": str(raw.get("direction") or "").strip().upper(),
        }
    return {"rtsp": "", "enabled": False, "name": ""}


def normalize_cfg(raw: dict | None) -> dict:
    """قالب یکسان برای router/poller — همیشه کلیدهای IN/OUT/poll_interval/ocr."""
    raw = raw if isinstance(raw, dict) else {}
    out: dict = {}
    for side in SIDES:
        s = _normalize_side(raw.get(side))
        out[side] = s
    try:
        interval = float(raw.get("poll_interval") or settings.CAMERA_POLL_INTERVAL)
    except (TypeError, ValueError):
        interval = settings.CAMERA_POLL_INTERVAL
    out["poll_interval"] = max(3.0, min(120.0, interval))
    out["ocr"] = bool(raw.get("ocr", True))
    return out


async def load_cameras(db: AsyncSession) -> dict:
    """خواندن پیکربندی دوربین‌ها از DB (بدون کش)."""
    from app.modules.config_admin.models import AppSetting

    row = (await db.execute(
        select(AppSetting).where(AppSetting.key == CAMERAS_KEY)
    )).scalar_one_or_none()
    return normalize_cfg(row.value if row and isinstance(row.value, dict) else None)


async def refresh_config_cache(db: AsyncSession) -> dict:
    """کش در-پروسس را به‌روز می‌کند (استارتاپ و بعد از ذخیرهٔ تنظیمات)."""
    global _cfg_cache, _cfg_ts
    _cfg_cache.clear()
    _cfg_cache.update(await load_cameras(db))
    _cfg_ts = time.time()
    return dict(_cfg_cache)


async def ensure_default_seeded(db: AsyncSession) -> bool:
    """اگر DB هیچ آدرس دوربینی نداشته باشد، پیش‌فرض‌های گیت seed می‌شود.

    در استارتاپ (lifespan) صدا زده می‌شود؛ idempotent است — چند worker همزمان
    هم فقط همان مقدار یکسان را می‌نویسند. خروجی: آیا seed انجام شد؟
    """
    global _seeded_once
    from loguru import logger

    from app.modules.config_admin.models import AppSetting

    if _seeded_once:
        return False
    try:
        row = (await db.execute(
            select(AppSetting).where(AppSetting.key == CAMERAS_KEY)
        )).scalar_one_or_none()
        raw = row.value if row and isinstance(row.value, dict) else {}
        has_any_url = any(
            str((raw.get(side) or {}).get("rtsp") or "").strip()
            for side in SIDES
        )
        if has_any_url:
            _seeded_once = True          # پیکربندی کاربر هست — دست نمی‌زنیم
            return False
        norm = normalize_cfg(DEFAULT_SEED)
        if row is None:
            db.add(AppSetting(key=CAMERAS_KEY, value=norm))
        else:
            row.value = norm
        await db.commit()
        _seeded_once = True
        logger.info("[camera-config] DB خالی بود → پیش‌فرض‌های گیت seed شد "
                    "(IN: 192.168.100.230 / OUT: 192.168.100.231 — شهاب HTTP snapshot)")
        return True
    except Exception as exc:  # noqa: BLE001 — seed هرگز بوت را نبندد
        # تداخل دو worker روی unique key هم اینجا می‌افتد — بی‌خطر است
        logger.warning(f"[camera-config] seed پیش‌فرض دوربین‌ها ناموفق: "
                       f"{type(exc).__name__}: {exc}")
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


def cached_cfg() -> dict:
    """کش فعلی — اگر خالی باشد normalize پایه برمی‌گردد."""
    if not _cfg_cache:
        return normalize_cfg(None)
    return dict(_cfg_cache)


def mask_rtsp(url: str) -> str:
    """پنهان‌سازی رمز در URL برای نمایش در UI (rtsp://user:***@ip)."""
    import re
    return re.sub(r"(://[^:/@]+:)([^@]+)(@)", r"\1***\3", url or "")


def public_cfg(cfg: dict | None = None) -> dict:
    """نسخهٔ قابل‌نمایش (رمز دوربین mask می‌شود)."""
    cfg = cfg or cached_cfg()
    out = {"poll_interval": cfg.get("poll_interval"), "ocr": cfg.get("ocr"), "sides": {}}
    for side in SIDES:
        s = dict(cfg.get(side) or {})
        s["rtsp"] = mask_rtsp(s.get("rtsp") or "")
        out["sides"][side] = s
    return out
