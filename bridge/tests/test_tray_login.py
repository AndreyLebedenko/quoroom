"""Task tray-04: the login rule of story Q1, armed for a window after start."""

import re
import unittest
from pathlib import Path

from quoroomtray import settings
from quoroomtray.actions import ActionKind
from quoroomtray.login import LoginRule
from quoroomtray.login_observer import LoginRuleObserver
from quoroomtray.runner import ScriptRunner
from tests.tray_fakes import (
    GREEN_PROBES,
    GREY_PROBES,
    ONLY_BROKER_PROBES,
    ONLY_STACK_PROBES,
    ManualSpawn,
    ScriptedLauncher,
)

START_PS1 = Path(__file__).resolve().parents[2] / "start.ps1"
WINDOW = settings.LOGIN_RULE_WINDOW_SECONDS
POLL = settings.POLL_INTERVAL_SECONDS


def decisions(observations):
    rule = LoginRule(0.0)
    return [
        rule.should_start(observation, index * POLL, False)
        for index, observation in enumerate(observations)
    ]


class LoginRuleDecisionTests(unittest.TestCase):
    def test_the_reboot_scenario_starts_on_the_second_half_state_poll(self):
        sequence = [GREY_PROBES, GREY_PROBES, ONLY_STACK_PROBES, ONLY_STACK_PROBES]

        self.assertEqual([False, False, False, True], decisions(sequence))

    def test_a_stand_stopped_on_purpose_stays_stopped_for_the_whole_window(self):
        polls = int(WINDOW / POLL)

        self.assertEqual([False] * polls, decisions([GREY_PROBES] * polls))

    def test_grey_polls_keep_the_rule_armed(self):
        rule = LoginRule(0.0)

        rule.should_start(GREY_PROBES, 0.0, False)
        rule.should_start(GREY_PROBES, POLL, False)

        self.assertTrue(rule.armed)

    def test_a_running_stand_disarms_the_rule_without_acting(self):
        sequence = [GREEN_PROBES, ONLY_STACK_PROBES, ONLY_STACK_PROBES]

        self.assertEqual([False, False, False], decisions(sequence))

    def test_a_broker_without_the_stack_disarms_the_rule_without_acting(self):
        sequence = [ONLY_BROKER_PROBES, ONLY_STACK_PROBES, ONLY_STACK_PROBES]

        self.assertEqual([False, False, False], decisions(sequence))

    def test_a_manual_start_passing_through_the_half_state_is_left_alone(self):
        sequence = [GREY_PROBES, ONLY_STACK_PROBES, GREEN_PROBES, ONLY_STACK_PROBES]

        self.assertEqual([False] * 4, decisions(sequence))

    def test_a_half_state_followed_by_grey_resets_the_count(self):
        sequence = [ONLY_STACK_PROBES, GREY_PROBES, ONLY_STACK_PROBES]

        self.assertEqual([False] * 3, decisions(sequence))

    def test_the_count_starts_again_after_a_reset(self):
        sequence = [
            ONLY_STACK_PROBES,
            GREY_PROBES,
            ONLY_STACK_PROBES,
            ONLY_STACK_PROBES,
        ]

        self.assertEqual([False, False, False, True], decisions(sequence))

    def test_the_rule_fires_once_and_is_disarmed_afterwards(self):
        rule = LoginRule(0.0)

        results = [
            rule.should_start(ONLY_STACK_PROBES, i * POLL, False) for i in range(6)
        ]

        self.assertEqual([False, True, False, False, False, False], results)
        self.assertFalse(rule.armed)

    def test_a_fired_rule_is_never_rearmed_by_a_later_grey_poll(self):
        rule = LoginRule(0.0)
        rule.should_start(ONLY_STACK_PROBES, 0.0, False)
        rule.should_start(ONLY_STACK_PROBES, POLL, False)

        rule.should_start(GREY_PROBES, 2 * POLL, False)

        self.assertFalse(rule.armed)

    def test_a_half_state_confirmed_after_the_window_does_nothing(self):
        rule = LoginRule(0.0)

        first = rule.should_start(ONLY_STACK_PROBES, WINDOW - POLL, False)
        second = rule.should_start(ONLY_STACK_PROBES, WINDOW, False)

        self.assertEqual((False, False), (first, second))
        self.assertFalse(rule.armed)

    def test_the_last_poll_inside_the_window_still_counts(self):
        rule = LoginRule(0.0)

        rule.should_start(ONLY_STACK_PROBES, WINDOW - 2 * POLL, False)
        fired = rule.should_start(ONLY_STACK_PROBES, WINDOW - POLL, False)

        self.assertTrue(fired)

    def test_the_window_is_measured_from_the_start_of_the_tray(self):
        rule = LoginRule(1000.0)

        rule.should_start(ONLY_STACK_PROBES, 1000.0 + WINDOW - 2 * POLL, False)
        fired = rule.should_start(ONLY_STACK_PROBES, 1000.0 + WINDOW - POLL, False)

        self.assertTrue(fired)

    def test_an_action_already_seen_disarms_the_rule_without_acting(self):
        rule = LoginRule(0.0)
        rule.should_start(GREY_PROBES, 0.0, False)

        pressed = rule.should_start(ONLY_STACK_PROBES, POLL, True)
        later = [
            rule.should_start(ONLY_STACK_PROBES, POLL * (i + 2), False)
            for i in range(3)
        ]

        self.assertFalse(pressed)
        self.assertEqual([False] * 3, later)
        self.assertFalse(rule.armed)


class LoginRuleSettingsTests(unittest.TestCase):
    def docker_wait_of_start_ps1(self):
        text = START_PS1.read_text(encoding="utf-8-sig")
        return int(re.search(r"\$dockerWaitSeconds\s*=\s*(\d+)", text).group(1))

    def test_the_window_covers_the_docker_desktop_wait_of_start_ps1_and_some_polls(
        self,
    ):
        polls_to_see_and_confirm_the_half_state = (
            settings.LOGIN_RULE_CONFIRMING_POLLS + 1
        )

        needed = (
            self.docker_wait_of_start_ps1()
            + polls_to_see_and_confirm_the_half_state * POLL
        )

        self.assertGreaterEqual(WINDOW, needed)

    def test_the_half_state_needs_more_than_one_poll(self):
        self.assertGreaterEqual(settings.LOGIN_RULE_CONFIRMING_POLLS, 2)


class LoginRuleObserverTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.spawn = ManualSpawn()
        self.launcher = ScriptedLauncher()
        self.runner = ScriptRunner(
            {ActionKind.START: "start.ps1", ActionKind.STOP: "stop.ps1"},
            launch=self.launcher,
            spawn=self.spawn,
        )
        self.failures = []
        self.sequence = []
        self.polls = 0

    def observe(self):
        observation = self.sequence[min(self.polls, len(self.sequence) - 1)]
        self.polls += 1
        return observation

    def clock(self):
        return self.now

    def observer(self):
        return LoginRuleObserver(
            self.observe,
            LoginRule(self.now),
            self.runner,
            self.clock,
            self.failures.append,
        )

    def poll_through(self, observer, count):
        for _ in range(count):
            observer()
            self.now += POLL
        self.spawn.run_all()

    def test_the_reboot_scenario_launches_start_ps1_at_the_fourth_poll(self):
        self.sequence = [GREY_PROBES, GREY_PROBES, ONLY_STACK_PROBES, ONLY_STACK_PROBES]
        observer = self.observer()

        self.poll_through(observer, 3)
        self.assertEqual([], self.launcher.scripts)
        self.poll_through(observer, 1)

        self.assertEqual(["start.ps1"], self.launcher.scripts)

    def test_the_poll_that_launches_start_leaves_the_runner_running_for_the_icon(
        self,
    ):
        self.sequence = [ONLY_STACK_PROBES]
        observer = self.observer()

        observer()
        observer()

        self.assertEqual(ActionKind.START, self.runner.status().running)

    def test_the_observation_is_returned_unchanged(self):
        self.sequence = [ONLY_STACK_PROBES]

        self.assertIs(ONLY_STACK_PROBES, self.observer()())

    def test_a_button_pressed_before_the_half_state_disarms_the_rule(self):
        self.sequence = [GREY_PROBES, ONLY_STACK_PROBES]
        observer = self.observer()
        observer()
        self.runner.begin(ActionKind.STOP)

        self.poll_through(observer, 5)

        self.assertEqual(["stop.ps1"], self.launcher.scripts)

    def test_a_button_press_that_has_already_finished_still_disarms_the_rule(self):
        self.sequence = [GREY_PROBES, ONLY_STACK_PROBES]
        observer = self.observer()
        observer()
        self.runner.begin(ActionKind.START)
        self.spawn.run_all()

        self.poll_through(observer, 5)

        self.assertEqual(["start.ps1"], self.launcher.scripts)

    def test_a_failing_rule_is_reported_and_the_observation_still_arrives(self):
        self.sequence = [ONLY_STACK_PROBES]

        def broken_clock():
            raise RuntimeError("clock blew up")

        observer = LoginRuleObserver(
            self.observe,
            LoginRule(0.0),
            self.runner,
            broken_clock,
            self.failures.append,
        )

        result = observer()

        self.assertIs(ONLY_STACK_PROBES, result)
        self.assertEqual(["clock blew up"], [str(f) for f in self.failures])


if __name__ == "__main__":
    unittest.main()
