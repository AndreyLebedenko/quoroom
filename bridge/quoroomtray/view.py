from collections.abc import Callable
from typing import Protocol

from .entries import TraySnapshot


class TrayView(Protocol):
    def run(self, first: TraySnapshot, on_ready: Callable[[], None]) -> None: ...

    def show(self, snapshot: TraySnapshot) -> None: ...

    def notify(self, text: str) -> None: ...

    def stop(self) -> None: ...
