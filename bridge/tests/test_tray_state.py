"""Task tray-02: the colour contract of the story, one test per situation."""

import unittest

from quoroomtray.actions import ActionKind, ActionStatus
from quoroomtray.state import Colour, RedReason, StandState, stand_state
from tests.tray_fakes import (
    ALL_PROBES,
    GREEN_PROBES,
    GREY_PROBES,
    NO_ACTION,
    ONLY_BROKER_PROBES,
    ONLY_STACK_PROBES,
    finished,
    running,
)


class ProbeDrivenColourTests(unittest.TestCase):
    def test_nothing_answering_is_grey_because_the_stand_is_stopped_on_purpose(self):
        self.assertEqual(StandState(Colour.GREY), stand_state(GREY_PROBES, NO_ACTION))

    def test_the_stack_and_the_broker_both_answering_is_green(self):
        self.assertEqual(StandState(Colour.GREEN), stand_state(GREEN_PROBES, NO_ACTION))

    def test_the_broker_killed_while_the_stack_runs_is_red_with_a_reason(self):
        state = stand_state(ONLY_STACK_PROBES, NO_ACTION)

        self.assertEqual(Colour.RED, state.colour)
        self.assertEqual(RedReason.ONLY_STACK_ANSWERS, state.reason)

    def test_docker_down_while_the_broker_keeps_running_is_red_with_a_reason(self):
        state = stand_state(ONLY_BROKER_PROBES, NO_ACTION)

        self.assertEqual(Colour.RED, state.colour)
        self.assertEqual(RedReason.ONLY_BROKER_ANSWERS, state.reason)


class ActionDrivenColourTests(unittest.TestCase):
    def test_a_running_start_is_yellow_whatever_the_probes_show(self):
        for name, probes in ALL_PROBES.items():
            with self.subTest(probes=name):
                state = stand_state(probes, running(ActionKind.START))

                self.assertEqual(Colour.YELLOW, state.colour)
                self.assertEqual(ActionKind.START, state.running)

    def test_a_running_stop_is_yellow_whatever_the_probes_show(self):
        for name, probes in ALL_PROBES.items():
            with self.subTest(probes=name):
                state = stand_state(probes, running(ActionKind.STOP))

                self.assertEqual(Colour.YELLOW, state.colour)
                self.assertEqual(ActionKind.STOP, state.running)

    def test_a_failed_start_with_nothing_answering_is_red_with_the_failure(self):
        actions = finished(ActionKind.START, 1, "ERROR: docker did not start")

        state = stand_state(GREY_PROBES, actions)

        self.assertEqual(Colour.RED, state.colour)
        self.assertEqual(RedReason.ACTION_FAILED, state.reason)
        self.assertEqual(actions.last_result, state.failure)

    def test_a_failed_stop_with_the_stand_still_up_is_red_with_the_failure(self):
        actions = finished(ActionKind.STOP, 1, "ERROR: compose down failed")

        state = stand_state(GREEN_PROBES, actions)

        self.assertEqual(Colour.RED, state.colour)
        self.assertEqual(RedReason.ACTION_FAILED, state.reason)

    def test_a_failed_start_with_a_half_state_names_the_failure_not_the_half_state(
        self,
    ):
        for name, probes in (
            ("only stack", ONLY_STACK_PROBES),
            ("only broker", ONLY_BROKER_PROBES),
        ):
            with self.subTest(probes=name):
                actions = finished(ActionKind.START, 2, "ERROR: broker exited")

                state = stand_state(probes, actions)

                self.assertEqual(RedReason.ACTION_FAILED, state.reason)

    def test_a_failed_stop_with_a_half_state_names_the_failure(self):
        actions = finished(ActionKind.STOP, 1, "ERROR: compose down failed")

        state = stand_state(ONLY_STACK_PROBES, actions)

        self.assertEqual(RedReason.ACTION_FAILED, state.reason)

    def test_a_failed_start_repaired_from_a_console_is_green_on_the_next_poll(self):
        actions = finished(ActionKind.START, 1, "ERROR: docker did not start")

        self.assertEqual(StandState(Colour.GREEN), stand_state(GREEN_PROBES, actions))

    def test_a_failed_stop_finished_from_a_console_is_grey_on_the_next_poll(self):
        actions = finished(ActionKind.STOP, 1, "ERROR: compose down failed")

        self.assertEqual(StandState(Colour.GREY), stand_state(GREY_PROBES, actions))

    def test_a_failed_start_is_not_cleared_by_the_stand_being_grey(self):
        actions = finished(ActionKind.START, 1, "ERROR: docker did not start")

        self.assertEqual(Colour.RED, stand_state(GREY_PROBES, actions).colour)

    def test_a_failed_stop_is_not_cleared_by_the_stand_being_green(self):
        actions = finished(ActionKind.STOP, 1, "ERROR: compose down failed")

        self.assertEqual(Colour.RED, stand_state(GREEN_PROBES, actions).colour)

    def test_a_new_action_turns_a_failed_one_yellow_while_it_runs(self):
        failed = finished(ActionKind.START, 1, "ERROR: docker did not start")
        again = ActionStatus(ActionKind.START, failed.last_result)

        self.assertEqual(Colour.YELLOW, stand_state(GREY_PROBES, again).colour)

    def test_a_successful_action_after_a_failed_one_clears_the_red(self):
        succeeded = finished(ActionKind.START, 0, "Done.")

        self.assertEqual(Colour.GREEN, stand_state(GREEN_PROBES, succeeded).colour)

    def test_a_successful_stop_leaves_the_probes_to_say_grey(self):
        succeeded = finished(ActionKind.STOP, 0, "Stopped.")

        self.assertEqual(Colour.GREY, stand_state(GREY_PROBES, succeeded).colour)

    def test_a_successful_action_does_not_hide_a_half_state_the_probes_show(self):
        succeeded = finished(ActionKind.START, 0, "Done.")

        state = stand_state(ONLY_STACK_PROBES, succeeded)

        self.assertEqual(RedReason.ONLY_STACK_ANSWERS, state.reason)

    def test_an_exit_code_other_than_zero_is_a_failure(self):
        for code in (1, 2, -1, 255):
            with self.subTest(code=code):
                self.assertFalse(finished(ActionKind.START, code).last_result.succeeded)

    def test_exit_code_zero_is_a_success(self):
        self.assertTrue(finished(ActionKind.START, 0).last_result.succeeded)


if __name__ == "__main__":
    unittest.main()
