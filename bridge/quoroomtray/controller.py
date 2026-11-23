from collections.abc import Callable
from functools import partial
from pathlib import Path

from . import settings
from .click import OpenElement, left_click
from .entries import TrayEntry, TraySnapshot
from .guard import FailureReport, guarded
from .menu import MenuItem, MenuRole, build_menu
from .observation import Observation
from .refresh import RefreshSignal
from .runner import ScriptRunner
from .state import StandState, stand_state
from .texts import TrayTexts
from .view import TrayView
from .wording import tooltip_text


class TrayController:
    def __init__(
        self,
        observe: Callable[[], Observation],
        runner: ScriptRunner,
        texts: TrayTexts,
        view: TrayView,
        signal: RefreshSignal,
        open_url: Callable[[str], object],
        open_file: Callable[[Path], object],
        report: FailureReport,
    ):
        self._observe = observe
        self._runner = runner
        self._texts = texts
        self._view = view
        self._signal = signal
        self._open_url = open_url
        self._open_file = open_file
        self._report = report
        self._state: StandState | None = None
        self._shown: TraySnapshot | None = None
        self._selections: dict[MenuRole, Callable[[MenuItem], None]] = {
            MenuRole.TOGGLE: self._toggle,
            MenuRole.OPEN_LOG: self._open_log,
            MenuRole.EXIT: self._exit,
        }

    def snapshot(self) -> TraySnapshot:
        observation = self._observe()
        state = stand_state(observation, self._runner.status())
        self._state = state
        menu = build_menu(state, observation, self._texts)
        return TraySnapshot(
            state.colour,
            tooltip_text(state, self._texts),
            (self._click_entry(), *(self._entry(item) for item in menu)),
        )

    def opening_snapshot(self) -> TraySnapshot:
        snapshot = self.snapshot()
        self._shown = snapshot
        return snapshot

    def refresh(self) -> None:
        snapshot = self.snapshot()
        if snapshot != self._shown:
            self._view.show(snapshot)
            self._shown = snapshot

    def _click_entry(self) -> TrayEntry:
        return TrayEntry(
            "", True, guarded(self._click, self._report), default=True, visible=False
        )

    def _entry(self, item: MenuItem) -> TrayEntry:
        select = self._selections.get(item.role)
        if select is None:
            return TrayEntry(item.text, item.enabled)
        on_select = guarded(partial(select, item), self._report)
        return TrayEntry(item.text, item.enabled, on_select)

    def _click(self) -> None:
        decision = left_click(self._state, self._texts)
        if isinstance(decision, OpenElement):
            self._open_url(decision.url)
        else:
            self._view.notify(decision.text)

    def _toggle(self, item: MenuItem) -> None:
        if self._runner.begin(item.action):
            self._signal.request()

    def _open_log(self, item: MenuItem) -> None:
        self._open_file(settings.BROKER_LOG)

    def _exit(self, item: MenuItem) -> None:
        self._signal.stop()
        self._view.stop()
