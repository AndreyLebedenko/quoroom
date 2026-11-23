import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from . import settings
from .actions import ActionResult
from .controller import TrayController
from .guard import FailureReport, guarded
from .login import LoginRule
from .login_observer import LoginRuleObserver
from .observation import Observation
from .refresh import PollLoop, RefreshSignal
from .process import run_powershell_script
from .runner import ScriptLauncher, ScriptRunner, ThreadSpawner, spawn_daemon_thread
from .texts import TrayTexts
from .view import TrayView


class InstanceClaim(Protocol):
    def close(self) -> None: ...


def refresh_after_action(
    signal: RefreshSignal, report: FailureReport
) -> Callable[[ActionResult], None]:
    return guarded(lambda result: signal.request(), report)


@dataclass(frozen=True)
class TraySeams:
    spawn: ThreadSpawner = spawn_daemon_thread
    launch: ScriptLauncher = run_powershell_script
    clock: Callable[[], float] = time.monotonic
    poll_interval: float = settings.POLL_INTERVAL_SECONDS


def run_tray(
    claim_instance: Callable[[], InstanceClaim | None],
    build_view: Callable[[], TrayView],
    observe: Callable[[], Observation],
    texts: TrayTexts,
    open_url: Callable[[str], object],
    open_file: Callable[[Path], object],
    report: FailureReport,
    seams: TraySeams = TraySeams(),
) -> int:
    claim = claim_instance()
    if claim is None:
        return 0
    try:
        signal = RefreshSignal()
        runner = ScriptRunner(
            launch=seams.launch,
            spawn=seams.spawn,
            on_finished=refresh_after_action(signal, report),
        )
        login_observe = LoginRuleObserver(
            observe, LoginRule(seams.clock()), runner, seams.clock, report
        )
        view = build_view()
        controller = TrayController(
            login_observe, runner, texts, view, signal, open_url, open_file, report
        )
        loop = PollLoop(controller.refresh, signal, report, seams.poll_interval)
        view.run(controller.opening_snapshot(), lambda: seams.spawn(loop.run))
    finally:
        claim.close()
    return 0
