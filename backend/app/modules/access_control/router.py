import json
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.audit import write_audit
from app.core.config import settings
from app.core.exceptions import ForbiddenError
from app.core.permissions import user_has_permission, user_is_admin
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
    if x_api_key and secrets.compare_digest(x_api_key, settings.GATE_API_KEY):
        return None
    if credentials is not None:
        try:
            payload = decode_token(credentials.credentials)
            if payload.get("type") == "access":
                return payload.get("sub")
        except Exception:
            pass
    raise HTTPException(status_code=401, detail="GATE_AUTH_FAILED")


async def _enforce_user_permission(db: AsyncSession, user: User, perm_code: str) -> None:
    """P0 (سند بخش ۸): مجوز عملیات حساس گیت در لایه API.
    با ENFORCE_GATE_PERMISSIONS=False قابل موقت‌غیرفعال‌سازی است (rollback سریع)."""
    if not getattr(settings, "ENFORCE_GATE_PERMISSIONS", True):
        return
    if await user_is_admin(db, user):
        return
    if not await user_has_permission(db, user, perm_code):
        raise ForbiddenError("دسترسی مجاز نیست")


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
    "EXIT_UNPAID_BLOCKED": "خروج به‌دلیل بدهی پرداخت‌نشده (سیاست مصوب نشده/فعال)",
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
    except Exception as _exc:
        import traceback
        print("[notify] FAILED:", repr(_exc))
        traceback.print_exc()


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
            driver_request=body.driver_request,
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
            driver_request=body.driver_request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/access/manual")
async def access_manual(body: ManualAccessRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    # P0 (سند بخش ۸): عملیات دستی گیت نیازمند مجوز است
    await _enforce_user_permission(db, user, "gate.manual_access")
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
    # P0 (سند بخش ۸): بازکردن دستی راهبند نیازمند مجوز است
    await _enforce_user_permission(db, user, "gate.barrier_open")
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
                driver_request=ev.driver_request,
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


# ---------------------------------------------------------------------------
# الحاقیه §۳ — صف تأیید انسانی پلاک (NEEDS_REVIEW)
# اصل حفظ سابقه: plate_raw اصلی هرگز تغییر نمی‌کند؛ اصلاح در ستون‌های
# corrected_* ثبت می‌شود (مقدار + کاربر + زمان + یادداشت) و audit می‌ماند.
# ---------------------------------------------------------------------------
from fastapi import Query  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy import func  # noqa: E402

from app.core.exceptions import NotFoundError  # noqa: E402
from app.modules.access_control.models import PlateRecognitionEvent  # noqa: E402
from app.shared.plate import normalize_plate  # noqa: E402


class PlateReviewResolve(BaseModel):
    action: str = "CONFIRM"          # CONFIRM | CORRECT | REJECT
    plate_raw: str | None = None     # برای CORRECT — مقدار اصلاح‌شدهٔ تایپی
    note: str | None = None


@router.get("/plate-reviews")
async def list_plate_reviews(
    status: str = "NEEDS_REVIEW",
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not (await user_is_admin(db, user) or await user_has_permission(db, user, "gate.manual_access")):
        raise ForbiddenError("مجوز بازبینی پلاک ندارید")
    q = select(PlateRecognitionEvent).where(
        PlateRecognitionEvent.review_status == status.upper())
    total = (await db.execute(select(func.count()).select_from(
        PlateRecognitionEvent).where(
            PlateRecognitionEvent.review_status == status.upper()))).scalar_one()
    rows = (await db.execute(q.order_by(
        PlateRecognitionEvent.received_at.desc()).limit(limit))).scalars().all()
    return {
        "status": status.upper(), "total": total, "items": [{
            "id": r.id, "gate_id": r.gate_id, "direction": r.direction,
            "plate_raw": r.plate_raw, "plate_normalized": r.plate_normalized,
            "plate_corrected": r.plate_corrected,
            "confidence": r.confidence, "review_status": r.review_status,
            "capture_quality": r.capture_quality,
            "corrected_by": r.corrected_by, "corrected_at": (
                r.corrected_at.isoformat() if r.corrected_at else None),
            "correction_note": r.correction_note,
            "captured_at": r.captured_at.isoformat() if r.captured_at else None,
            "received_at": r.received_at.isoformat() if r.received_at else None,
        } for r in rows],
    }


@router.get("/plate-reviews/metrics")
async def plate_review_metrics(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """آمار بازبینی + صدک تأخیر پردازش (هدف الحاقیه: p95 < ۱ ثانیه)."""
    if not (await user_is_admin(db, user) or await user_has_permission(db, user, "gate.manual_access")):
        raise ForbiddenError("مجوز بازبینی پلاک ندارید")
    counts: dict[str, int] = {}
    for st in ("AUTO_OK", "NEEDS_REVIEW", "CONFIRMED", "CORRECTED", "REJECTED"):
        counts[st] = (await db.execute(
            select(func.count()).select_from(PlateRecognitionEvent)
            .where(PlateRecognitionEvent.review_status == st))).scalar_one()
    latencies = (await db.execute(
        select(PlateRecognitionEvent.processing_ms)
        .where(PlateRecognitionEvent.processing_ms.isnot(None))
        .order_by(PlateRecognitionEvent.processing_ms.asc())
        .limit(2000))).scalars().all()

    def _pct(p: float) -> float | None:
        if not latencies:
            return None
        idx = min(int(p * (len(latencies) - 1)), len(latencies) - 1)
        return round(float(latencies[idx]), 1)

    return {"counts": counts,
            "processing_ms": {"p50": _pct(0.50), "p95": _pct(0.95),
                              "target_p95_ms": 1000.0, "n": len(latencies)}}


@router.post("/plate-reviews/{recognition_id}/resolve")
async def resolve_plate_review(
    recognition_id: str,
    body: PlateReviewResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """تأیید/اصلاح/رد پلاک توسط انسان — مقدار اصلی حفظ و اصلاح جداگانه ثبت می‌شود."""
    if not (await user_is_admin(db, user) or await user_has_permission(db, user, "gate.manual_access")):
        raise ForbiddenError("مجوز بازبینی پلاک ندارید")
    rec = await db.get(PlateRecognitionEvent, recognition_id)
    if rec is None:
        raise NotFoundError("رکورد پلاک‌خوانی یافت نشد")
    action = body.action.upper()
    if action not in ("CONFIRM", "CORRECT", "REJECT"):
        raise ForbiddenError("عملیات نامعتبر است (CONFIRM/CORRECT/REJECT)")
    if action == "CORRECT":
        if not body.plate_raw:
            raise ForbiddenError("برای اصلاح، مقدار پلاک الزامی است")
        rec.plate_corrected = body.plate_raw
        rec.plate_corrected_normalized = normalize_plate(body.plate_raw) or None
        rec.corrected_by = user.id
        rec.corrected_at = datetime.now(timezone.utc)
        rec.correction_note = body.note
        rec.review_status = "CORRECTED"
    elif action == "CONFIRM":
        rec.review_status = "CONFIRMED"
        if body.note:
            rec.correction_note = body.note
    else:
        rec.review_status = "REJECTED"
        if body.note:
            rec.correction_note = body.note
    await write_audit(db, user_id=user.id, action=f"PLATE_REVIEW_{action}",
                      module="gate", entity_type="plate_recognition",
                      entity_id=rec.id,
                      old_values={"plate_raw": rec.plate_raw,
                                  "review_status": "NEEDS_REVIEW"},
                      new_values={"plate_corrected": rec.plate_corrected,
                                  "review_status": rec.review_status,
                                  "note": body.note})
    await db.commit()
    return {"success": True, "id": rec.id, "review_status": rec.review_status,
            "plate_raw": rec.plate_raw,
            "plate_corrected": rec.plate_corrected,
            "plate_corrected_normalized": rec.plate_corrected_normalized}
