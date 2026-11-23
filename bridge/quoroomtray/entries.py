from collections.abc import Callable
from dataclasses import dataclass, field

from .state import Colour


@dataclass(frozen=True)
class TrayEntry:
    text: str
    enabled: bool
    on_select: Callable[[], None] | None = field(default=None, compare=False)
    default: bool = False
    visible: bool = True


@dataclass(frozen=True)
class TraySnapshot:
    colour: Colour
    tooltip: str
    entries: tuple[TrayEntry, ...]
