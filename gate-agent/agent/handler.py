import uuid
from datetime import datetime, timezone

from agent.central_client import central
from agent.config import settings
from agent.database import db
from agent.decision import offline_decide
from agent.shared_plate import normalize_plate


async def handle_plate_event(plate_raw: str, source_event_id: str | None = None,
                             direction: str = "IN") -> dict:
    normalized = normalize_plate(plate_raw)
    source_event_id = source_event_id or str(uuid.uuid4())
    idem_key = f"{settings.GATE_CODE}:{source_event_id}"

    payload = {
        "gate_code": settings.GATE_CODE,
        "direction": direction,
        "plate_raw": plate_raw,
        "source_event_id": source_event_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "confidence": 97.5,
    }

    decision_info = None
    online = False
    if await central.check_online():
        try:
            decision_info = await central.check_access(payload)
            online = True
        except Exception:
            decision_info = None

    if decision_info is None:
        snap = await db.get_snapshot()
        decision_info = offline_decide(snap, normalized, direction, await db.is_locally_inside(normalized or ""))
        await db.add_pending(idem_key, {**payload, "client_decision": decision_info["decision"]})

    decision = decision_info.get("decision")
    reason = decision_info.get("decision_reason") or decision_info.get("reason") or ""
    await db.log_event(normalized or plate_raw, decision, reason, direction, online)

    barrier_action = decision_info.get("barrier_action") or (
        "OPEN" if decision in ("ALLOW", "ALLOW_WITH_WARNING", "OFFLINE_ALLOW") else "KEEP_CLOSED"
    )
    if barrier_action == "OPEN":
        from agent.runtime import runtime
        if runtime.barrier is not None:
            result = await runtime.barrier.open(command_id=idem_key)
            print(f"[barrier] {result.message}")

    return {
        "decision": decision,
        "decision_reason": reason,
        "barrier_action": barrier_action,
        "online": online,
        "plate_normalized": normalized,
        "source_event_id": source_event_id,
    }