import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .shell_settings import ERROR_LOG_MAX_BYTES

BACKUP_SUFFIX = ".1"


class ErrorLog:
    def __init__(
        self,
        path: Path,
        clock: Callable[[], datetime] = datetime.now,
        max_bytes: int = ERROR_LOG_MAX_BYTES,
    ):
        self._path = path
        self._clock = clock
        self._max_bytes = max_bytes

    @property
    def backup_path(self) -> Path:
        return self._path.with_name(self._path.name + BACKUP_SUFFIX)

    def __call__(self, failure: Exception) -> None:
        stamp = self._clock().isoformat(timespec="seconds")
        trace = "".join(traceback.format_exception(failure))
        entry = f"{stamp} {trace}\n".encode("utf-8")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._make_room_for(len(entry))
            with self._path.open("ab") as log:
                log.write(entry)
        except OSError:
            pass

    def _make_room_for(self, incoming: int) -> None:
        try:
            current = self._path.stat().st_size
        except FileNotFoundError:
            return
        if current and current + incoming > self._max_bytes:
            self._path.replace(self.backup_path)
