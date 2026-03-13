import threading
from datetime import datetime, timezone
from enum import Enum


class ScannerStatus(Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    SHUTTING_DOWN = "shutting_down"


class ScannerState:
    def __init__(self):
        self._lock = threading.Lock()
        self._status = ScannerStatus.IDLE
        self._started_at: datetime = datetime.now(timezone.utc)

    @property
    def status(self) -> ScannerStatus:
        with self._lock:
            return self._status

    @status.setter
    def status(self, value: ScannerStatus) -> None:
        with self._lock:
            self._status = value

    @property
    def started_at(self) -> datetime:
        return self._started_at

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "status": self._status.value,
                "started_at": self._started_at.isoformat(),
            }


_state: ScannerState | None = None


def get_scanner_state() -> ScannerState:
    global _state
    if _state is None:
        _state = ScannerState()
    return _state
