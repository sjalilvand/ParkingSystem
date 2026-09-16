import httpx

from agent.config import settings


class CentralClient:
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=settings.CENTRAL_API_URL, timeout=5.0)
        self.online = False

    def _headers(self):
        return {"X-API-Key": settings.GATE_API_KEY, "Content-Type": "application/json"}

    async def check_online(self) -> bool:
        try:
            r = await self.client.get("/ping", headers=self._headers())
            self.online = r.status_code == 200
        except Exception:
            self.online = False
        return self.online

    async def check_access(self, payload: dict) -> dict:
        r = await self.client.post("/gate/events/plate-detected", json=payload, headers=self._headers())
        r.raise_for_status()
        self.online = True
        return r.json()

    async def heartbeat(self, payload: dict) -> dict | None:
        try:
            r = await self.client.post("/gate/heartbeat", json=payload, headers=self._headers())
            r.raise_for_status()
            self.online = True
            return r.json()
        except Exception:
            return None

    async def fetch_snapshot(self) -> dict | None:
        try:
            r = await self.client.get("/gate/offline-snapshot", params={"gate_code": settings.GATE_CODE}, headers=self._headers())
            r.raise_for_status()
            self.online = True
            return r.json()
        except Exception:
            return None

    async def sync_events(self, events: list[dict]) -> dict | None:
        try:
            r = await self.client.post("/gate/sync", json={"events": events}, headers=self._headers())
            r.raise_for_status()
            self.online = True
            return r.json()
        except Exception:
            return None


central = CentralClient()