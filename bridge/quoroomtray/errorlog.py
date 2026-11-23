import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path


class ErrorLog:
    def __init__(self, path: Path, clock: Callable[[], datetime] = datetime.now):
        self._path = path
        self._clock = clock

    def __call__(self, failure: Exception) -> None:
        stamp = self._clock().isoformat(timespec="seconds")
        trace = "".join(traceback.format_exception(failure))
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as log:
                log.write(f"{stamp} {trace}\n")
        except OSError:
            pass
