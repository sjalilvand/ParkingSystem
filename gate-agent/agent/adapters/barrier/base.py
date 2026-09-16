from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class BarrierResult:
    success: bool
    command_id: str
    message: str = ""


@dataclass
class BarrierStatus:
    is_open: bool
    healthy: bool


class BarrierAdapter(ABC):
    @abstractmethod
    async def open(self, command_id: str) -> BarrierResult: ...

    @abstractmethod
    async def get_status(self) -> BarrierStatus: ...

    @abstractmethod
    async def health_check(self) -> bool: ...