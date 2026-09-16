import asyncio
import shutil

from agent.central_client import central
from agent.config import settings
from agent.database import db
from agent.runtime import runtime


async def heartbeat_loop():
    while True:
        try:
            camera_ok = await runtime.reader.health_check() if runtime.reader else False
            barrier_ok = await runtime.barrier.health_check() if runtime.barrier else False
            disk_free_mb = int(shutil.disk_usage(".").free // (1024 * 1024))
            payload = {
                "gate_code": settings.GATE_CODE,
                "agent_version": settings.AGENT_VERSION,
                "camera_ok": camera_ok,
                "barrier_ok": barrier_ok,
                "printer_ok": None,
                "disk_free_mb": disk_free_mb,
                "unsynced_count": await db.pending_count(),
            }
            resp = await central.heartbeat(payload)
            print(f"[heartbeat] {'ONLINE' if resp else 'OFFLINE (retry later)'}")
        except Exception as exc:
            print(f"[heartbeat] error: {exc}")
        await asyncio.sleep(settings.HEARTBEAT_INTERVAL_SECONDS)