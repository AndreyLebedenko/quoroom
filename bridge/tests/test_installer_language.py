"""Карточка installer-bilingual: язык установщика задаёт флаг --lang и Boundaries.lang."""

import os
import re
import ssl
import subprocess
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from tests.installer_fakes import (
    FileMarker,
    InstallerTestCase,
    Marker,
    State,
    boundaries,
    make_run,
    recorded,
    role,
)
from sessionchat.installer.boundaries import Boundaries, ask_secret, describe
from sessionchat.installer.catalogue import DEFAULT_LANGUAGE, LANGUAGES
from sessionchat.installer.confirmation import WORD
from sessionchat.installer.main import (
    CANCELLED,
    DONE,
    FAILED,
    HUMAN,
    USAGE,
    main,
)
from sessionchat.installer.options import language_of
from sessionchat.installer.ownership import Entry, Ownership, PurgeTarget
from sessionchat.installer.steps import (
    Failure,
    FoundStep,
    OwnedStep,
    execute,
    report_kept,
)

BRIDGE = Path(__file__).resolve().parent.parent
CYRILLIC = re.compile("[Ѐ-ӿ]")
SECRET = "s3cr3t-value"


def words(given: Boundaries) -> str:
    return given.stdout.getvalue() + given.stderr.getvalue()


class RememberStep:
    name = "remember data"

    def __init__(self, target: Path) -> None:
        self.target = target

    def check(self, run) -> State:
        return State.DONE if self.target.exists() else State.TODO

    def apply(self, run) -> None:
        run.record("server", "file", str(self.target))
        self.target.write_text("data", encoding="utf-8")


class LanguageOfArgumentsTests(unittest.TestCase):
    def test_without_the_flag_the_default_stays(self):
        self.assertEqual(language_of(["--role", "server"], "en"), "en")

    def test_the_flag_with_a_separate_value_is_read(self):
        self.assertEqual(language_of(["--lang", "ru", "--role", "x"], "en"), "ru")

    def test_the_flag_with_an_equals_sign_is_read(self):
        self.assertEqual(language_of(["--lang=ru"], "en"), "ru")

    def test_the_last_flag_wins(self):
        self.assertEqual(language_of(["--lang", "ru", "--lang", "en"], "ru"), "en")

    def test_a_flag_without_a_value_leaves_the_default(self):
        self.assertEqual(language_of(["--role", "x", "--lang"], "en"), "en")

    def test_a_value_is_not_checked_here(self):
        self.assertEqual(language_of(["--lang", "xx"], "en"), "xx")


class UnknownLanguageTests(InstallerTestCase):
    def refused(self, argv, lang="ru"):
        given = self.boundaries(lang=lang)
        code = main(argv, given, (role("server"),))
        return code, given

    def test_an_unknown_language_is_a_usage_error(self):
        code, _ = self.refused(["--role", "server", "--lang", "xx"])
        self.assertEqual(code, USAGE)

    def test_the_equals_form_of_an_unknown_language_is_a_usage_error(self):
        code, _ = self.refused(["--role", "server", "--lang=xx"])
        self.assertEqual(code, USAGE)

    def test_the_refusal_is_english_even_when_the_run_was_russian(self):
        _, given = self.refused(["--role", "server", "--lang", "xx"], lang="ru")
        self.assertIsNone(CYRILLIC.search(words(given)))

    def test_the_refusal_names_the_value_and_the_choices(self):
        _, given = self.refused(["--role", "server", "--lang", "xx"])
        self.assertIn("'xx'", given.stderr.getvalue())
        self.assertIn("en, ru", given.stderr.getvalue())

    def test_the_refusal_goes_to_stderr_with_the_prefix(self):
        _, given = self.refused(["--role", "server", "--lang", "xx"])
        self.assertTrue(given.stderr.getvalue().startswith("AGENTSCHAT: "))
        self.assertEqual(given.stdout.getvalue(), "")

    def test_a_flag_without_a_value_is_a_usage_error(self):
        code, _ = self.refused(["--role", "server", "--lang"])
        self.assertEqual(code, USAGE)

    def test_nothing_runs_after_an_unknown_language(self):
        marker = Marker("install package", self.log)
        main(
            ["--role", "server", "--lang", "xx"],
            self.boundaries(),
            (role("server", install=(marker,)),),
        )
        self.assertEqual(self.log, [])


class ChosenLanguageTests(InstallerTestCase):
    def purge_alone(self, argv, lang):
        given = self.boundaries(lang=lang)
        code = main(argv, given, (role("server"),))
        return code, given

    def test_the_language_of_the_boundaries_is_the_default(self):
        _, russian = self.purge_alone(["--purge"], "ru")
        _, english = self.purge_alone(["--purge"], "en")
        self.assertIn("имеет смысл только вместе", russian.stderr.getvalue())
        self.assertIn("only makes sense together", english.stderr.getvalue())

    def test_the_flag_overrides_the_language_of_the_boundaries(self):
        _, given = self.purge_alone(["--purge", "--lang", "ru"], "en")
        self.assertIn("имеет смысл только вместе", given.stderr.getvalue())

    def test_the_flag_overrides_in_the_other_direction_too(self):
        _, given = self.purge_alone(["--purge", "--lang=en"], "ru")
        self.assertIn("only makes sense together", given.stderr.getvalue())

    def test_the_flag_is_accepted_after_the_role(self):
        given = self.boundaries(lang="en")
        code = main(["--role", "server", "--lang", "ru"], given, (role("server"),))
        self.assertEqual(code, DONE)

    def test_the_usage_line_mentions_the_flag(self):
        _, given = self.purge_alone(["--no-such-flag"], "en")
        self.assertIn("--lang {en,ru}", given.stderr.getvalue())

    def test_help_mentions_the_flag(self):
        given = self.boundaries(lang="en")
        main(["--help"], given, (role("server"),))
        self.assertIn("--lang", given.stdout.getvalue())

    def test_help_is_in_english_by_default(self):
        given = self.boundaries(lang="en")
        main(["--help"], given, (role("server"),))
        self.assertIn("Install and remove Quoroom", given.stdout.getvalue())
        self.assertIsNone(CYRILLIC.search(given.stdout.getvalue()))

    def test_help_follows_the_flag_in_description_and_every_help_text(self):
        given = self.boundaries(lang="en")
        main(["--help", "--lang", "ru"], given, (role("server"),))
        shown = given.stdout.getvalue()
        for phrase in (
            "Установка и удаление Quoroom на одной машине",
            "роль установки",
            "удалить вместо установки",
            "удалить и данные роли",
            "язык сообщений установщика",
        ):
            self.assertIn(phrase, shown)

    def test_help_exits_zero_in_both_languages(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                given = self.boundaries()
                self.assertEqual(
                    main(["--help", "--lang", lang], given, (role("server"),)), DONE
                )

    def test_the_interactive_question_follows_the_language(self):
        english = self.boundaries(stdin="1\n", interactive=True, lang="en")
        main([], english, (role("server"),))
        russian = self.boundaries(stdin="1\n", interactive=True, lang="en")
        main(["--lang", "ru"], russian, (role("server"),))
        self.assertIn("What do we install or remove?", english.stdout.getvalue())
        self.assertIn("Что ставим или удаляем?", russian.stdout.getvalue())


class SameScenarioTests(InstallerTestCase):
    def home_for(self, lang):
        home = self.home / lang
        home.mkdir()
        return home

    def install(self, log, completed):
        return role(
            "server",
            install=(
                Marker("install package", log),
                Marker("create room", log),
            ),
            report=lambda run: completed.append(list(run.completed)),
        )

    def failing(self, log, completed):
        return role(
            "server",
            install=(
                Marker("install package", log),
                Marker("create room", log, stays_todo=True),
            ),
            report=lambda run: completed.append(list(run.completed)),
        )

    def waiting(self, log, completed):
        return role(
            "server",
            install=(
                Marker("install package", log),
                FileMarker(
                    "enter room", self.home / "room.txt", log, needs_human="Enter it."
                ),
            ),
            report=lambda run: completed.append(list(run.completed)),
        )

    def purging(self, log, completed):
        return role(
            "server",
            purge=(
                OwnedStep(
                    "remove files",
                    "server",
                    "file",
                    lambda run, id: log.append(f"delete:{Path(id).name}"),
                ),
            ),
            report=lambda run: completed.append(list(run.completed)),
        )

    def outcome(self, scenario, argv, stdin, lang):
        log, completed = [], []
        home = self.home_for(lang)
        recorded(home, "records/server.json", [("file", str(home / "data.txt"))])
        given = boundaries(home, stdin=stdin, lang="ru")
        code = main([*argv, "--lang", lang], given, (scenario(log, completed),))
        return code, log, completed, given

    def assert_same_in_both_languages(self, scenario, argv, expected, stdin=""):
        seen = {lang: self.outcome(scenario, argv, stdin, lang) for lang in LANGUAGES}
        english, russian = seen["en"], seen["ru"]
        self.assertEqual(english[0], expected, words(english[3]))
        self.assertEqual(russian[0], expected, words(russian[3]))
        self.assertEqual(english[1], russian[1])
        self.assertEqual(english[2], russian[2])

    def test_an_install_ends_the_same_way_and_completes_the_same_steps(self):
        self.assert_same_in_both_languages(self.install, ["--role", "server"], DONE)

    def test_the_completed_step_keys_are_the_names_in_both_languages(self):
        _, _, completed, _ = self.outcome(self.install, ["--role", "server"], "", "ru")
        self.assertEqual(completed, [["install package", "create room"]])

    def test_a_failure_ends_the_same_way(self):
        self.assert_same_in_both_languages(self.failing, ["--role", "server"], FAILED)

    def test_a_stop_for_a_human_ends_the_same_way(self):
        self.assert_same_in_both_languages(self.waiting, ["--role", "server"], HUMAN)

    def test_a_refused_purge_ends_the_same_way(self):
        self.assert_same_in_both_languages(
            self.purging,
            ["--role", "server", "--remove", "--purge"],
            CANCELLED,
            stdin="no\n",
        )

    def test_a_confirmed_purge_ends_the_same_way(self):
        self.assert_same_in_both_languages(
            self.purging,
            ["--role", "server", "--remove", "--purge"],
            DONE,
            stdin=f"{WORD}\n",
        )

    def test_a_usage_error_ends_the_same_way(self):
        self.assert_same_in_both_languages(self.install, ["--purge"], USAGE)


class EnglishByDefaultTests(InstallerTestCase):
    def english(self, **values):
        return self.boundaries(lang="en", **values)

    def assert_english(self, given):
        shown = words(given)
        self.assertTrue(shown)
        self.assertIsNone(CYRILLIC.search(shown), shown)

    def test_the_real_boundaries_speak_english_unless_told_otherwise(self):
        self.assertEqual(DEFAULT_LANGUAGE, "en")
        self.assertEqual(Boundaries.real().lang, "en")

    def test_a_usage_error_is_english(self):
        given = self.english()
        main(["--purge"], given, (role("server"),))
        self.assert_english(given)

    def test_an_unknown_role_is_english(self):
        given = self.english()
        main(["--role", "nobody"], given, (role("server"),))
        self.assert_english(given)

    def test_a_missing_role_without_a_terminal_is_english(self):
        given = self.english()
        main([], given, (role("server"),))
        self.assert_english(given)

    def test_a_build_without_roles_is_english(self):
        given = self.english()
        main([], given, ())
        self.assert_english(given)

    def test_a_misunderstood_answer_is_english(self):
        given = self.english(stdin="what?\n", interactive=True)
        main([], given, (role("server"),))
        self.assert_english(given)

    def test_a_successful_install_is_english(self):
        given = self.english()
        main(
            ["--role", "server"],
            given,
            (role("server", install=(Marker("install package", self.log),)),),
        )
        self.assert_english(given)

    def test_a_step_that_was_already_done_is_english(self):
        given = self.english()
        main(
            ["--role", "server"],
            given,
            (
                role(
                    "server", install=(Marker("install package", self.log, done=True),)
                ),
            ),
        )
        self.assert_english(given)

    def test_a_failure_report_is_english(self):
        given = self.english()
        main(
            ["--role", "server"],
            given,
            (
                role(
                    "server",
                    install=(
                        Marker("install package", self.log),
                        Marker(
                            "create room",
                            self.log,
                            raises=RuntimeError("no answer"),
                            error_on_recheck=True,
                        ),
                    ),
                ),
            ),
        )
        self.assert_english(given)
        self.assertIn("Failed at step", given.stderr.getvalue())

    def test_a_step_that_stays_unfinished_is_english(self):
        given = self.english()
        main(
            ["--role", "server"],
            given,
            (
                role(
                    "server",
                    install=(Marker("create room", self.log, stays_todo=True),),
                ),
            ),
        )
        self.assert_english(given)

    def test_a_stop_for_a_human_is_english(self):
        given = self.english()
        waiting = FileMarker(
            "enter room", self.home / "room.txt", self.log, needs_human="Enter the id."
        )
        main(["--role", "server"], given, (role("server", install=(waiting,)),))
        self.assert_english(given)

    def test_a_broken_report_names_the_report_step_in_english(self):
        def report(run):
            raise RuntimeError("report failed")

        given = self.english()
        main(["--role", "server"], given, (role("server", report=report),))
        self.assert_english(given)
        self.assertIn("post-install report", given.stderr.getvalue())

    def test_a_failed_preparation_names_the_preparation_step_in_english(self):
        path = self.record("server")
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        given = self.english()
        code = main(["--role", "server"], given, (role("server"),))
        self.assertEqual(code, FAILED)
        self.assert_english(given)
        self.assertIn("run preparation", given.stderr.getvalue())

    def purge(self, stdin):
        target = self.home / "data.txt"
        target.write_text("data", encoding="utf-8")
        recorded(self.home, "records/server.json", [("file", str(target))])
        given = self.english(stdin=stdin)
        step = OwnedStep("remove files", "server", "file")
        code = main(
            ["--role", "server", "--remove", "--purge"],
            given,
            (role("server", purge=(step,)),),
        )
        return code, given

    def test_the_purge_confirmation_is_english(self):
        code, given = self.purge(f"{WORD}\n")
        self.assertEqual(code, DONE)
        self.assert_english(given)
        self.assertIn(f"type {WORD} and press Enter", given.stdout.getvalue())

    def test_a_refused_purge_is_english(self):
        code, given = self.purge("no\n")
        self.assertEqual(code, CANCELLED)
        self.assert_english(given)

    def test_the_default_consequence_is_english(self):
        _, given = self.purge(f"{WORD}\n")
        self.assertIn("Consequence: there will be no way", given.stdout.getvalue())

    def test_unconfirmed_targets_are_reported_in_english(self):
        given = self.english()
        ownership = Ownership(self.record("server"), [Entry("volume", "data-volume")])
        run = self.run_for(given, {"server": ownership}, purge=True)
        execute(
            (OwnedStep("remove volumes", "server", "volume", lambda r, i: None),), run
        )
        self.assert_english(given)
        self.assertIn("not confirmed, left in place: data-volume", words(given))

    def test_a_found_record_is_reported_in_english(self):
        given = self.english()
        record = self.record("server")
        run = self.run_for(given, {"server": Ownership(record)}, remove=True)
        run.records = frozenset({record.resolve()})
        found = FoundStep("sweep", "server", "file", lambda r: [str(record)])
        execute((found,), run)
        self.assert_english(given)
        self.assertIn("left in place as an installer record", words(given))


class RecordsAcrossLanguagesTests(InstallerTestCase):
    def installing(self, target):
        return role("server", install=(RememberStep(target),))

    def purging(self):
        return role("server", purge=(OwnedStep("remove data", "server", "file"),))

    def written_then_purged(self, written, purged):
        target = self.home / "data.txt"
        install = main(
            ["--role", "server", "--lang", written],
            self.boundaries(),
            (self.installing(target),),
        )
        self.assertEqual(install, DONE)
        given = self.boundaries(stdin=f"{WORD}\n")
        code = main(
            ["--role", "server", "--remove", "--purge", "--lang", purged],
            given,
            (self.purging(),),
        )
        return code, given, target

    def test_a_record_written_in_russian_is_purged_in_english(self):
        code, given, target = self.written_then_purged("ru", "en")
        self.assertEqual(code, DONE, words(given))
        self.assertIn(f"    server: file {target}", given.stdout.getvalue())
        self.assertFalse(target.exists())

    def test_a_record_written_in_english_is_purged_in_russian(self):
        code, given, target = self.written_then_purged("en", "ru")
        self.assertEqual(code, DONE, words(given))
        self.assertIn(f"    server: file {target}", given.stdout.getvalue())
        self.assertFalse(target.exists())

    def test_the_record_file_is_the_same_whatever_the_language(self):
        records = []
        for lang in LANGUAGES:
            home = self.home / lang
            home.mkdir()
            target = home / "data.txt"
            main(
                ["--role", "server", "--lang", lang],
                boundaries(home),
                (self.installing(target),),
            )
            text = (home / "records" / "server.json").read_text(encoding="utf-8")
            slashed = text.replace("\\\\", "/")
            records.append(slashed.replace(str(home).replace("\\", "/"), "HOME"))
        self.assertEqual(records[0], records[1])

    def test_the_confirmation_word_is_the_same_in_both_languages(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                target = self.home / f"{lang}.txt"
                recorded(self.home, "records/server.json", [("file", str(target))])
                target.write_text("data", encoding="utf-8")
                given = self.boundaries(stdin=f"{WORD}\n")
                code = main(
                    ["--role", "server", "--remove", "--purge", "--lang", lang],
                    given,
                    (self.purging(),),
                )
                self.assertEqual(code, DONE)
                self.assertIn(WORD, given.stdout.getvalue())


class ScrubbedPlaceholderTests(InstallerTestCase):
    def prepared(self, lang):
        given = self.boundaries(lang=lang)
        run = self.run_for(given)
        run.secrets.register(SECRET)
        return given, run

    def test_a_secret_passed_as_a_placeholder_never_reaches_stdout(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                given, run = self.prepared(lang)
                run.say(run.t("steps.done", step=SECRET))
                self.assertNotIn(SECRET, given.stdout.getvalue())
                self.assertIn(run.t("secrets.hidden"), given.stdout.getvalue())

    def test_a_secret_passed_as_a_placeholder_never_reaches_stderr(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                given, run = self.prepared(lang)
                run.warn(run.t("steps.kept_unconfirmed", step="x", ids=SECRET))
                run.warn_once("k", run.t("steps.kept_as_record", step="x", ids=SECRET))
                self.assertNotIn(SECRET, given.stderr.getvalue())
                self.assertIn(run.t("secrets.hidden"), given.stderr.getvalue())

    def test_the_placeholder_follows_the_language(self):
        english, run_en = self.prepared("en")
        run_en.say(SECRET)
        russian, run_ru = self.prepared("ru")
        run_ru.say(SECRET)
        self.assertEqual(english.stdout.getvalue(), "<hidden>\n")
        self.assertEqual(russian.stdout.getvalue(), "<скрыто>\n")

    def test_a_failure_report_scrubs_the_step_names_and_the_reason(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                _, run = self.prepared(lang)
                report = Failure(SECRET, (SECRET,), f"bad {SECRET}").render(
                    run.secrets, lang
                )
                self.assertNotIn(SECRET, report)

    def test_a_secret_in_the_consequence_is_scrubbed_in_the_confirmation(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                given, run = self.prepared(lang)
                run.confirm.ask(f"lost {SECRET}", [])
                self.assertNotIn(SECRET, given.stdout.getvalue())

    def test_the_registered_secret_is_scrubbed_from_a_full_failed_run(self):
        step = Marker(
            "create account",
            self.log,
            raises=RuntimeError(f"rejected {SECRET}"),
        )
        given = self.boundaries(lang="en")
        run = self.run_for(given)
        run.secrets.register(SECRET)
        execute((step,), run)
        self.assertNotIn(SECRET, words(given))


class StepIdentityTests(InstallerTestCase):
    def test_the_completed_list_keeps_the_key_while_the_text_is_rendered(self):
        for lang, shown in (("ru", "подготовка запуска"), ("en", "run preparation")):
            with self.subTest(lang=lang):
                given = self.boundaries(lang=lang)
                run = self.run_for(given)
                execute((Marker("prepare", self.log),), run)
                self.assertEqual(run.completed, ["prepare"])
                self.assertIn(f"{shown}: ", given.stdout.getvalue())

    def test_a_name_without_an_entry_is_shown_unchanged(self):
        given = self.boundaries(lang="en")
        run = self.run_for(given)
        execute((Marker("поставить пакет", self.log),), run)
        self.assertEqual(run.completed, ["поставить пакет"])
        self.assertIn("поставить пакет: done.", given.stdout.getvalue())

    def test_the_warn_once_key_is_the_name_not_the_rendered_text(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                given = self.boundaries(lang=lang)
                run = self.run_for(given, purge=True)
                target = PurgeTarget("server", "volume", "data-volume")
                report_kept(run, "prepare", [target])
                report_kept(run, "prepare", [target])
                self.assertEqual(run.warned, {"kept:prepare"})
                self.assertEqual(given.stderr.getvalue().count("\n"), 1)

    def test_a_failure_keeps_the_key_of_the_failed_step(self):
        failure = Failure("prepare", ("report",), "")
        self.assertEqual(failure.step, "prepare")
        self.assertEqual(failure.completed, ("report",))

    def test_a_failure_renders_the_catalogued_names_in_the_language(self):
        run = make_run(self.boundaries())
        failure = Failure("prepare", ("report",), "")
        english = failure.render(run.secrets, "en")
        russian = failure.render(run.secrets, "ru")
        self.assertIn('Failed at step "run preparation".', english)
        self.assertIn("    post-install report", english)
        self.assertIn("Сбой на шаге «подготовка запуска».", russian)
        self.assertIn("    отчёт после установки", russian)


class RealBoundariesTests(unittest.TestCase):
    def mismatched(self, real):
        answers = iter(["first", "second"])
        with patch("getpass.getpass", lambda prompt: next(answers)):
            with self.assertRaises(ValueError) as caught:
                real.secret("Password: ")
        return str(caught.exception)

    def test_the_real_secret_reader_refuses_in_the_chosen_language(self):
        self.assertEqual(self.mismatched(Boundaries.real("ru")), "пароли не совпали")
        self.assertEqual(
            self.mismatched(Boundaries.real("en")), "passwords did not match"
        )

    def test_the_real_boundaries_are_english_without_a_choice(self):
        self.assertEqual(self.mismatched(Boundaries.real()), "passwords did not match")

    def test_the_second_prompt_is_in_the_chosen_language(self):
        for lang, expected in (
            ("en", "Repeat the password: "),
            ("ru", "Повторите пароль: "),
        ):
            asked = []

            def fake(prompt):
                asked.append(prompt)
                return "same"

            with patch("getpass.getpass", fake):
                ask_secret("Password: ", lang)
            self.assertEqual(asked, ["Password: ", expected])

    def test_a_refused_certificate_is_described_in_the_chosen_language(self):
        failure = ssl.SSLCertVerificationError("certificate verify failed", 18)
        error = urllib.error.URLError(failure)
        self.assertIn("certificate not verified", describe(error, "en"))
        self.assertIn("сертификат не подтверждён", describe(error, "ru"))


class InstallerModuleTests(unittest.TestCase):
    def installer(self, *argv):
        env = dict(os.environ, PYTHONPATH=str(BRIDGE))
        return subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "sessionchat.installer", *argv],
            cwd=BRIDGE,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            stdin=subprocess.DEVNULL,
            check=False,
        )

    def test_an_unknown_language_exits_two_with_an_english_message(self):
        done = self.installer("--lang", "xx")
        self.assertEqual(done.returncode, USAGE)
        self.assertTrue(done.stderr.startswith("AGENTSCHAT: "))
        self.assertIsNone(CYRILLIC.search(done.stdout + done.stderr))

    def test_help_is_english_without_the_flag(self):
        done = self.installer("--help")
        self.assertEqual(done.returncode, DONE)
        self.assertIn("Install and remove Quoroom", done.stdout)
        self.assertIn("--lang {en,ru}", done.stdout)

    def test_help_is_russian_with_the_flag(self):
        done = self.installer("--lang", "ru", "--help")
        self.assertEqual(done.returncode, DONE)
        self.assertIn("Установка и удаление Quoroom на одной машине", done.stdout)

    def test_a_usage_error_follows_the_flag(self):
        done = self.installer("--lang", "ru", "--purge")
        self.assertEqual(done.returncode, USAGE)
        self.assertIn("имеет смысл только вместе", done.stderr)


if __name__ == "__main__":
    unittest.main()
