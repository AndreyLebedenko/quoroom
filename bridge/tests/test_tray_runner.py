"""Task tray-02: the script runner and the hidden PowerShell launch."""

import subprocess
import unittest
from pathlib import Path

from quoroomtray import process, runner, settings
from quoroomtray.actions import ActionKind, ActionResult
from quoroomtray.process import (
    CREATE_NO_WINDOW,
    ScriptOutcome,
    last_output_line,
    powershell_command,
    run_powershell_script,
)
from quoroomtray.runner import ScriptRunner
from tests.tray_fakes import ManualSpawn, ScriptedLauncher

START = Path("C:/stand/start.ps1")
STOP = Path("C:/stand/stop.ps1")
SCRIPTS = {ActionKind.START: START, ActionKind.STOP: STOP}


def runner_with(launcher, spawn=None, on_finished=None):
    return ScriptRunner(
        SCRIPTS,
        launch=launcher,
        spawn=spawn or ManualSpawn(),
        on_finished=on_finished,
    )


class OneActionAtATimeTests(unittest.TestCase):
    def test_a_fresh_runner_is_idle_with_no_result(self):
        status = runner_with(ScriptedLauncher()).status()

        self.assertIsNone(status.running)
        self.assertIsNone(status.last_result)

    def test_beginning_an_action_reports_it_as_running_before_the_script_ends(self):
        spawn = ManualSpawn()
        script_runner = runner_with(ScriptedLauncher(), spawn)

        accepted = script_runner.begin(ActionKind.START)

        self.assertTrue(accepted)
        self.assertEqual(ActionKind.START, script_runner.status().running)

    def test_the_script_is_not_launched_until_the_thread_runs(self):
        launcher = ScriptedLauncher()
        runner_with(launcher).begin(ActionKind.START)

        self.assertEqual([], launcher.scripts)

    def test_a_second_action_is_refused_while_one_runs(self):
        launcher = ScriptedLauncher()
        spawn = ManualSpawn()
        script_runner = runner_with(launcher, spawn)
        script_runner.begin(ActionKind.START)

        refused = script_runner.begin(ActionKind.STOP)
        spawn.run_all()

        self.assertFalse(refused)
        self.assertEqual([START], launcher.scripts)

    def test_the_same_action_twice_is_also_refused_while_it_runs(self):
        spawn = ManualSpawn()
        script_runner = runner_with(ScriptedLauncher(), spawn)
        script_runner.begin(ActionKind.START)

        self.assertFalse(script_runner.begin(ActionKind.START))
        self.assertEqual(1, len(spawn.pending))

    def test_a_new_action_is_accepted_once_the_previous_one_ended(self):
        spawn = ManualSpawn()
        script_runner = runner_with(ScriptedLauncher(), spawn)
        script_runner.begin(ActionKind.START)
        spawn.run_all()

        self.assertTrue(script_runner.begin(ActionKind.STOP))


class ScriptSelectionTests(unittest.TestCase):
    def test_start_runs_start_ps1(self):
        launcher = ScriptedLauncher()
        spawn = ManualSpawn()
        runner_with(launcher, spawn).begin(ActionKind.START)

        spawn.run_all()

        self.assertEqual([START], launcher.scripts)

    def test_stop_runs_stop_ps1(self):
        launcher = ScriptedLauncher()
        spawn = ManualSpawn()
        runner_with(launcher, spawn).begin(ActionKind.STOP)

        spawn.run_all()

        self.assertEqual([STOP], launcher.scripts)

    def test_by_default_the_scripts_are_the_ones_in_the_repository_root(self):
        self.assertEqual(
            {
                ActionKind.START: settings.REPO_ROOT / "start.ps1",
                ActionKind.STOP: settings.REPO_ROOT / "stop.ps1",
            },
            dict(runner.STAND_SCRIPTS),
        )
        self.assertTrue(settings.START_SCRIPT.is_file())
        self.assertTrue(settings.STOP_SCRIPT.is_file())


class ResultTests(unittest.TestCase):
    def finish(
        self, outcome=None, failure=None, kind=ActionKind.START, on_finished=None
    ):
        spawn = ManualSpawn()
        script_runner = runner_with(
            ScriptedLauncher(outcome, failure), spawn, on_finished
        )
        script_runner.begin(kind)
        spawn.run_all()
        return script_runner

    def test_a_script_that_exits_zero_is_a_success_and_the_runner_is_idle_again(self):
        script_runner = self.finish(ScriptOutcome(0, "==> Done\nDone. Element Web\n"))

        status = script_runner.status()

        self.assertIsNone(status.running)
        self.assertEqual(
            ActionResult(ActionKind.START, 0, "Done. Element Web"), status.last_result
        )

    def test_a_script_that_exits_non_zero_is_a_failure_with_its_last_line_as_reason(
        self,
    ):
        outcome = ScriptOutcome(1, "==> Starting\nERROR: docker was not found\n\n")

        result = self.finish(outcome).status().last_result

        self.assertFalse(result.succeeded)
        self.assertEqual(1, result.exit_code)
        self.assertEqual("ERROR: docker was not found", result.last_line)

    def test_the_failed_stop_keeps_its_kind(self):
        result = self.finish(ScriptOutcome(1, "ERROR: x"), kind=ActionKind.STOP)

        self.assertEqual(ActionKind.STOP, result.status().last_result.kind)

    def test_a_script_that_cannot_be_launched_is_a_failure_with_the_error_text(self):
        failure = FileNotFoundError("powershell.exe not found")

        result = self.finish(failure=failure).status().last_result

        self.assertFalse(result.succeeded)
        self.assertEqual("powershell.exe not found", result.last_line)

    def test_the_runner_goes_idle_even_when_the_launcher_blows_up(self):
        script_runner = self.finish(failure=RuntimeError("boom"))

        self.assertIsNone(script_runner.status().running)

    def test_the_previous_result_survives_while_the_next_action_runs(self):
        spawn = ManualSpawn()
        script_runner = runner_with(
            ScriptedLauncher(ScriptOutcome(1, "ERROR: x")), spawn
        )
        script_runner.begin(ActionKind.START)
        spawn.run_all()

        script_runner.begin(ActionKind.START)

        self.assertEqual(1, script_runner.status().last_result.exit_code)
        self.assertEqual(ActionKind.START, script_runner.status().running)

    def test_the_next_result_replaces_the_previous_one(self):
        spawn = ManualSpawn()
        launcher = ScriptedLauncher(ScriptOutcome(1, "ERROR: x"))
        script_runner = runner_with(launcher, spawn)
        script_runner.begin(ActionKind.START)
        spawn.run_all()
        launcher.outcome = ScriptOutcome(0, "Done.")
        script_runner.begin(ActionKind.START)
        spawn.run_all()

        self.assertTrue(script_runner.status().last_result.succeeded)

    def test_the_finish_callback_gets_the_result_after_the_runner_is_idle(self):
        seen = []
        spawn = ManualSpawn()
        script_runner = runner_with(
            ScriptedLauncher(ScriptOutcome(0, "Done.")),
            spawn,
            on_finished=lambda result: seen.append(
                (result, script_runner.status().running)
            ),
        )
        script_runner.begin(ActionKind.START)

        spawn.run_all()

        self.assertEqual([(ActionResult(ActionKind.START, 0, "Done."), None)], seen)

    def test_a_thread_that_cannot_be_started_leaves_the_runner_idle_and_raises(self):
        spawn = ManualSpawn(failure=RuntimeError("can't start new thread"))
        script_runner = runner_with(ScriptedLauncher(), spawn)

        with self.assertRaises(RuntimeError):
            script_runner.begin(ActionKind.START)

        self.assertIsNone(script_runner.status().running)
        self.assertIsNone(script_runner.status().last_result)


class DaemonThreadTests(unittest.TestCase):
    def test_the_default_spawner_runs_the_work_on_another_daemon_thread(self):
        import threading

        done = threading.Event()
        seen = {}

        def work():
            seen["thread"] = threading.current_thread()
            done.set()

        runner.spawn_daemon_thread(work)

        self.assertTrue(done.wait(5))
        self.assertIsNot(threading.main_thread(), seen["thread"])
        self.assertTrue(seen["thread"].daemon)


class LastOutputLineTests(unittest.TestCase):
    def test_the_last_non_empty_line_is_taken(self):
        self.assertEqual("c", last_output_line("a\nb\nc\n\n  \n"))

    def test_windows_line_endings_are_handled(self):
        self.assertEqual("c", last_output_line("a\r\nb\r\nc\r\n"))

    def test_surrounding_blanks_are_trimmed(self):
        self.assertEqual("done", last_output_line("  done  \n"))

    def test_output_without_text_gives_an_empty_line(self):
        self.assertEqual("", last_output_line(" \n\n"))

    def test_empty_output_gives_an_empty_line(self):
        self.assertEqual("", last_output_line(""))


class PowerShellLaunchTests(unittest.TestCase):
    def run_fake(self, raw=b"", code=0, encoding="utf-8"):
        calls = []

        def fake_run(command, **options):
            calls.append((command, options))
            return subprocess.CompletedProcess(command, code, stdout=raw)

        outcome = run_powershell_script(START, run=fake_run, encoding=encoding)
        return outcome, calls

    def test_the_command_is_powershell_without_profile_bypassing_the_policy(self):
        self.assertEqual(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(START),
            ],
            powershell_command(START),
        )

    def test_the_script_runs_through_that_command(self):
        _, calls = self.run_fake()

        self.assertEqual(powershell_command(START), calls[0][0])

    def test_no_console_window_is_created(self):
        _, calls = self.run_fake()

        self.assertEqual(CREATE_NO_WINDOW, calls[0][1]["creationflags"])
        self.assertEqual(0x08000000, CREATE_NO_WINDOW)

    def test_standard_input_is_closed_because_pythonw_has_none(self):
        _, calls = self.run_fake()

        self.assertIs(subprocess.DEVNULL, calls[0][1]["stdin"])

    def test_errors_are_merged_into_the_output_that_is_read(self):
        _, calls = self.run_fake()

        self.assertIs(subprocess.PIPE, calls[0][1]["stdout"])
        self.assertIs(subprocess.STDOUT, calls[0][1]["stderr"])

    def test_the_exit_code_and_the_decoded_output_are_returned(self):
        outcome, _ = self.run_fake(b"line one\r\nline two\r\n", code=3)

        self.assertEqual(ScriptOutcome(3, "line one\r\nline two\r\n"), outcome)

    def test_output_is_decoded_with_the_console_code_page(self):
        raw = "ОШИБКА: нет docker".encode("cp866")

        outcome, _ = self.run_fake(raw, encoding="cp866")

        self.assertEqual(
            "ОШИБКА: нет docker",
            outcome.output,
        )

    def test_bytes_that_do_not_decode_are_replaced_not_raised(self):
        outcome, _ = self.run_fake(b"ok \xff\xfe", encoding="utf-8")

        self.assertTrue(outcome.output.startswith("ok "))

    def test_the_console_code_page_is_a_known_python_codec(self):
        import codecs

        self.assertIsNotNone(codecs.lookup(process.console_encoding()))


if __name__ == "__main__":
    unittest.main()
