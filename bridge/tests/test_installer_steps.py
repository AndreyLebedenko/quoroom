"""Карточка local-installers-02: шаг, сбой, человек, секрет, отчёт роли."""

import unittest
import urllib.parse
from dataclasses import dataclass

from tests.installer_fakes import FileMarker, InstallerTestCase, Marker, role
from sessionchat.installer.main import DONE, FAILED, HUMAN, main
from sessionchat.installer.ownership import Entry, Ownership, PurgeTarget
from sessionchat.installer.steps import (
    HumanStep,
    NeedsHuman,
    Outcome,
    OwnedStep,
    State,
    execute,
)

RESUME = "Повторите ту же команду: она продолжит с места, где остановилась."


@dataclass
class Waiting:
    name: str
    log: list[str]
    instruction: str

    def check(self, run) -> State:
        self.log.append(f"check:{self.name}")
        return State.TODO

    def apply(self, run) -> None:
        self.log.append(f"apply:{self.name}")
        raise NeedsHuman(self.instruction)


class StepModelTests(InstallerTestCase):
    def test_a_completed_step_is_not_applied(self):
        given = self.boundaries()
        step = Marker("поставить пакет", self.log, done=True)
        outcome = execute((step,), self.run_for(given))
        self.assertEqual(outcome, Outcome.DONE)
        self.assertEqual(self.log, ["check:поставить пакет"])

    def test_a_step_is_applied_and_then_checked_again(self):
        given = self.boundaries()
        step = Marker("поставить пакет", self.log)
        outcome = execute((step,), self.run_for(given))
        self.assertEqual(outcome, Outcome.DONE)
        self.assertEqual(
            self.log,
            ["check:поставить пакет", "apply:поставить пакет", "check:поставить пакет"],
        )

    def test_a_completed_step_is_named_as_a_change_of_this_run(self):
        given = self.boundaries()
        run = self.run_for(given)
        execute((Marker("поставить пакет", self.log),), run)
        self.assertEqual(run.completed, ["поставить пакет"])

    def test_steps_run_in_the_given_order(self):
        given = self.boundaries()
        steps = (
            Marker("первый", self.log, done=True),
            Marker("второй", self.log, done=True),
        )
        execute(steps, self.run_for(given))
        self.assertEqual(self.log, ["check:первый", "check:второй"])

    def test_a_step_that_stays_unfinished_fails_the_run(self):
        given = self.boundaries()
        outcome = execute(
            (Marker("создать комнату", self.log, stays_todo=True),), self.run_for(given)
        )
        self.assertEqual(outcome, Outcome.FAILED)
        self.assertIn("создать комнату", given.stderr.getvalue())

    def test_later_steps_do_not_run_after_a_failure(self):
        given = self.boundaries()
        steps = (
            Marker("сломанный", self.log, stays_todo=True),
            Marker("следующий", self.log),
        )
        execute(steps, self.run_for(given))
        self.assertNotIn("check:следующий", self.log)


class FailureReportTests(InstallerTestCase):
    def failing_run(self, error=None, **values):
        given = self.boundaries(**values)
        run = self.run_for(given)
        run.completed.append("поставить пакет")
        step = Marker("создать комнату", self.log, raises=error, error_on_recheck=True)
        execute((step,), run)
        return given.stderr.getvalue()

    def test_the_report_names_the_failed_step(self):
        self.assertIn("создать комнату", self.failing_run(RuntimeError("нет ответа")))

    def test_the_report_carries_the_error_text(self):
        self.assertIn("нет ответа", self.failing_run(RuntimeError("нет ответа")))

    def test_the_report_lists_what_this_run_changed(self):
        self.assertIn("поставить пакет", self.failing_run(RuntimeError("нет ответа")))

    def test_the_report_says_how_to_resume(self):
        self.assertIn(RESUME, self.failing_run(RuntimeError("нет ответа")))


class HumanStepTests(InstallerTestCase):
    def test_a_pending_human_step_stops_the_run_with_its_instruction(self):
        given = self.boundaries()
        step = HumanStep("hosts", "Допишите строку в файл hosts.", lambda run: False)
        outcome = execute((step,), self.run_for(given))
        self.assertEqual(outcome, Outcome.HUMAN)
        self.assertIn("Допишите строку в файл hosts.", given.stdout.getvalue())

    def test_a_pending_human_step_is_never_applied(self):
        step = HumanStep("hosts", "Допишите строку.", lambda run: False)
        with self.assertRaises(NeedsHuman):
            step.apply(self.run_for(self.boundaries()))

    def test_a_human_step_already_done_is_a_completed_step(self):
        given = self.boundaries()
        step = HumanStep("hosts", "Допишите строку.", lambda run: True)
        outcome = execute((step, Marker("дальше", self.log)), self.run_for(given))
        self.assertEqual(outcome, Outcome.DONE)
        self.assertEqual(self.log, ["check:дальше", "apply:дальше", "check:дальше"])

    def test_the_stop_says_how_to_resume(self):
        given = self.boundaries()
        execute(
            (HumanStep("hosts", "Допишите строку.", lambda run: False),),
            self.run_for(given),
        )
        self.assertIn(RESUME, given.stderr.getvalue())

    def test_an_ordinary_step_can_stop_the_run_for_a_human(self):
        given = self.boundaries()
        outcome = execute(
            (Waiting("ввести комнату", self.log, "Введите id комнаты."),),
            self.run_for(given),
        )
        self.assertEqual(outcome, Outcome.HUMAN)
        self.assertIn("Введите id комнаты.", given.stdout.getvalue())

    def test_a_run_that_needs_a_human_exits_three(self):
        given = self.boundaries()
        waiting = Waiting("ввести комнату", self.log, "Введите id комнаты.")
        code = main(["--role", "server"], given, (role("server", install=(waiting,)),))
        self.assertEqual(code, HUMAN)
        self.assertIn("ввести комнату", given.stderr.getvalue())


class SecretTests(InstallerTestCase):
    PASSWORD = "s3cr3t-пароль"

    def test_registering_gives_the_value_back_not_the_placeholder(self):
        run = self.run_for(self.boundaries())
        self.assertEqual(run.secrets.register(self.PASSWORD), self.PASSWORD)

    def test_a_registered_secret_is_scrubbed(self):
        run = self.run_for(self.boundaries())
        run.secrets.register(self.PASSWORD)
        self.assertNotIn(self.PASSWORD, run.secrets.scrub(f"пароль {self.PASSWORD}"))

    def test_the_escaped_form_of_a_secret_is_scrubbed(self):
        run = self.run_for(self.boundaries())
        run.secrets.register("C:\\state\\token")
        escaped = "C:\\\\state\\\\token"
        self.assertNotIn(escaped, run.secrets.scrub(f"путь {escaped}"))

    def test_the_percent_encoded_form_of_a_secret_is_scrubbed(self):
        run = self.run_for(self.boundaries())
        run.secrets.register("токен")
        quoted = urllib.parse.quote("токен", safe="")
        self.assertNotIn(quoted, run.secrets.scrub(f"путь {quoted}"))

    def both_streams(self, where: str) -> str:
        given = self.boundaries()
        run = self.run_for(given)
        run.secrets.register(self.PASSWORD)
        step = Marker(
            "создать аккаунт",
            self.log,
            raises=RuntimeError(f"не принят пароль {self.PASSWORD}"),
            error_on_recheck=where == "recheck",
        )
        execute((step,), run)
        return given.stdout.getvalue() + given.stderr.getvalue()

    def test_a_secret_in_an_exception_never_reaches_the_output(self):
        for where in ("apply", "recheck"):
            self.assertNotIn(self.PASSWORD, self.both_streams(where))

    def test_the_placeholder_stands_in_for_the_secret(self):
        self.assertIn("<скрыто>", self.both_streams("apply"))

    def test_say_and_warn_scrub_what_they_print(self):
        given = self.boundaries()
        run = self.run_for(given)
        run.secrets.register(self.PASSWORD)
        run.say(f"пароль {self.PASSWORD}")
        run.warn(f"пароль {self.PASSWORD}")
        self.assertNotIn(self.PASSWORD, given.stdout.getvalue())
        self.assertNotIn(self.PASSWORD, given.stderr.getvalue())


class OwnedStepTests(InstallerTestCase):
    def ownership(self) -> Ownership:
        return Ownership(
            self.record("server"),
            [Entry("volume", "continuwuity-data"), Entry("volume", "caddy-data")],
        )

    def owned_step(self) -> OwnedStep:
        return OwnedStep(
            "удалить тома", "server", "volume", lambda run, id: self.log.append(id)
        )

    def test_only_recorded_identifiers_are_deleted(self):
        ownership = self.ownership()
        execute(
            (self.owned_step(),),
            self.run_for(self.boundaries(), {"server": ownership}),
        )
        self.assertEqual(self.log, ["continuwuity-data", "caddy-data"])

    def test_a_deleted_resource_is_forgotten(self):
        ownership = self.ownership()
        execute(
            (self.owned_step(),),
            self.run_for(self.boundaries(), {"server": ownership}),
        )
        self.assertEqual(ownership.of_kind("volume"), [])

    def test_a_step_with_nothing_recorded_is_already_done(self):
        ownership = Ownership(self.record("server"))
        step = self.owned_step()
        run = self.run_for(self.boundaries(), {"server": ownership})
        self.assertIs(step.check(run), State.DONE)

    def test_a_role_without_a_record_never_deletes(self):
        given = self.boundaries()
        run = self.run_for(given, {"server": Ownership(self.record("server"))})
        outcome = execute((self.owned_step(),), run)
        self.assertEqual(outcome, Outcome.DONE)
        self.assertEqual(self.log, [])

    def test_the_default_deleter_removes_the_file(self):
        target = self.home / "config.yaml"
        target.write_text("port: 8770\n", encoding="utf-8")
        ownership = Ownership(self.record("server"), [Entry("file", str(target))])
        step = OwnedStep("убрать конфигурацию", "server", "file")
        execute((step,), self.run_for(self.boundaries(), {"server": ownership}))
        self.assertFalse(target.exists())
        self.assertEqual(ownership.entries, [])

    def test_the_default_deleter_tolerates_a_missing_file(self):
        ownership = Ownership(
            self.record("server"), [Entry("file", str(self.home / "нет"))]
        )
        step = OwnedStep("убрать конфигурацию", "server", "file")
        outcome = execute(
            (step,), self.run_for(self.boundaries(), {"server": ownership})
        )
        self.assertEqual(outcome, Outcome.DONE)


class PurgeStepTests(InstallerTestCase):
    def purge_run(self, confirmed: bool):
        ownership = Ownership(
            self.record("server"), [Entry("volume", "continuwuity-data")]
        )
        run = self.run_for(self.boundaries(), {"server": ownership}, purge=True)
        if confirmed:
            run.confirmed.update([PurgeTarget("server", "volume", "continuwuity-data")])
        return run

    def test_a_confirmed_target_is_deleted(self):
        run = self.purge_run(confirmed=True)
        execute(
            (OwnedStep("удалить тома", "server", "volume", lambda r, i: None),), run
        )
        self.assertEqual(run.ownership_of("server").of_kind("volume"), [])

    def test_an_unconfirmed_target_survives_and_is_reported(self):
        given = self.boundaries()
        ownership = Ownership(
            self.record("server"), [Entry("volume", "continuwuity-data")]
        )
        run = self.run_for(given, {"server": ownership}, purge=True)
        execute(
            (OwnedStep("удалить тома", "server", "volume", lambda r, i: None),), run
        )
        self.assertEqual(
            run.ownership_of("server").of_kind("volume"), ["continuwuity-data"]
        )
        self.assertIn("continuwuity-data", given.stderr.getvalue())

    def test_removal_without_purge_needs_no_confirmation(self):
        ownership = Ownership(
            self.record("server"), [Entry("volume", "continuwuity-data")]
        )
        run = self.run_for(self.boundaries(), {"server": ownership}, remove=True)
        execute(
            (OwnedStep("удалить тома", "server", "volume", lambda r, i: None),), run
        )
        self.assertEqual(run.ownership_of("server").of_kind("volume"), [])


class RoleReportTests(InstallerTestCase):
    def test_the_report_runs_after_every_role_finished(self):
        said: list[str] = []

        def report(run) -> None:
            said.append(run.plan.roles[0])

        given = self.boundaries()
        code = main(
            ["--role", "server"],
            given,
            (role("server", install=(Marker("поставить", self.log),), report=report),),
        )
        self.assertEqual(code, DONE)
        self.assertEqual(said, ["server"])

    def test_the_report_sees_the_changes_of_the_whole_run(self):
        seen: list[list[str]] = []

        given = self.boundaries()
        main(
            ["--role", "server"],
            given,
            (
                role(
                    "server",
                    install=(Marker("поставить", self.log),),
                    report=lambda run: seen.append(list(run.completed)),
                ),
            ),
        )
        self.assertEqual(seen, [["поставить"]])

    def test_a_broken_report_fails_the_run_without_a_traceback(self):
        def report(run) -> None:
            raise RuntimeError("отчёт не напечатан")

        given = self.boundaries()
        code = main(["--role", "server"], given, (role("server", report=report),))
        self.assertEqual(code, FAILED)
        self.assertIn("отчёт после установки", given.stderr.getvalue())
        self.assertNotIn("Traceback", given.stderr.getvalue())

    def test_a_broken_report_keeps_a_secret_out_of_the_output(self):
        def report(run) -> None:
            run.secrets.register("s3cr3t-пароль")
            raise RuntimeError("отчёт не напечатан: s3cr3t-пароль")

        given = self.boundaries()
        code = main(["--role", "server"], given, (role("server", report=report),))
        self.assertEqual(code, FAILED)
        self.assertNotIn("s3cr3t-пароль", given.stderr.getvalue())

    def test_a_broken_report_lists_what_the_run_changed(self):
        def report(run) -> None:
            raise RuntimeError("отчёт не напечатан")

        given = self.boundaries()
        main(
            ["--role", "server"],
            given,
            (
                role(
                    "server",
                    install=(Marker("поставить", self.log),),
                    report=report,
                ),
            ),
        )
        self.assertIn("поставить", given.stderr.getvalue())

    def test_no_report_after_a_failure(self):
        said: list[str] = []
        broken = Marker("сломанный", self.log, stays_todo=True)
        code = main(
            ["--role", "server"],
            self.boundaries(),
            (
                role(
                    "server", install=(broken,), report=lambda run: said.append("отчёт")
                ),
            ),
        )
        self.assertEqual(code, FAILED)
        self.assertEqual(said, [])


class InterruptedRunTests(InstallerTestCase):
    def install_role(self, error=None):
        return role(
            "server",
            install=(
                FileMarker("поставить пакет", self.home / "venv", self.log),
                FileMarker(
                    "создать комнату",
                    self.home / "room.txt",
                    self.log,
                    raises_on_apply=error,
                ),
            ),
        )

    def test_a_step_that_failed_is_the_only_one_the_next_run_applies(self):
        first = self.install_role(RuntimeError("комната занята"))
        self.assertEqual(
            main(["--role", "server"], self.boundaries(), (first,)), FAILED
        )
        self.log.clear()
        second = self.install_role()
        self.assertEqual(main(["--role", "server"], self.boundaries(), (second,)), DONE)
        self.assertEqual(
            self.log,
            [
                "check:поставить пакет",
                "check:создать комнату",
                "apply:создать комнату",
                "check:создать комнату",
            ],
        )

    def test_a_second_run_over_a_finished_installation_applies_nothing(self):
        self.assertEqual(
            main(["--role", "server"], self.boundaries(), (self.install_role(),)), DONE
        )
        self.log.clear()
        main(["--role", "server"], self.boundaries(), (self.install_role(),))
        self.assertEqual(self.log, ["check:поставить пакет", "check:создать комнату"])


if __name__ == "__main__":
    unittest.main()
