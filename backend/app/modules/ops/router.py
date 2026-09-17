"""مرکز عملیات: وضعیت زنده، لاگ‌ها، تنظیمات vision (admin)."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.access_control.models import AccessEvent
from app.modules.devices.models import Device, Gate
from app.modules.identity.models import User

router = APIRouter(prefix="/ops", tags=["Ops"])

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
LOG_DIR = _PROJECT_ROOT / "logs"
AGENT_ENV = _PROJECT_ROOT / "gate-agent" / ".env"

ALLOWED_LOGS = {"backend", "frontend", "agent", "vision", "autostart"}
CONFIG_KEYS = ["GATE_CODE", "DEFAULT_DIRECTION", "ANPR_PORT", "WEBCAM_INDEX",
               "RTSP_URL", "SCAN_INTERVAL", "PRC_API_TOKEN", "RTSP_GATE_CODE", "RTSP_DIRECTION"]
WRITABLE_KEYS = {"DEFAULT_DIRECTION", "ANPR_PORT", "WEBCAM_INDEX", "RTSP_URL",
                 "SCAN_INTERVAL", "PRC_API_TOKEN", "RTSP_GATE_CODE", "RTSP_DIRECTION"}
SECRET_KEYS = {"PRC_API_TOKEN", "RTSP_URL"}


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    gates = (await db.execute(select(Gate))).scalars().all()
    devices = (await db.execute(select(Device))).scalars().all()
    out = []
    for g in gates:
        seen = _aware(g.last_seen_at)
        online = bool(seen and (now - seen).total_seconds() < 120)
        out.append({"code": g.code, "name": g.name, "direction": g.direction,
                    "status": g.status, "last_seen_at": seen.isoformat() if seen else None,
                    "online": online})
    hour_ago = now - timedelta(hours=1)
    rows = (await db.execute(
        select(AccessEvent.decision, func.count())
        .where(AccessEvent.event_time >= hour_ago)
        .group_by(AccessEvent.decision))).all()
    by_decision = {d or "-": n for d, n in rows}
    return {"server_time": now.isoformat(), "db": True,
            "gates": out, "devices": len(devices),
            "events_last_hour": {"total": sum(by_decision.values()), "by_decision": by_decision}}


@router.get("/logs")
async def logs(name: str = "vision", lines: int = 200, user: User = Depends(get_current_user)):
    if name not in ALLOWED_LOGS:
        raise NotFoundError("نام لاگ مجاز نیست")
    p = LOG_DIR / "{}.log".format(name)
    if not p.exists():
        return {"name": name, "exists": False, "lines": []}
    data = p.read_text(encoding="utf-8", errors="replace").splitlines()
    n = max(10, min(lines, 500))
    return {"name": name, "exists": True, "lines": data[-n:]}


def _read_env_map():
    out = {}
    if AGENT_ENV.exists():
        for line in AGENT_ENV.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


@router.get("/config")
async def get_config(user: User = Depends(get_current_user)):
    env = _read_env_map()
    items = []
    for k in CONFIG_KEYS:
        v = env.get(k, "")
        if k in SECRET_KEYS and v:
            v = v[:4] + "..." + v[-4:] if len(v) > 10 else "***"
        items.append({"key": k, "value": v, "writable": k in WRITABLE_KEYS})
    return {"items": items, "env_path": str(AGENT_ENV)}


class ConfigUpdate(BaseModel):
    updates: dict[str, str]


@router.post("/config")
async def set_config(body: ConfigUpdate, user: User = Depends(get_current_user)):
    lines = AGENT_ENV.read_text(encoding="utf-8-sig").splitlines() if AGENT_ENV.exists() else []
    changed = []
    for k, v in body.updates.items():
        if k not in WRITABLE_KEYS or "..." in v or v is None:
            continue
        v = str(v).strip()
        found = False
        for i, ln in enumerate(lines):
            if ln.strip().startswith(k + "="):
                lines[i] = "{}={}".format(k, v)
                found = True
                break
        if not found:
            lines.append("{}={}".format(k, v))
        changed.append(k)
    if changed:
        AGENT_ENV.parent.mkdir(parents=True, exist_ok=True)
        AGENT_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"success": True, "changed": changed,
            "note": "برای اعمال، پروسه‌های vision_bridge مربوطه را ری‌استارت کنید"}