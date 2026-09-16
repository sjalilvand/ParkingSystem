import asyncio
import json

from agent.central_client import central
from agent.config import settings
from agent.database import db


async def upload_pending() -> int:
    """ارسال رخدادهای آفلاین به ترتیب زمانی؛ حذف پس از تأیید سرور. خروجی: تعداد ارسالی یا -1."""
    rows = await db.pending_events()
    if not rows:
        return 0
    if not await central.check_online():
        return -1

    events = []
    for _row_id, idem_key, payload_raw in rows:
        payload = json.loads(payload_raw)
        payload["idempotency_key"] = idem_key
        events.append(payload)

    result = await central.sync_events(events)
    if result and result.get("success"):
        processed = {r.get("source_event_id"): r for r in result.get("results", [])}
        for row_id, _idem_key, payload_raw in rows:
            payload = json.loads(payload_raw)
            info = processed.get(payload.get("source_event_id"))
            if info and "error" not in info:
                await db.remove_pending(row_id)
        return len(rows)
    return -1


async def refresh_snapshot() -> bool:
    snap = await central.fetch_snapshot()
    if snap:
        await db.save_snapshot(snap)
        return True
    return False


async def sync_loop():
    while True:
        try:
            sent = await upload_pending()
            refreshed = await refresh_snapshot()
            if sent or refreshed:
                print(f"[sync] sent={sent} snapshot={'OK' if refreshed else 'FAIL'}")
        except Exception as exc:
            print(f"[sync] error: {exc}")
        await asyncio.sleep(settings.SNAPSHOT_INTERVAL_SECONDS)