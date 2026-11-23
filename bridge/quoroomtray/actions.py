from dataclasses import dataclass
from enum import Enum

LAUNCH_FAILED_EXIT_CODE = -1


class ActionKind(Enum):
    START = "start"
    STOP = "stop"


@dataclass(frozen=True)
class ActionResult:
    kind: ActionKind
    exit_code: int
    last_line: str

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class ActionStatus:
    running: ActionKind | None = None
    last_result: ActionResult | None = None
