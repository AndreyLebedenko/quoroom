"""Task tray-03: the poll loop, the refresh signal and the failure guard."""

import threading
import unittest

from quoroomtray import settings
from quoroomtray.actions import ActionKind, ActionResult
from quoroomtray.app import refresh_after_action
from quoroomtray.guard import guarded
from quoroomtray.refresh import PollLoop, RefreshSignal
from quoroomtray.runner import ScriptRunner
from tests.tray_fakes import ManualSpawn, ScriptedLauncher
from tests.tray_shell_fakes import FlagEvent

DONE = ActionResult(ActionKind.START, 0, "Done.")


class PollLoopTests(unittest.TestCase):
    def setUp(self):
        self.event = FlagEvent()
        self.signal = RefreshSignal(self.event)
        self.refreshes = 0
        self.failures = []

    def loop(self, refresh, interval=settings.POLL_INTERVAL_SECONDS):
        return PollLoop(refresh, self.signal, self.failures.append, interval)

    def stop_after(self, count, then=lambda: None):
        def refresh():
            self.refreshes += 1
            then()
            if self.refreshes == count:
                self.signal.stop()

        return refresh

    def test_the_poll_interval_is_five_seconds_by_default(self):
        self.loop(self.stop_after(2)).run()

        self.assertEqual([5, 5], [timeout for timeout, _ in self.event.waits])

    def test_the_loop_refreshes_once_per_wait_until_stopped(self):
        self.loop(self.stop_after(3)).run()

        self.assertEqual(3, self.refreshes)

    def test_a_stop_before_the_first_refresh_refreshes_nothing(self):
        self.signal.stop()

        self.loop(self.stop_after(1)).run()

        self.assertEqual(0, self.refreshes)

    def test_a_stop_during_the_wait_ends_the_loop_without_another_refresh(self):
        self.event.on_wait = self.signal.stop

        self.loop(self.stop_after(10)).run()

        self.assertEqual(1, self.refreshes)

    def test_a_stop_that_lands_while_the_loop_re_arms_is_not_lost(self):
        self.event.on_clear = self.signal.stop

        self.loop(self.stop_after(10)).run()

        self.assertEqual(0, self.refreshes)

    def test_a_request_made_during_a_refresh_wakes_the_next_wait_at_once(self):
        self.loop(self.stop_after(2, then=self.signal.request)).run()

        self.assertTrue(self.event.waits[0][1])

    def test_a_wait_with_no_request_is_not_a_wake_up(self):
        self.loop(self.stop_after(2)).run()

        self.assertFalse(self.event.waits[0][1])

    def test_a_refresh_that_raises_is_reported_and_the_polling_goes_on(self):
        def refresh():
            self.refreshes += 1
            if self.refreshes == 1:
                raise ConnectionError("probe blew up")
            self.signal.stop()

        self.loop(refresh).run()

        self.assertEqual(2, self.refreshes)
        self.assertEqual(["probe blew up"], [str(failure) for failure in self.failures])


class RealThreadWakeTests(unittest.TestCase):
    def test_a_request_refreshes_at_once_instead_of_after_the_poll_interval(self):
        signal = RefreshSignal()
        first_refresh = threading.Event()
        second_refresh = threading.Event()
        calls = []

        def refresh():
            calls.append(1)
            (first_refresh if len(calls) == 1 else second_refresh).set()

        loop = PollLoop(refresh, signal, lambda failure: None, interval=600)
        thread = threading.Thread(target=loop.run, daemon=True)
        thread.start()
        self.assertTrue(first_refresh.wait(5))

        signal.request()

        self.assertTrue(second_refresh.wait(5))
        signal.stop()
        thread.join(5)
        self.assertFalse(thread.is_alive())


class GuardTests(unittest.TestCase):
    def test_an_exception_from_the_action_does_not_escape(self):
        def failing():
            raise RuntimeError("boom")

        guarded(failing, lambda failure: None)()

    def test_the_exception_is_handed_to_the_report(self):
        reported = []

        def failing():
            raise RuntimeError("boom")

        guarded(failing, reported.append)()

        self.assertEqual(["boom"], [str(failure) for failure in reported])

    def test_arguments_reach_the_action(self):
        seen = []

        guarded(lambda *args, **kwargs: seen.append((args, kwargs)), print)(1, a=2)

        self.assertEqual([((1,), {"a": 2})], seen)

    def test_a_report_that_raises_does_not_escape_either(self):
        def failing():
            raise RuntimeError("boom")

        def failing_report(failure):
            raise OSError("log is read-only")

        guarded(failing, failing_report)()


class FinishCallbackTests(unittest.TestCase):
    def test_a_finished_action_requests_a_refresh(self):
        event = FlagEvent()

        refresh_after_action(RefreshSignal(event), lambda failure: None)(DONE)

        self.assertTrue(event.flag)

    def test_a_signal_that_raises_does_not_escape_the_callback(self):
        class BrokenSignal:
            def request(self):
                raise RuntimeError("signal is gone")

        reported = []

        refresh_after_action(BrokenSignal(), reported.append)(DONE)

        self.assertEqual(["signal is gone"], [str(failure) for failure in reported])

    def test_the_runner_worker_survives_a_callback_that_raises(self):
        class BrokenSignal:
            def request(self):
                raise RuntimeError("signal is gone")

        spawn = ManualSpawn()
        runner = ScriptRunner(
            {ActionKind.START: "start.ps1"},
            launch=ScriptedLauncher(),
            spawn=spawn,
            on_finished=refresh_after_action(BrokenSignal(), lambda failure: None),
        )
        runner.begin(ActionKind.START)

        spawn.run_all()

        self.assertTrue(runner.status().last_result.succeeded)


if __name__ == "__main__":
    unittest.main()
