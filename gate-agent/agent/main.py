import asyncio
import sys

import uvicorn

from agent.adapters.barrier.mock import MockBarrier
from agent.adapters.plate_reader.mock import MockPlateReader
from agent.config import settings
from agent.database import db
from agent.heartbeat import heartbeat_loop
from agent.local_api import app as local_app
from agent.runtime import runtime
from agent.sync import refresh_snapshot, sync_loop


def _force_utf8_stdio():
    """جلوگیری از UnicodeEncodeError وقتی stdout به فایل redirect می‌شود (ویندوز cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


async def wait_initial_snapshot():
    """Startup: up to 30s retry for initial snapshot."""
    for i in range(15):
        if await refresh_snapshot():
            print(f"[startup] snapshot OK (attempt {i + 1})")
            return
        print(f"[startup] snapshot retry {i + 1}/15 ...")
        await asyncio.sleep(2)
    print("[startup] snapshot FAILED after 15 attempts")


async def main():
    _force_utf8_stdio()
    print(f"=== Gate Agent | gate={settings.GATE_CODE} | central={settings.CENTRAL_API_URL} | local=:{settings.LOCAL_API_PORT} ===")
    await db.init()

    runtime.barrier = MockBarrier()
    runtime.reader = MockPlateReader()
    await runtime.reader.connect()

    config = uvicorn.Config(local_app, host="127.0.0.1", port=settings.LOCAL_API_PORT, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    tasks = [
        asyncio.create_task(sync_loop()),
        asyncio.create_task(heartbeat_loop()),
        asyncio.create_task(wait_initial_snapshot()),
    ]
    await asyncio.gather(*tasks, server_task)


if __name__ == "__main__":
    asyncio.run(main())