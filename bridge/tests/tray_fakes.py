from collections.abc import Callable
from pathlib import Path

from quoroomtray.actions import ActionKind, ActionResult, ActionStatus
from quoroomtray.observation import Observation, SessionLine
from quoroomtray.process import ScriptOutcome

NO_ACTION = ActionStatus()
SESSION = SessionLine("claude", "online", "claude   online   quiet 3s")
OTHER_SESSION = SessionLine("opencode", "not connected", "opencode not connected")

GREY_PROBES = Observation(stack_answers=False, sessions=None)
GREEN_PROBES = Observation(stack_answers=True, sessions=(SESSION,))
ONLY_STACK_PROBES = Observation(stack_answers=True, sessions=None)
ONLY_BROKER_PROBES = Observation(stack_answers=False, sessions=(SESSION,))

ALL_PROBES = {
    "grey": GREY_PROBES,
    "green": GREEN_PROBES,
    "only stack": ONLY_STACK_PROBES,
    "only broker": ONLY_BROKER_PROBES,
}


def finished(kind: ActionKind, exit_code: int, last_line: str = "") -> ActionStatus:
    return ActionStatus(None, ActionResult(kind, exit_code, last_line))


def running(kind: ActionKind) -> ActionStatus:
    return ActionStatus(kind, None)


class FakeSocket:
    def __init__(self):
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeConnect:
    def __init__(self, failure: OSError | None = None):
        self.failure = failure
        self.calls: list[tuple[tuple[str, int], float]] = []
        self.sockets: list[FakeSocket] = []

    def __call__(self, address: tuple[str, int], timeout: float) -> FakeSocket:
        self.calls.append((address, timeout))
        if self.failure is not None:
            raise self.failure
        opened = FakeSocket()
        self.sockets.append(opened)
        return opened


class FakeFetch:
    def __init__(self, body: bytes | None = None, failure: Exception | None = None):
        self.body = body
        self.failure = failure
        self.calls: list[tuple[str, float]] = []

    def __call__(self, url: str, timeout: float) -> bytes:
        self.calls.append((url, timeout))
        if self.failure is not None:
            raise self.failure
        return self.body


class ManualSpawn:
    def __init__(self, failure: Exception | None = None):
        self.failure = failure
        self.pending: list[Callable[[], None]] = []

    def __call__(self, work: Callable[[], None]) -> None:
        if self.failure is not None:
            raise self.failure
        self.pending.append(work)

    def run_all(self) -> None:
        pending, self.pending = self.pending, []
        for work in pending:
            work()


class ScriptedLauncher:
    def __init__(
        self, outcome: ScriptOutcome | None = None, failure: Exception | None = None
    ):
        self.outcome = outcome or ScriptOutcome(0, "")
        self.failure = failure
        self.scripts: list[Path] = []

    def __call__(self, script: Path) -> ScriptOutcome:
        self.scripts.append(script)
        if self.failure is not None:
            raise self.failure
        return self.outcome
