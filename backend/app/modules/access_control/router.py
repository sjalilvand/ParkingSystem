import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.audit import write_audit
from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.modules.access_control.models import AccessEvent
from app.modules.access_control.schemas import (
    BarrierOpenRequest,
    HeartbeatRequest,
    ManualAccessRequest,
    PlateDetectedRequest,
    SyncRequest,
)
from app.modules.access_control.service import GateDecisionService
from app.modules.devices.models import Device, Gate
from app.modules.identity.models import User
from app.modules.vehicles.models import AccessPermit, VehicleRestriction
from app.realtime.manager import manager

router = APIRouter(prefix="/gate", tags=["Gate"])
bearer_scheme = HTTPBearer(auto_error=False)


async def require_gate_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    """احراز هویت گیت: کلید دستگاه (X-API-Key) یا توکن کاربر."""
    if x_api_key == settings.GATE_API_KEY:
        return None
    if credentials is not None:
        try:
            payload = decode_token(credentials.credentials)
            if payload.get("type") == "access":
                return payload.get("sub")
        except Exception:
            pass
    raise HTTPException(status_code=401, detail="GATE_AUTH_FAILED")


_NOTIFY_DECISIONS = {"DENY", "UNKNOWN_PLATE", "REQUIRE_OPERATOR_APPROVAL", "OFFLINE_REQUIRE_REVIEW"}

_DECISION_TITLE = {
    "DENY": "🚫 تردد ممنوع",
    "UNKNOWN_PLATE": "❓ پلاک ناشناس در گیت",
    "REQUIRE_OPERATOR_APPROVAL": "⏳ نیاز به تأیید اپراتور",
    "OFFLINE_REQUIRE_REVIEW": "🔍 نیازمند بررسی (آفلاین)",
}

_REASON_FA = {
    "VEHICLE_NOT_REGISTERED": "خودرو در سیستم ثبت نشده است",
    "VEHICLE_INACTIVE": "خودرو غیرفعال است",
    "PLATE_NOT_READABLE": "پلاک قابل خواندن نیست",
    "PLATE_RESTRICTED": "پلاک محدود/ممنوع است",
    "NO_ACTIVE_PERMIT": "مجوز فعالی یافت نشد",
    "PERMIT_NOT_FOUND": "مجوزی یافت نشد",
    "PERMIT_EXPIRED": "اعتبار مجوز به پایان رسیده است",
    "SESSION_ALREADY_OPEN": "جلسه پارکینگ از قبل باز است",
    "DUPLICATE_ENTRY_SESSION_OPEN": "ورود تکراری",
    "NO_OPEN_SESSION_FOR_EXIT": "جلسه بازی برای خروج یافت نشد",
    "UNKNOWN_PLATE": "پلاک ناشناس",
}


async def _notify_gate_decision(db, gate_code: str, plate_raw: str, result: dict) -> None:
    """اعلان زنده برای اپراتورها روی تصمیم‌های حساس گیت."""
    try:
        decision = result.get("decision")
        if decision not in _NOTIFY_DECISIONS or result.get("duplicate"):
            return
        from app.modules.notifications.service import push_notification
        reason = result.get("decision_reason") or ""
        await push_notification(
            db,
            recipient_user_id=None,
            title="{} — گیت {}".format(_DECISION_TITLE.get(decision, decision), gate_code),
            message="پلاک: {} | دلیل: {}".format(
                plate_raw, _REASON_FA.get(reason, reason)),
            payload={"decision": decision, "reason": reason, "gate_code": gate_code,
                     "access_event_id": result.get("access_event_id")},
        )
    except Exception:
        pass


@router.post("/events/plate-detected")
async def plate_detected(body: PlateDetectedRequest, db: AsyncSession = Depends(get_db), _: object = Depends(require_gate_key)):
    try:
        result = await GateDecisionService.process_plate_event(
            db,
            gate_code=body.gate_code,
            direction=body.direction,
            plate_raw=body.plate_raw,
            source_event_id=body.source_event_id,
            device_id=body.device_id,
            captured_at=body.captured_at,
            confidence=body.confidence,
            raw_payload=body.raw_payload,
            client_decision=body.client_decision,
        )
        await _notify_gate_decision(db, body.gate_code, body.plate_raw, result)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/access/check")
async def access_check(body: PlateDetectedRequest, db: AsyncSession = Depends(get_db), _: object = Depends(require_gate_key)):
    try:
        return await GateDecisionService.process_plate_event(
            db,
            gate_code=body.gate_code, direction=body.direction, plate_raw=body.plate_raw,
            source_event_id=body.source_event_id, device_id=body.device_id,
            captured_at=body.captured_at, confidence=body.confidence,
            dry_run=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/access/manual")
async def access_manual(body: ManualAccessRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    direction = "IN" if "ENTRY" in body.event_type else "OUT"
    try:
        return await GateDecisionService.process_plate_event(
            db,
            gate_code=body.gate_code, direction=direction, plate_raw=body.plate_raw,
            source_event_id=f"manual-{int(time.time() * 1000)}",
            is_manual=True, operator_id=user.id if user else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/barrier/open")
async def barrier_open(body: BarrierOpenRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    gate = (await db.execute(select(Gate).where(Gate.code == body.gate_code))).scalar_one_or_none()
    if not gate:
        raise HTTPException(status_code=404, detail="GATE_NOT_FOUND")

    event = AccessEvent(
        gate_id=gate.id, plate_normalized=None, event_type="BARRIER_OPEN",
        event_time=datetime.now(timezone.utc), decision="ALLOW",
        decision_reason=body.reason, operator_id=user.id if user else None,
        is_manual=True, idempotency_key=f"barrier-{gate.id}-{int(time.time() * 1000)}",
    )
    db.add(event)
    if user:
        await write_audit(db, user_id=user.id, action="BARRIER_MANUAL_OPEN", module="gate",
                          entity_type="gate", entity_id=gate.id, reason=body.reason)
    await db.commit()

    await manager.broadcast("barrier.open_request", {"gate_code": gate.code, "reason": body.reason, "access_event_id": event.id})
    return {"success": True, "command_id": event.id, "barrier_action": "OPEN"}


@router.post("/barrier/result")
async def barrier_result(body: dict, _: object = Depends(require_gate_key)):
    await manager.broadcast("barrier.result", body)
    return {"success": True}


@router.post("/heartbeat")
async def heartbeat(body: HeartbeatRequest, db: AsyncSession = Depends(get_db), _: object = Depends(require_gate_key)):
    gate = (await db.execute(select(Gate).where(Gate.code == body.gate_code))).scalar_one_or_none()
    if not gate:
        raise HTTPException(status_code=404, detail="GATE_NOT_FOUND")
    gate.status = "ONLINE"
    gate.last_seen_at = datetime.now(timezone.utc)
    gate.agent_version = body.agent_version
    devices = (await db.execute(select(Device).where(Device.gate_id == gate.id))).scalars().all()
    for d in devices:
        ok = {"CAMERA": body.camera_ok, "BARRIER": body.barrier_ok, "PRINTER": body.printer_ok}.get(d.device_type)
        if ok is not None:
            d.status = "ONLINE" if ok else "ERROR"
            d.last_seen_at = gate.last_seen_at
    await db.commit()
    return {"success": True, "server_time": gate.last_seen_at.isoformat(), "snapshot_interval_min": 5}


@router.post("/sync")
async def sync_offline(body: SyncRequest, db: AsyncSession = Depends(get_db), _: object = Depends(require_gate_key)):
    results = []
    ordered = sorted(body.events, key=lambda e: e.captured_at or datetime.now(timezone.utc))
    for ev in ordered:
        try:
            resp = await GateDecisionService.process_plate_event(
                db,
                gate_code=ev.gate_code, direction=ev.direction, plate_raw=ev.plate_raw,
                source_event_id=ev.source_event_id, device_id=ev.device_id,
                captured_at=ev.captured_at, confidence=ev.confidence,
                raw_payload=ev.raw_payload, offline_created=True,
                client_decision=ev.client_decision,
            )
            results.append({"source_event_id": ev.source_event_id, "decision": resp["decision"],
                            "needs_review": resp.get("needs_review", False), "duplicate": resp.get("duplicate", False)})
        except Exception as exc:
            results.append({"source_event_id": ev.source_event_id, "error": str(exc)})
    return {"success": True, "results": results}


@router.get("/offline-snapshot")
async def offline_snapshot(gate_code: str, db: AsyncSession = Depends(get_db), _: object = Depends(require_gate_key)):
    gate = (await db.execute(select(Gate).where(Gate.code == gate_code))).scalar_one_or_none()
    if not gate:
        raise HTTPException(status_code=404, detail="GATE_NOT_FOUND")
    now = datetime.now(timezone.utc)

    permits = (await db.execute(select(AccessPermit).where(AccessPermit.status == "ACTIVE"))).scalars().all()
    allowed_plates = []
    for p in permits:
        if p.valid_until and p.valid_until < now:
            continue
        if p.allowed_gate_ids:
            try:
                if gate.id not in json.loads(p.allowed_gate_ids):
                    continue
            except Exception:
                pass
        allowed_plates.append({
            "plate": p.plate_normalized, "permit_id": p.id, "permit_type": p.permit_type,
            "valid_until": p.valid_until.isoformat() if p.valid_until else None,
            "max_entries": p.max_entries, "used_entries": p.used_entries,
        })

    restrictions = (await db.execute(select(VehicleRestriction).where(VehicleRestriction.status == "ACTIVE"))).scalars().all()
    restricted_plates = []
    for r in restrictions:
        if r.ends_at and r.ends_at < now:
            continue
        restricted_plates.append({"plate": r.plate_normalized, "type": r.restriction_type})

    return {
        "version": int(time.time()),
        "generated_at": now.isoformat(),
        "gate": {"id": gate.id, "code": gate.code, "direction": gate.direction},
        "allowed_plates": allowed_plates,
        "restricted_plates": restricted_plates,
        "tariffs": [],
        "settings": {"unknown_plate_policy": "REQUIRE_OPERATOR_APPROVAL"},
    }