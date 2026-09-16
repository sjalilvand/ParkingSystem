import time

from agent.adapters.barrier.base import BarrierAdapter, BarrierResult, BarrierStatus


class MockBarrier(BarrierAdapter):
    def __init__(self):
        self._open_until = 0.0

    async def open(self, command_id: str) -> BarrierResult:
        self._open_until = time.time() + 5
        return BarrierResult(success=True, command_id=command_id, message="MOCK_BARRIER_OPENED")

    async def get_status(self) -> BarrierStatus:
        return BarrierStatus(is_open=time.time() < self._open_until, healthy=True)

    async def health_check(self) -> bool:
        return True