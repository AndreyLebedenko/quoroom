"""Task tray-03: the controller that maps the model to what the shell draws."""

import unittest
from pathlib import Path

from quoroomtray import settings
from quoroomtray.actions import ActionKind
from quoroomtray.controller import TrayController
from quoroomtray.entries import TrayEntry, TraySnapshot
from quoroomtray.menu import build_menu
from quoroomtray.observation import Observation, SessionLine
from quoroomtray.process import ScriptOutcome
from quoroomtray.refresh import RefreshSignal
from quoroomtray.runner import ScriptRunner
from quoroomtray.state import Colour, stand_state
from quoroomtray.texts import TrayTexts
from quoroomtray.wording import tooltip_text
from tests.tray_fakes import (
    GREEN_PROBES,
    GREY_PROBES,
    ONLY_STACK_PROBES,
    SESSION,
    ManualSpawn,
    ScriptedLauncher,
)
from tests.tray_shell_fakes import (
    FakeView,
    FlagEvent,
    default_entry,
    entry_with_text,
    visible_entries,
)

TEXTS = TrayTexts("en")
START = Path("C:/stand/start.ps1")
STOP = Path("C:/stand/stop.ps1")


class Rig:
    def __init__(self, probes=GREY_PROBES, launcher=None):
        self.probes = probes
        self.view = FakeView()
        self.event = FlagEvent()
        self.signal = RefreshSignal(self.event)
        self.spawn = ManualSpawn()
        self.launcher = launcher or ScriptedLauncher(ScriptOutcome(0, "Done."))
        self.runner = ScriptRunner(
            {ActionKind.START: START, ActionKind.STOP: STOP},
            launch=self.launcher,
            spawn=self.spawn,
        )
        self.opened_urls = []
        self.open_url_failure = None
        self.opened_files = []
        self.failures = []
        self.open_file_failure = None
        self.controller = TrayController(
            lambda: self.probes,
            self.runner,
            TEXTS,
            self.view,
            self.signal,
            self.open_url,
            self.open_file,
            self.failures.append,
        )

    def open_url(self, url):
        if self.open_url_failure is not None:
            raise self.open_url_failure
        self.opened_urls.append(url)

    def open_file(self, path):
        if self.open_file_failure is not None:
            raise self.open_file_failure
        self.opened_files.append(path)

    def snapshot(self) -> TraySnapshot:
        return self.controller.snapshot()

    def entry(self, text: str) -> TrayEntry:
        return entry_with_text(self.snapshot(), text)


class SnapshotContentTests(unittest.TestCase):
    def test_the_colour_and_the_tooltip_come_from_the_model(self):
        rig = Rig(GREEN_PROBES)

        snapshot = rig.snapshot()

        state = stand_state(GREEN_PROBES, rig.runner.status())
        self.assertEqual(Colour.GREEN, snapshot.colour)
        self.assertEqual(tooltip_text(state, TEXTS), snapshot.tooltip)

    def test_the_visible_entries_are_the_model_menu_in_the_same_order(self):
        rig = Rig(GREEN_PROBES)

        shown = [(e.text, e.enabled) for e in visible_entries(rig.snapshot())]

        state = stand_state(GREEN_PROBES, rig.runner.status())
        expected = [
            (item.text, item.enabled) for item in build_menu(state, GREEN_PROBES, TEXTS)
        ]
        self.assertEqual(expected, shown)

    def test_the_session_lines_are_listed_verbatim_and_cannot_be_selected(self):
        rig = Rig(GREEN_PROBES)

        entry = rig.entry(SESSION.line)

        self.assertFalse(entry.enabled)
        self.assertIsNone(entry.on_select)

    def test_the_status_line_cannot_be_selected(self):
        rig = Rig()

        entry = rig.entry(TEXTS.text("tray.status_grey"))

        self.assertFalse(entry.enabled)
        self.assertIsNone(entry.on_select)

    def test_there_is_exactly_one_default_entry_and_it_is_not_drawn(self):
        snapshot = Rig().snapshot()

        defaults = [entry for entry in snapshot.entries if entry.default]

        self.assertEqual(1, len(defaults))
        self.assertFalse(defaults[0].visible)

    def test_a_snapshot_is_equal_to_another_with_the_same_look_whatever_its_callbacks(
        self,
    ):
        rig = Rig(GREEN_PROBES)

        self.assertEqual(rig.snapshot(), rig.snapshot())

    def test_a_snapshot_differs_when_the_colour_differs(self):
        rig = Rig(GREY_PROBES)
        grey = rig.snapshot()
        rig.probes = GREEN_PROBES

        self.assertNotEqual(grey, rig.snapshot())

    def test_a_snapshot_differs_when_only_a_session_line_differs(self):
        rig = Rig(GREEN_PROBES)
        before = rig.snapshot()
        rig.probes = Observation(
            True, (SessionLine("claude", "online", "claude online quiet 9s"),)
        )

        self.assertNotEqual(before, rig.snapshot())


class LeftClickTests(unittest.TestCase):
    def click(self, rig):
        default_entry(rig.snapshot()).on_select()

    def test_a_click_on_green_opens_element_in_the_default_browser(self):
        rig = Rig(GREEN_PROBES)

        self.click(rig)

        self.assertEqual([settings.ELEMENT_URL], rig.opened_urls)
        self.assertEqual([], rig.view.notifications)

    def test_a_click_on_grey_notifies_and_opens_nothing(self):
        rig = Rig(GREY_PROBES)

        self.click(rig)

        self.assertEqual(
            [TEXTS.text("tray.notification_not_running")], rig.view.notifications
        )
        self.assertEqual([], rig.opened_urls)

    def test_a_click_on_red_notifies_and_opens_nothing(self):
        rig = Rig(ONLY_STACK_PROBES)

        self.click(rig)

        self.assertEqual(1, len(rig.view.notifications))
        self.assertEqual([], rig.opened_urls)

    def test_a_click_while_an_action_runs_notifies_and_opens_nothing(self):
        rig = Rig(GREEN_PROBES)
        rig.runner.begin(ActionKind.STOP)

        self.click(rig)

        self.assertEqual(1, len(rig.view.notifications))
        self.assertEqual([], rig.opened_urls)

    def test_a_browser_that_cannot_be_opened_is_reported_and_does_not_escape(self):
        rig = Rig(GREEN_PROBES)
        rig.open_url_failure = OSError("no browser")

        self.click(rig)

        self.assertEqual(["no browser"], [str(failure) for failure in rig.failures])


class ToggleTests(unittest.TestCase):
    def test_start_on_grey_runs_start_ps1(self):
        rig = Rig(GREY_PROBES)

        rig.entry(TEXTS.text("tray.start")).on_select()
        rig.spawn.run_all()

        self.assertEqual([START], rig.launcher.scripts)

    def test_stop_on_green_runs_stop_ps1(self):
        rig = Rig(GREEN_PROBES)

        rig.entry(TEXTS.text("tray.stop")).on_select()
        rig.spawn.run_all()

        self.assertEqual([STOP], rig.launcher.scripts)

    def test_an_accepted_action_asks_for_an_immediate_refresh(self):
        rig = Rig(GREY_PROBES)

        rig.entry(TEXTS.text("tray.start")).on_select()

        self.assertTrue(rig.event.flag)

    def test_after_the_action_begins_the_next_snapshot_is_yellow_with_the_toggle_disabled(
        self,
    ):
        rig = Rig(GREY_PROBES)
        rig.entry(TEXTS.text("tray.start")).on_select()

        snapshot = rig.snapshot()

        self.assertEqual(Colour.YELLOW, snapshot.colour)
        self.assertFalse(entry_with_text(snapshot, TEXTS.text("tray.starting")).enabled)

    def test_a_refused_second_action_does_not_ask_for_a_refresh(self):
        rig = Rig(GREY_PROBES)
        rig.entry(TEXTS.text("tray.start")).on_select()
        rig.event.clear()

        rig.entry(TEXTS.text("tray.starting")).on_select()

        self.assertFalse(rig.event.flag)
        self.assertEqual(1, len(rig.spawn.pending))

    def test_a_runner_that_cannot_start_its_thread_is_reported_not_raised(self):
        rig = Rig(GREY_PROBES)
        rig.spawn.failure = RuntimeError("can't start new thread")

        rig.entry(TEXTS.text("tray.start")).on_select()

        self.assertEqual(
            ["can't start new thread"], [str(failure) for failure in rig.failures]
        )


class OpenLogTests(unittest.TestCase):
    def test_open_log_opens_the_broker_log_with_the_default_handler(self):
        rig = Rig()

        rig.entry(TEXTS.text("tray.open_log")).on_select()

        self.assertEqual([settings.BROKER_LOG], rig.opened_files)

    def test_a_missing_log_is_reported_and_does_not_escape(self):
        rig = Rig()
        rig.open_file_failure = FileNotFoundError("broker.log")

        rig.entry(TEXTS.text("tray.open_log")).on_select()

        self.assertEqual(["broker.log"], [str(failure) for failure in rig.failures])


class ExitTests(unittest.TestCase):
    def test_exit_stops_the_icon(self):
        rig = Rig(GREEN_PROBES)

        rig.entry(TEXTS.text("tray.exit")).on_select()

        self.assertTrue(rig.view.stopped)

    def test_exit_stops_the_poll_loop(self):
        rig = Rig(GREEN_PROBES)

        rig.entry(TEXTS.text("tray.exit")).on_select()

        self.assertTrue(rig.signal.stopped)

    def test_exit_leaves_the_stand_alone(self):
        rig = Rig(GREEN_PROBES)

        rig.entry(TEXTS.text("tray.exit")).on_select()
        rig.spawn.run_all()

        self.assertEqual([], rig.launcher.scripts)
        self.assertIsNone(rig.runner.status().running)


class RefreshTests(unittest.TestCase):
    def test_the_first_refresh_shows_the_snapshot(self):
        rig = Rig(GREEN_PROBES)

        rig.controller.refresh()

        self.assertEqual([Colour.GREEN], [shown.colour for shown in rig.view.shown])

    def test_an_unchanged_stand_is_not_redrawn(self):
        rig = Rig(GREEN_PROBES)
        rig.controller.refresh()

        rig.controller.refresh()

        self.assertEqual(1, len(rig.view.shown))

    def test_a_changed_stand_is_redrawn(self):
        rig = Rig(GREEN_PROBES)
        rig.controller.refresh()
        rig.probes = GREY_PROBES

        rig.controller.refresh()

        self.assertEqual(
            [Colour.GREEN, Colour.GREY], [shown.colour for shown in rig.view.shown]
        )

    def test_the_snapshot_the_icon_opened_with_is_not_drawn_again(self):
        rig = Rig(GREEN_PROBES)
        rig.controller.opening_snapshot()

        rig.controller.refresh()

        self.assertEqual([], rig.view.shown)

    def test_a_failed_draw_is_tried_again_on_the_next_refresh(self):
        rig = Rig(GREEN_PROBES)
        rig.view.show_failure = OSError("shell is busy")
        with self.assertRaises(OSError):
            rig.controller.refresh()

        rig.controller.refresh()

        self.assertEqual(1, len(rig.view.shown))

    def test_a_click_acts_on_the_state_last_probed(self):
        rig = Rig(GREEN_PROBES)
        rig.controller.refresh()
        rig.probes = GREY_PROBES
        rig.controller.refresh()

        default_entry(rig.view.shown[-1]).on_select()

        self.assertEqual([], rig.opened_urls)
        self.assertEqual(1, len(rig.view.notifications))


class TrayEntryEqualityTests(unittest.TestCase):
    def test_entries_with_different_callbacks_but_the_same_look_are_equal(self):
        self.assertEqual(
            TrayEntry("Start", True, lambda: None),
            TrayEntry("Start", True, lambda: None),
        )

    def test_entries_with_different_text_are_different(self):
        self.assertNotEqual(TrayEntry("Start", True), TrayEntry("Stop", True))

    def test_entries_with_different_enabled_flags_are_different(self):
        self.assertNotEqual(TrayEntry("Start", True), TrayEntry("Start", False))


if __name__ == "__main__":
    unittest.main()
