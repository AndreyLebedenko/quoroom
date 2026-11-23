import threading
from collections.abc import Callable
from typing import Protocol

from . import settings
from .guard import FailureReport, guarded


class Wakeable(Protocol):
    def set(self) -> None: ...
    def clear(self) -> None: ...
    def wait(self, timeout: float | None = None) -> object: ...


class RefreshSignal:
    def __init__(self, event: Wakeable | None = None):
        self._event = event or threading.Event()
        self._stopped = False

    @property
    def stopped(self) -> bool:
        return self._stopped

    def request(self) -> None:
        self._event.set()

    def stop(self) -> None:
        self._stopped = True
        self._event.set()

    def rearm(self) -> None:
        self._event.clear()

    def wait(self, seconds: float) -> None:
        self._event.wait(seconds)


class PollLoop:
    def __init__(
        self,
        refresh: Callable[[], None],
        signal: RefreshSignal,
        report: FailureReport,
        interval: float = settings.POLL_INTERVAL_SECONDS,
    ):
        self._refresh = guarded(refresh, report)
        self._signal = signal
        self._interval = interval

    def run(self) -> None:
        while True:
            self._signal.rearm()
            if self._signal.stopped:
                return
            self._refresh()
            self._signal.wait(self._interval)
