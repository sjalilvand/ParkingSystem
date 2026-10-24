import json
import secrets
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
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


# ---------------------------------------------------------------------------
# الحاقیه §۶ — سناریو A: دریافت مستقیم رویداد از دوربین‌های پلاک‌خوان ANPR
#   (Hikvision / Dahua / UpCam / عمومی). دوربین به این آدرس POST می‌زند:
#     http://<سرور>:<پورت>/api/v1/gate/events/anpr/GATE-IN-01/IN?api_key=<کلید گیت>
#   بدنهٔ پذیرفته‌شده: JSON تودرتو / XML / متن ساده / multipart (ISAPI) —
#   همچنین پلاک می‌تواند در خود query string باشد (?plate=12ب345ایران11).
# ---------------------------------------------------------------------------
_ANPR_PLATE_KEYS = (
    "plate", "platenumber", "plate_number", "plateno", "plate_no", "platestring",
    "licenseplate", "license_plate", "lpnumber", "carNumber".lower(),
    "platenos", "carnumber", "licencenumber", "licensenumber",
)


async def _require_gate_key_relaxed(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    api_key: str | None = None,
) -> None:
    """احراز دوربین: X-API-Key یا api_key در query (دوربین‌ها هدر نمی‌فرستند) یا Bearer."""
    if x_api_key and secrets.compare_digest(x_api_key, settings.GATE_API_KEY):
        return
    if api_key and secrets.compare_digest(api_key, settings.GATE_API_KEY):
        return
    if credentials is not None:
        try:
            payload = decode_token(credentials.credentials)
            if payload.get("type") == "access":
                return
        except Exception:
            pass
    raise HTTPException(status_code=401, detail="GATE_AUTH_FAILED")


def _dig_plate(obj) -> str | None:
    keys = set(_ANPR_PLATE_KEYS)
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in keys and isinstance(v, (str, int)) and str(v).strip():
                return str(v).strip()
        for v in obj.values():
            r = _dig_plate(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _dig_plate(v)
            if r:
                return r
    return None


def _plate_from_text(text: str) -> str | None:
    import re
    alt = "|".join(re.escape(k) for k in _ANPR_PLATE_KEYS)
    m = re.search(rf'"(?:{alt})"\s*:\s*"([^"]+)"', text, re.I)
    if m:
        return m.group(1)
    m = re.search(rf"<(?:{alt})>\s*([^<]+?)\s*</", text, re.I)
    if m:
        return m.group(1)
    # الگوی مستقیم پلاک ایرانی در متن: 12ب345ایران11 / 12B345IR11 / ۱۲ ب ۳۴۵ ایران ۱۱
    m = re.search(r"\d{2}[\s\u200c]*[بپتثجچخدذرزژسشصضطظعغفقکگلمنوهابیاA-Zآ-ی][\s\u200c]*\d{3}"
                  r"(?:[\s\u200c]*(?:ایران|IR|ir))?(?:[\s\u200c]*\d{2})?", text)
    if m:
        return m.group(0).strip()
    return None


def _extract_anpr_plate(raw_body: bytes, content_type: str) -> str | None:
    """استخراج پلاک از JSON / XML / متن / multipart."""
    text = (raw_body or b"").decode("utf-8", "replace")
    if not text.strip():
        return None
    ct = (content_type or "").lower()
    if "json" in ct or text.lstrip().startswith(("{", "[")):
        try:
            import json
            return _dig_plate(json.loads(text))
        except Exception:
            pass
    if "multipart" in ct:
        # همهٔ بخش‌های متنی multipart را باهم ببین (ISAPI: XML + JPEG)
        try:
            from email.parser import Parser
            from email.policy import default as epolicy
            msg = Parser(policy=epolicy).parsestr(
                "Content-Type: " + (content_type or "") + "\r\n\r\n" + text)
            for part in msg.walk():
                if part.get_content_type().startswith(("text/", "application/json", "application/xml")):
                    try:
                        payload = part.get_payload(decode=True) or b""
                        found = _plate_from_text(payload.decode("utf-8", "replace"))
                        if found:
                            return found
                        import json as _json
                        try:
                            found = _dig_plate(_json.loads(payload.decode("utf-8", "replace")))
                            if found:
                                return found
                        except Exception:
                            pass
                    except Exception:
                        continue
        except Exception:
            pass
        return _plate_from_text(text)
    return _plate_from_text(text)


async def _handle_anpr(request: Request, db: AsyncSession,
                       gate_code: str | None, direction: str | None,
                       _: object) -> dict:
    # ۱) پلاک در query string (بسیاری از دوربین‌ها فقط query می‌فرستند)
    plate = request.query_params.get("plate") or request.query_params.get("PlateNo") \
        or request.query_params.get("plateNumber")
    raw_body = await request.body()
    ct = request.headers.get("content-type", "")
    # ۲) پلاک در بدنه (JSON/XML/text/multipart)
    if not plate:
        plate = _extract_anpr_plate(raw_body, ct)
    if not plate:
        raise HTTPException(status_code=422,
                            detail="PLATE_NOT_FOUND_IN_PAYLOAD — پلاک در query یا بدنهٔ ارسالی یافت نشد")
    gate_code = (gate_code or request.query_params.get("gate") or request.query_params.get("gate_code")
                 or "GATE-IN-01").upper()
    direction = (direction or request.query_params.get("direction") or "IN").upper()
    if direction not in ("IN", "OUT"):
        direction = "IN"
    try:
        confidence = float(request.query_params.get("confidence") or 0) or None
    except (TypeError, ValueError):
        confidence = None
    try:
        result = await GateDecisionService.process_plate_event(
            db,
            gate_code=gate_code,
            direction=direction,
            plate_raw=plate,
            source_event_id=f"anpr-{uuid.uuid4()}",
            confidence=confidence,
            raw_payload={"source": "anpr-camera",
                         "content_type": ct,
                         "query": dict(request.query_params)},
        )
        await _notify_gate_decision(db, gate_code, plate, result)
        return {
            "ok": True,
            "decision": result.get("decision"),
            "decision_reason": result.get("decision_reason"),
            "barrier_action": result.get("barrier_action"),
            "duplicate": result.get("duplicate", False),
            "plate": result.get("plate", {}).get("normalized"),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/events/anpr")
async def anpr_event(request: Request,
                     db: AsyncSession = Depends(get_db),
                     _: object = Depends(_require_gate_key_relaxed)):
    return await _handle_anpr(request, db, None, None, _)


@router.post("/events/anpr/{gate_code}/{direction}")
async def anpr_event_gate(request: Request, gate_code: str, direction: str,
                          db: AsyncSession = Depends(get_db),
                          _: object = Depends(_require_gate_key_relaxed)):
    return await _handle_anpr(request, db, gate_code, direction, _)


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
