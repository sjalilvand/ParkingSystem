"""موج ۷a — دوربین: snapshot از RTSP با کش، استفاده در پنل گیت."""
import asyncio
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Header
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.config_admin.models import AppSetting
from app.modules.identity.models import User

router = APIRouter(prefix="/camera", tags=["Camera"])

SNAPSHOT_TTL = 2.0          # ثانیه — کش برای جلوگیری از باز کردن مکرر RTSP
FFMPEG_CANDIDATES = [
    Path("E:/ParkingSystem/tools/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe"),
]

_cache: dict = {}  # side -> {"path": ..., "ts": ...}


def _ffmpeg_exe() -> str:
    for c in FFMPEG_CANDIDATES:
        if c.exists():
            return str(c)
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise NotFoundError("ffmpeg پیدا نشد — tools/ffmpeg را نصب کنید")


def _cameras_cfg() -> dict:
    import json
    # از تنظیمات نسخه‌بندی‌شده بخوان (طراح)
    return _read_cameras_sync()


def _read_cameras_sync() -> dict:
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # در context async — از کِش تنظیمات استفاده کن
            return _cfg_cache
    except RuntimeError:
        pass
    return _cfg_cache


_cfg_cache: dict = {}


async def load_cameras_cache(db: AsyncSession):
    """کنگرهٔ تنظیمات دوربین — در startup و بعد از تغییر، refresh می‌شود."""
    from sqlalchemy import select
    row = (await db.execute(select(AppSetting).where(AppSetting.key == "cameras"))).scalar_one_or_none()
    if row and isinstance(row.value, dict):
        _cfg_cache.update(row.value)


@router.get("/snapshot/{side}")
async def snapshot(side: str, db: AsyncSession = Depends(get_db),
                   x_api_key: str = Header(default=None, alias="X-API-Key"),
                   authorization: str = Header(default=None, alias="Authorization"),
                   api_key: str = None):
    """احراز: X-API-Key (برای img tag) یا Bearer token."""
    import secrets as _secrets
    api_key_ok = x_api_key and _secrets.compare_digest(x_api_key, settings.GATE_API_KEY)
    if not api_key_ok and api_key:
        api_key_ok = _secrets.compare_digest(api_key, settings.GATE_API_KEY)
    if not api_key_ok:
        if not (authorization and authorization.startswith("Bearer ")):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="camera auth failed")
        from app.core.security import decode_token
        try:
            decode_token(authorization.replace("Bearer ", ""))
        except Exception:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="invalid token")
    """فریم لحظه‌ای دوربین (JPEG) — با کش TTL دو ثانیه."""
    side = side.upper()
    if side not in ("IN", "OUT"):
        raise NotFoundError("side باید IN یا OUT باشد")
    if not _cfg_cache:
        await load_cameras_cache(db)

    cam = _cfg_cache.get(side)
    if not cam:
        raise NotFoundError(f"دوربین {side} پیکربندی نشده است")

    # کش
    now = time.time()
    cached = _cache.get(side)
    if cached and (now - cached["ts"]) < SNAPSHOT_TTL:
        return FileResponse(cached["path"], media_type="image/jpeg")

    out = Path(f"E:/ParkingSystem/logs/cam-{side}.jpg")
    rtsp = cam.get("rtsp")
    ff = _ffmpeg_exe()
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
    if proc.returncode != 0 or not out.exists() or out.stat().st_size < 3000:
        raise NotFoundError(f"دوربین {side} در دسترس نیست: {stderr.decode(errors='replace')[:200]}")

    _cache[side] = {"path": str(out), "ts": now}
    return FileResponse(str(out), media_type="image/jpeg")
