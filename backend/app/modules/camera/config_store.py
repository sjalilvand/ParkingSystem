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

# کش در-پروسس — با refresh_config_cache پر می‌شود (استارتاپ + بعد از PUT)
_cfg_cache: dict = {}
_cfg_ts: float = 0.0


def _normalize_side(raw) -> dict:
    """نسخهٔ قدیمی (رشته) و نسخهٔ جدید (دیکشنری) هر دو پذیرفته می‌شوند."""
    if isinstance(raw, str):
        return {"rtsp": raw.strip(), "enabled": bool(raw.strip()), "name": ""}
    if isinstance(raw, dict):
        rtsp = str(raw.get("rtsp") or "").strip()
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
