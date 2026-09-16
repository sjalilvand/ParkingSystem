import asyncio
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, set[WebSocket]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active[user_id].add(ws)

    def disconnect(self, user_id: str, ws: WebSocket):
        self.active[user_id].discard(ws)
        if not self.active[user_id]:
            self.active.pop(user_id, None)

    async def broadcast(self, event_type: str, data: dict):
        message = {
            "event": event_type,
            "event_id": str(uuid.uuid4()),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        text = json.dumps(message, ensure_ascii=False)
        dead = []
        for user_id, sockets in list(self.active.items()):
            for ws in list(sockets):
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append((user_id, ws))
        for user_id, ws in dead:
            self.disconnect(user_id, ws)

    def broadcast_threadsafe(self, event_type: str, data: dict):
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(event_type, data), self._loop)


manager = ConnectionManager()