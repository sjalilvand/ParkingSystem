"""مرکز عملیات: وضعیت زنده، لاگ‌ها، تنظیمات vision — فقط ادمین (user.manage)."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.permissions import require_permission
from app.db.session import get_db
from app.modules.access_control.models import AccessEvent
from app.modules.devices.models import Device, Gate
from app.modules.identity.models import User

router = APIRouter(prefix="/ops", tags=["Ops"])

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
LOG_DIR = _PROJECT_ROOT / "logs"
AGENT_ENV = _PROJECT_ROOT / "gate-agent" / ".env"

ALLOWED_LOGS = {"backend", "frontend", "agent", "vision", "autostart", "anpr"}
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
async def status(db: AsyncSession = Depends(get_db),
                 user: User = Depends(require_permission("user.manage"))):
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
async def logs(name: str = "vision", lines: int = 200,
               user: User = Depends(require_permission("user.manage"))):
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
async def get_config(user: User = Depends(require_permission("user.manage"))):
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
async def set_config(body: ConfigUpdate,
                     user: User = Depends(require_permission("user.manage"))):
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

# ---------------- جریمه‌ها ----------------

class FineCreate(BaseModel):
    plate_raw: str
    amount: int = 500000
    reason: str | None = None
    violation_type: str = "MANUAL"


@router.post("/fine")
async def create_fine(body: FineCreate, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_permission("user.manage"))):
    """INTROSPECTIVE_FINE — فقط ستون‌های موجود + پرکردن الزامی‌ها."""
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz

    from app.modules.notifications.service import push_notification
    from app.modules.violations.models import Violation
    from app.modules.vehicles.models import Vehicle
    from app.shared.plate import normalize_plate

    norm = normalize_plate(body.plate_raw) or body.plate_raw
    cols = {c.name: c for c in Violation.__table__.columns}
    data = {"plate_normalized": norm}
    for alt, val in (("plate_raw", body.plate_raw), ("violation_type", body.violation_type),
                     ("type", body.violation_type), ("amount", body.amount),
                     ("fine_amount", body.amount), ("reason", body.reason),
                     ("description", body.reason), ("status", "ACTIVE")):
        if alt in cols:
            data[alt] = val

    # vehicle_id اگر الزام‌آور بود، با خودروی واقعی پر شود
    if "vehicle_id" in cols and "vehicle_id" not in data:
        v = (await db.execute(select(Vehicle).where(
            Vehicle.plate_normalized == norm))).scalars().first()
        if v:
            data["vehicle_id"] = v.id

    # هر ستون NOT-NULL بدون default که هنوز خالی است، مقدار منطقی بگیرد
    for name, col in cols.items():
        if name in data or name in ("id", "created_at", "updated_at"):
            continue
        if col.nullable or col.default is not None or col.server_default is not None:
            continue
        try:
            pt = col.type.python_type
        except Exception:
            pt = str
        if name.endswith("_id"):
            data[name] = user.id if user and name in ("created_by", "reported_by", "recorded_by", "operator_id") else None
            if data[name] is None:
                data[name] = None
        elif pt is int:
            data[name] = 0
        elif pt is bool:
            data[name] = False
        elif pt is _dt:
            data[name] = _dt.now(_tz.utc)
        else:
            data[name] = _uuid.uuid4().hex[:12]

    obj = Violation(**{k: v for k, v in data.items() if k in cols})
    db.add(obj)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        import traceback
        traceback.print_exc()
        raise
    await db.refresh(obj)
    try:
        await push_notification(db, recipient_user_id=None,
                                title="FINE ISSUED",
                                message="plate {} amount {}".format(norm, body.amount),
                                payload={"violation_id": obj.id, "plate": norm, "amount": body.amount})
    except Exception:
        pass
    return {"success": True, "id": obj.id, "plate": norm, "amount": body.amount}



@router.get("/fines")
async def list_fines(limit: int = 20, db: AsyncSession = Depends(get_db),
                     user: User = Depends(require_permission("user.manage"))):
    from app.modules.violations.models import Violation
    rows = (await db.execute(
        select(Violation).order_by(Violation.created_at.desc()).limit(limit))).scalars().all()
    items = []
    for r in rows:
        d = {}
        for c in Violation.__table__.columns:
            val = getattr(r, c.name)
            d[c.name] = val.isoformat() if hasattr(val, "isoformat") else val
        items.append(d)
    return {"items": items}

@router.get("/gate-key")
async def get_gate_key(user: User = Depends(require_permission("user.manage"))):
    from app.core.config import settings

    return {"key": settings.GATE_API_KEY}
