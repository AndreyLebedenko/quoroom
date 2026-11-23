from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from . import settings


class AutostartOutcome(Enum):
    INSTALLED = "installed"
    REMOVED = "removed"
    NOT_INSTALLED = "not_installed"
    TARGET_MISSING = "target_missing"


@dataclass(frozen=True)
class Shortcut:
    path: Path
    target: Path
    arguments: str
    working_directory: Path
    description: str


ShortcutWriter = Callable[[Shortcut], None]


def startup_folder(environ: Mapping[str, str]) -> Path:
    return Path(environ["APPDATA"]) / settings.STARTUP_FOLDER_UNDER_APPDATA


def stand_shortcut(environ: Mapping[str, str]) -> Shortcut:
    return Shortcut(
        startup_folder(environ) / settings.AUTOSTART_SHORTCUT_NAME,
        settings.PYTHONW,
        settings.AUTOSTART_ARGUMENTS,
        settings.BRIDGE_DIR,
        settings.AUTOSTART_DESCRIPTION,
    )


class Autostart:
    def __init__(self, shortcut: Shortcut, write: ShortcutWriter):
        self._shortcut = shortcut
        self._write = write

    @property
    def shortcut(self) -> Shortcut:
        return self._shortcut

    def install(self) -> AutostartOutcome:
        if not self._shortcut.target.is_file():
            return AutostartOutcome.TARGET_MISSING
        self._shortcut.path.parent.mkdir(parents=True, exist_ok=True)
        self._write(self._shortcut)
        return AutostartOutcome.INSTALLED

    def remove(self) -> AutostartOutcome:
        try:
            self._shortcut.path.unlink()
        except FileNotFoundError:
            return AutostartOutcome.NOT_INSTALLED
        return AutostartOutcome.REMOVED
