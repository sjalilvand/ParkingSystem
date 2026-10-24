"""صدور رویداد گیت از مسیر دوربین (سناریو A/B) — مشترک میان poller و capture-ocr.

جریان: پلاک خوانده‌شده → process_plate_event (تصمیم/جلسه/رویداد)
      → اعلان اپراتور (تصمیم‌های حساس) → رلهٔ راهبند (در صورت تنظیم BARRIER_RELAY_URL)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings


async def emit_plate_event(
    db: AsyncSession,
    *,
    gate_code: str,
    direction: str,
    plate_raw: str,
    confidence: float | None = None,
    source: str = "camera",
    source_event_id: str | None = None,
    raw_payload: dict | None = None,
    notify: bool = True,
) -> dict:
    """رویداد پلاک را در زنجیرهٔ تصمیم گیت ثبت می‌کند و نتیجه را برمی‌گرداند."""
    from app.modules.access_control.router import _notify_gate_decision
    from app.modules.access_control.service import GateDecisionService

    source_event_id = source_event_id or f"cam-{uuid.uuid4()}"
    payload_extra = dict(raw_payload or {})
    payload_extra.setdefault("source", source)

    result = await GateDecisionService.process_plate_event(
        db,
        gate_code=gate_code,
        direction=direction,
        plate_raw=plate_raw,
        source_event_id=source_event_id,
        confidence=confidence,
        captured_at=datetime.now(timezone.utc),
        raw_payload=payload_extra,
    )
    if notify:
        await _notify_gate_decision(db, gate_code, plate_raw, result)

    # رلهٔ راهبند — سخت‌افزار واقعی (اختیاری؛ BARRIER_RELAY_URL در .env)
    if result.get("barrier_action") == "OPEN":
        _fire_barrier_relay(gate_code=gate_code, plate_raw=plate_raw,
                            source_event_id=source_event_id)
    return result


def _fire_barrier_relay(*, gate_code: str, plate_raw: str, source_event_id: str) -> None:
    """فرمان OPEN به رلهٔ راهبند (best-effort — خطا فقط لاگ می‌شود)."""
    url = (settings.BARRIER_RELAY_URL or "").strip()
    if not url:
        return

    def _post() -> None:
        try:
            import httpx
            httpx.post(url, json={
                "gate_code": gate_code,
                "action": "OPEN",
                "plate_raw": plate_raw,
                "source_event_id": source_event_id,
                "ts": datetime.now(timezone.utc).isoformat(),
            }, timeout=3.0)
            logger.info(f"[barrier-relay] OPEN sent → {gate_code}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[barrier-relay] FAILED: {type(exc).__name__}: {exc}")

    import threading
    threading.Thread(target=_post, daemon=True, name="barrier-relay").start()
