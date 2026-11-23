"""Task tray-02: the login rule of story Q1, option (a)."""

import unittest

from quoroomtray.actions import ActionKind
from quoroomtray.login import apply_login_rule, login_action
from quoroomtray.runner import ScriptRunner
from tests.tray_fakes import (
    GREEN_PROBES,
    GREY_PROBES,
    ONLY_BROKER_PROBES,
    ONLY_STACK_PROBES,
    ManualSpawn,
    ScriptedLauncher,
)


class LoginDecisionTests(unittest.TestCase):
    def test_the_stack_up_after_a_login_with_no_broker_runs_start(self):
        self.assertEqual(ActionKind.START, login_action(ONLY_STACK_PROBES))

    def test_a_stand_stopped_on_purpose_stays_stopped(self):
        self.assertIsNone(login_action(GREY_PROBES))

    def test_a_stand_that_is_already_green_is_left_alone(self):
        self.assertIsNone(login_action(GREEN_PROBES))

    def test_a_broker_that_survived_without_the_stack_is_left_alone(self):
        self.assertIsNone(login_action(ONLY_BROKER_PROBES))


class LoginApplicationTests(unittest.TestCase):
    def runner(self):
        self.spawn = ManualSpawn()
        self.launcher = ScriptedLauncher()
        return ScriptRunner(
            {ActionKind.START: "start.ps1", ActionKind.STOP: "stop.ps1"},
            launch=self.launcher,
            spawn=self.spawn,
        )

    def test_the_half_state_starts_start_ps1_through_the_runner(self):
        script_runner = self.runner()

        launched = apply_login_rule(lambda: ONLY_STACK_PROBES, script_runner)
        self.spawn.run_all()

        self.assertEqual(ActionKind.START, launched)
        self.assertEqual(["start.ps1"], self.launcher.scripts)

    def test_any_other_combination_launches_nothing(self):
        for name, probes in (
            ("grey", GREY_PROBES),
            ("green", GREEN_PROBES),
            ("broker only", ONLY_BROKER_PROBES),
        ):
            with self.subTest(probes=name):
                script_runner = self.runner()

                launched = apply_login_rule(lambda p=probes: p, script_runner)
                self.spawn.run_all()

                self.assertIsNone(launched)
                self.assertEqual([], self.launcher.scripts)
                self.assertIsNone(script_runner.status().running)

    def test_the_rule_observes_once_per_application(self):
        calls = []

        def observe():
            calls.append(1)
            return GREEN_PROBES

        apply_login_rule(observe, self.runner())

        self.assertEqual(1, len(calls))

    def test_the_rule_launches_nothing_when_an_action_is_already_running(self):
        script_runner = self.runner()
        script_runner.begin(ActionKind.STOP)

        launched = apply_login_rule(lambda: ONLY_STACK_PROBES, script_runner)

        self.assertIsNone(launched)


if __name__ == "__main__":
    unittest.main()
