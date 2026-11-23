"""Task tray-03: the start-up sequence and the single-instance guard."""

import unittest

from quoroomtray.app import run_tray
from quoroomtray.texts import TrayTexts
from tests.tray_fakes import GREEN_PROBES, ManualSpawn
from tests.tray_shell_fakes import FakeClaim, FakeView, entry_with_text

TEXTS = TrayTexts("en")


class Start:
    def __init__(self, claim=None, view=None):
        self.claim = claim
        self.view = view or FakeView()
        self.views_built = 0
        self.observations = 0
        self.spawn = ManualSpawn()
        self.failures = []

    def build_view(self):
        self.views_built += 1
        return self.view

    def observe(self):
        self.observations += 1
        return GREEN_PROBES

    def run(self):
        return run_tray(
            lambda: self.claim,
            self.build_view,
            self.observe,
            TEXTS,
            lambda url: None,
            lambda path: None,
            self.failures.append,
            self.spawn,
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


if __name__ == "__main__":
    unittest.main()
