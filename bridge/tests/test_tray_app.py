"""Task tray-03: the start-up sequence and the single-instance guard."""

import unittest

from quoroomtray import settings
from quoroomtray.app import TraySeams, run_tray
from quoroomtray.process import ScriptOutcome
from quoroomtray.texts import TrayTexts
from tests.tray_fakes import (
    GREEN_PROBES,
    GREY_PROBES,
    ONLY_BROKER_PROBES,
    ONLY_STACK_PROBES,
    ManualSpawn,
    ScriptedLauncher,
)
from tests.tray_shell_fakes import FakeClaim, FakeView, entry_with_text

TEXTS = TrayTexts("en")
POLL_SECONDS = 5.0


class Start:
    def __init__(self, claim=None, view=None, probes=GREEN_PROBES):
        self.claim = claim
        self.view = view or FakeView()
        self.probes = probes if isinstance(probes, list) else [probes]
        self.launcher = ScriptedLauncher(ScriptOutcome(0, "Done."))
        self.views_built = 0
        self.observations = 0
        self.spawn = ManualSpawn()
        self.failures = []
        self.on_observe = None
        self.clock_calls = 0
        self.failing_clock_call = None

    def build_view(self):
        self.views_built += 1
        return self.view

    def observe(self):
        self.observations += 1
        if self.on_observe is not None:
            self.on_observe(self.observations)
        return self.probes[min(self.observations, len(self.probes)) - 1]

    def clock(self):
        self.clock_calls += 1
        if self.clock_calls == self.failing_clock_call:
            raise RuntimeError("clock blew up")
        return self.observations * POLL_SECONDS

    def press_exit(self):
        entry_with_text(self.view.first, TEXTS.text("tray.exit")).on_select()

    def run(self):
        return run_tray(
            lambda: self.claim,
            self.build_view,
            self.observe,
            TEXTS,
            lambda url: None,
            lambda path: None,
            self.failures.append,
            TraySeams(self.spawn, self.launcher, self.clock, 0),
        )


class SingleInstanceTests(unittest.TestCase):
    def test_a_second_copy_exits_without_building_the_icon(self):
        start = Start(claim=None)

        exit_code = start.run()

        self.assertEqual(0, exit_code)
        self.assertEqual(0, start.views_built)

    def test_a_second_copy_does_not_probe_the_stand_or_start_polling(self):
        start = Start(claim=None)

        start.run()

        self.assertEqual(0, start.observations)
        self.assertEqual([], start.spawn.pending)

    def test_the_first_copy_builds_the_icon_and_runs_it(self):
        start = Start(claim=FakeClaim())

        start.run()

        self.assertEqual(1, start.views_built)
        self.assertIsNotNone(start.view.first)

    def test_the_claim_is_held_while_the_icon_runs_and_released_when_it_ends(self):
        claim = FakeClaim()
        held_while_running = []
        start = Start(
            claim=claim,
            view=FakeView(lambda view: held_while_running.append(claim.closed)),
        )

        start.run()

        self.assertEqual([False], held_while_running)
        self.assertTrue(claim.closed)

    def test_the_claim_is_released_even_when_the_icon_fails(self):
        claim = FakeClaim()

        def failing(view):
            raise RuntimeError("shell crashed")

        start = Start(claim=claim, view=FakeView(failing))

        with self.assertRaises(RuntimeError):
            start.run()

        self.assertTrue(claim.closed)


class StartUpSequenceTests(unittest.TestCase):
    def test_the_icon_opens_with_a_snapshot_probed_before_it_appears(self):
        start = Start(claim=FakeClaim())

        start.run()

        self.assertEqual(1, start.observations)

    def test_the_poll_loop_is_started_only_when_the_icon_is_ready(self):
        pending_when_ready = []
        start = Start(
            claim=FakeClaim(),
            view=FakeView(
                lambda view: pending_when_ready.append(len(start.spawn.pending))
            ),
        )

        start.run()

        self.assertEqual([1], pending_when_ready)

    def test_exit_from_the_menu_stops_the_icon_and_ends_the_queued_poll_loop(self):
        def choose_exit(view):
            entry_with_text(view.first, TEXTS.text("tray.exit")).on_select()

        start = Start(claim=FakeClaim(), view=FakeView(choose_exit))

        start.run()
        start.spawn.run_all()

        self.assertTrue(start.view.stopped)
        self.assertEqual(1, start.observations)
        self.assertEqual([], start.view.shown)


def run_polls_until(start, last_observation):
    def work(view):
        previous = start.on_observe

        def on_observe(count):
            if previous is not None:
                previous(count)
            if count == last_observation:
                start.press_exit()

        start.on_observe = on_observe
        start.spawn.run_all()
        start.spawn.run_all()

    start.view.while_running = work
    return start


REBOOT_SEQUENCE = [
    GREY_PROBES,
    GREY_PROBES,
    ONLY_STACK_PROBES,
    ONLY_STACK_PROBES,
]


class LoginRuleTests(unittest.TestCase):
    def run_polls(self, probes, last_observation):
        start = Start(claim=FakeClaim(), probes=probes)
        run_polls_until(start, last_observation)
        start.run()
        return start

    def test_the_reboot_sequence_runs_start_ps1_on_the_second_half_state_poll(self):
        start = self.run_polls(REBOOT_SEQUENCE, 5)

        self.assertEqual([settings.START_SCRIPT], start.launcher.scripts)

    def test_the_first_half_state_poll_alone_launches_nothing(self):
        start = self.run_polls(REBOOT_SEQUENCE, 3)

        self.assertEqual([], start.launcher.scripts)

    def test_the_icon_turns_yellow_on_the_poll_that_launched_start(self):
        start = self.run_polls(REBOOT_SEQUENCE, 5)

        starting = TEXTS.text("tray.status_starting")
        self.assertTrue(any(starting in shown.tooltip for shown in start.view.shown))

    def test_the_half_state_persisting_after_the_launch_does_not_launch_again(self):
        start = self.run_polls(REBOOT_SEQUENCE + [ONLY_STACK_PROBES] * 5, 9)

        self.assertEqual([settings.START_SCRIPT], start.launcher.scripts)

    def test_a_single_observation_at_start_up_never_launches_start(self):
        start = Start(claim=FakeClaim(), probes=ONLY_STACK_PROBES)

        def exit_at_once(view):
            start.press_exit()
            start.spawn.run_all()

        start.view.while_running = exit_at_once

        start.run()

        self.assertEqual(1, start.observations)
        self.assertEqual([], start.launcher.scripts)

    def test_a_stand_stopped_on_purpose_is_never_started(self):
        start = self.run_polls(GREY_PROBES, 8)

        self.assertEqual([], start.launcher.scripts)

    def test_a_running_stand_is_left_alone(self):
        start = self.run_polls(GREEN_PROBES, 8)

        self.assertEqual([], start.launcher.scripts)

    def test_a_broker_without_the_stack_is_left_alone(self):
        start = self.run_polls(ONLY_BROKER_PROBES, 8)

        self.assertEqual([], start.launcher.scripts)

    def test_a_manual_start_passing_through_the_half_state_is_left_alone(self):
        sequence = [GREY_PROBES, ONLY_STACK_PROBES, GREEN_PROBES, ONLY_STACK_PROBES]
        start = self.run_polls(sequence + [ONLY_STACK_PROBES] * 4, 8)

        self.assertEqual([], start.launcher.scripts)

    def test_no_second_copy_applies_the_login_rule(self):
        start = Start(claim=None, probes=ONLY_STACK_PROBES)

        start.run()
        start.spawn.run_all()

        self.assertEqual([], start.launcher.scripts)
        self.assertEqual(0, start.observations)

    def test_a_failing_login_rule_is_reported_and_the_icon_still_opens(self):
        start = Start(claim=FakeClaim())
        start.failing_clock_call = 2

        start.run()

        self.assertEqual(["clock blew up"], [str(f) for f in start.failures])
        self.assertIsNotNone(start.view.first)


if __name__ == "__main__":
    unittest.main()
