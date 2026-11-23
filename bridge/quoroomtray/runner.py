import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType

from . import settings
from .actions import (
    LAUNCH_FAILED_EXIT_CODE,
    ActionKind,
    ActionResult,
    ActionStatus,
)
from .process import ScriptOutcome, last_output_line, run_powershell_script

ScriptLauncher = Callable[[Path], ScriptOutcome]
ThreadSpawner = Callable[[Callable[[], None]], None]

STAND_SCRIPTS = MappingProxyType(
    {
        ActionKind.START: settings.START_SCRIPT,
        ActionKind.STOP: settings.STOP_SCRIPT,
    }
)


def spawn_daemon_thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, daemon=True).start()


class ScriptRunner:
    def __init__(
        self,
        scripts: Mapping[ActionKind, Path] = STAND_SCRIPTS,
        launch: ScriptLauncher = run_powershell_script,
        spawn: ThreadSpawner = spawn_daemon_thread,
        on_finished: Callable[[ActionResult], None] | None = None,
    ):
        self._scripts = scripts
        self._launch = launch
        self._spawn = spawn
        self._on_finished = on_finished
        self._lock = threading.Lock()
        self._status = ActionStatus()

    def status(self) -> ActionStatus:
        with self._lock:
            return self._status

    def begin(self, kind: ActionKind) -> bool:
        with self._lock:
            if self._status.running is not None:
                return False
            self._status = ActionStatus(kind, self._status.last_result)
        try:
            self._spawn(lambda: self._work(kind))
        except BaseException:
            self._finish(None)
            raise
        return True

    def _work(self, kind: ActionKind) -> None:
        try:
            outcome = self._launch(self._scripts[kind])
            result = ActionResult(
                kind, outcome.exit_code, last_output_line(outcome.output)
            )
        except Exception as failure:
            result = ActionResult(kind, LAUNCH_FAILED_EXIT_CODE, str(failure))
        self._finish(result)
        if self._on_finished is not None:
            self._on_finished(result)

    def _finish(self, result: ActionResult | None) -> None:
        with self._lock:
            self._status = ActionStatus(None, result or self._status.last_result)
