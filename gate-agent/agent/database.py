import json
import time

import aiosqlite

from agent.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT UNIQUE,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL,
    tries INTEGER DEFAULT 0,
    last_error TEXT
);
CREATE TABLE IF NOT EXISTS snapshot (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL
);
CREATE TABLE IF NOT EXISTS recent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate TEXT, decision TEXT, reason TEXT,
    direction TEXT, online INTEGER, created_at REAL
);
CREATE TABLE IF NOT EXISTS open_entries (
    plate TEXT PRIMARY KEY, entry_at REAL
);
"""


class LocalDB:
    def __init__(self):
        self.path = settings.DB_PATH

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def execute(self, sql: str, params: tuple = (), fetch: str | None = None):
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(sql, params)
            rows = None
            if fetch == "one":
                rows = await cur.fetchone()
            elif fetch == "all":
                rows = await cur.fetchall()
            await db.commit()
            return cur.lastrowid, rows

    async def add_pending(self, idem_key: str, payload: dict):
        await self.execute(
            "INSERT OR IGNORE INTO pending_events (idempotency_key, payload, created_at) VALUES (?,?,?)",
            (idem_key, json.dumps(payload, ensure_ascii=False), time.time()),
        )

    async def pending_events(self, limit: int = 100):
        _, rows = await self.execute(
            "SELECT id, idempotency_key, payload FROM pending_events ORDER BY created_at ASC LIMIT ?",
            (limit,), fetch="all",
        )
        return rows or []

    async def pending_count(self) -> int:
        _, row = await self.execute("SELECT COUNT(*) FROM pending_events", fetch="one")
        return row[0] if row else 0

    async def remove_pending(self, event_id: int):
        await self.execute("DELETE FROM pending_events WHERE id = ?", (event_id,))

    async def save_snapshot(self, snapshot: dict):
        await self.execute(
            "INSERT OR REPLACE INTO snapshot (key, value, updated_at) VALUES ('main', ?, ?)",
            (json.dumps(snapshot, ensure_ascii=False), time.time()),
        )

    async def get_snapshot(self) -> dict | None:
        _, row = await self.execute("SELECT value FROM snapshot WHERE key='main'", fetch="one")
        return json.loads(row[0]) if row else None

    async def log_event(self, plate: str, decision: str, reason: str, direction: str, online: bool):
        await self.execute(
            "INSERT INTO recent_events (plate, decision, reason, direction, online, created_at) VALUES (?,?,?,?,?,?)",
            (plate, decision, reason, direction, 1 if online else 0, time.time()),
        )
        if decision in ("ALLOW", "ALLOW_WITH_WARNING", "OFFLINE_ALLOW") and direction == "IN":
            await self.execute("INSERT OR REPLACE INTO open_entries (plate, entry_at) VALUES (?,?)", (plate, time.time()))
        if direction == "OUT" and decision in ("ALLOW", "ALLOW_WITH_WARNING", "OFFLINE_ALLOW"):
            await self.execute("DELETE FROM open_entries WHERE plate = ?", (plate,))

    async def recent_events(self, limit: int = 50):
        _, rows = await self.execute(
            "SELECT plate, decision, reason, direction, online, created_at FROM recent_events ORDER BY id DESC LIMIT ?",
            (limit,), fetch="all",
        )
        return [{"plate": r[0], "decision": r[1], "reason": r[2], "direction": r[3],
                 "online": bool(r[4]), "created_at": r[5]} for r in (rows or [])]

    async def is_locally_inside(self, plate: str) -> bool:
        _, row = await self.execute("SELECT 1 FROM open_entries WHERE plate = ?", (plate,), fetch="one")
        return row is not None


db = LocalDB()