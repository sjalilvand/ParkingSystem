from agent.adapters.plate_reader.base import PlateReaderAdapter


class MockPlateReader(PlateReaderAdapter):
    """دوربین شبیه‌سازی‌شده — برای توسعه و تست بدون سخت‌افزار."""

    def __init__(self):
        self.connected = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def health_check(self) -> bool:
        return self.connected