from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .actions import ActionResult
from .controller import TrayController
from .guard import FailureReport, guarded
from .observation import Observation
from .refresh import PollLoop, RefreshSignal
from .runner import ScriptRunner, ThreadSpawner, spawn_daemon_thread
from .texts import TrayTexts
from .view import TrayView


class InstanceClaim(Protocol):
    def close(self) -> None: ...


def refresh_after_action(
    signal: RefreshSignal, report: FailureReport
) -> Callable[[ActionResult], None]:
    return guarded(lambda result: signal.request(), report)


def run_tray(
    claim_instance: Callable[[], InstanceClaim | None],
    build_view: Callable[[], TrayView],
    observe: Callable[[], Observation],
    texts: TrayTexts,
    open_url: Callable[[str], object],
    open_file: Callable[[Path], object],
    report: FailureReport,
    spawn: ThreadSpawner = spawn_daemon_thread,
) -> int:
    claim = claim_instance()
    if claim is None:
        return 0
    try:
        signal = RefreshSignal()
        runner = ScriptRunner(on_finished=refresh_after_action(signal, report))
        view = build_view()
        controller = TrayController(
            observe, runner, texts, view, signal, open_url, open_file, report
        )
        loop = PollLoop(controller.refresh, signal, report)
        view.run(controller.opening_snapshot(), lambda: spawn(loop.run))
    finally:
        claim.close()
    return 0
