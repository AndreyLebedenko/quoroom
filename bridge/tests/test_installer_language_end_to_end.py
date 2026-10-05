"""Task installer-bilingual, slice 3, part B: the whole installer, server and participant, end to end in both languages."""

import re
import unittest
from pathlib import Path

import tests.test_installer_language as language_tests
from tests.test_installer_participant_languages import (
    RecordingMachine,
    RunSpy,
    watched,
)
from tests.test_installer_server import ADMIN, ROOM, Machine
from tests.test_installer_server_languages import ServerLanguageCase
from sessionchat.installer import participant, server
from sessionchat.installer.catalogue import LANGUAGES
from sessionchat.installer.confirmation import WORD
from sessionchat.installer.main import (
    CANCELLED,
    DONE,
    FAILED,
    USAGE,
    main,
)
from sessionchat.installer.participant import participant_role
from sessionchat.installer.server import server_role

CYRILLIC = re.compile("[Ѐ-ӿ]")
PARTICIPANT_TOOLS = ("pipx", "uv", "agentschat")
TARGET_LINE = re.compile(r"^ {4}(server|participant): ", re.M)
RUSSIAN_HELP = {
    "server": (
        "локальный аккаунт человека в Element",
        "идентификатор комнаты, например !AbCdEf:agentschat.local",
    ),
    "participant": (
        "адрес брокера (по умолчанию",
        "набор только для Claude Code",
        "набор только для OpenCode",
    ),
}
ENGLISH_HELP = {
    "server": (
        "the human's local account in Element",
        "room identifier, for example !AbCdEf:agentschat.local",
    ),
    "participant": (
        "broker address (default",
        "kit for Claude Code only",
        "kit for OpenCode only",
    ),
}


class SharedMachine(Machine):
    def __init__(self, home: Path, repo: Path, participant_machine) -> None:
        super().__init__(home, repo)
        self.participant_machine = participant_machine

    def __call__(self, argv, stdin=None, output=None):
        if Path(str(argv[0])).name.startswith(PARTICIPANT_TOOLS):
            return self.participant_machine(argv)
        return super().__call__(argv, stdin, output)


class BothRolesCase(ServerLanguageCase):
    def setUp(self):
        super().setUp()
        self.participant_machine = RecordingMachine(self.home)
        self.machine = SharedMachine(self.home, self.repo, self.participant_machine)
        self.env["PATH"] = str(self.home / "pipx" / "bin")

    def roles(self):
        self.spy = RunSpy()
        return (
            watched(server_role(sleep=self.slept.append), self.spy),
            watched(participant_role(version=(3, 12)), self.spy),
        )

    def both(self, *flags, **values):
        return self.command("both", *flags, **values)

    def command(self, role, *flags, **values):
        given = self.given(**values)
        code = main(["--role", role, *flags], given, self.roles())
        self.last_given = given
        return code, given

    def install_everything(self, role="both", **values):
        return self.command(role, "--admin-user", ADMIN, "--room-id", ROOM, **values)

    def installed_both(self, lang):
        code, given = self.install_everything(lang=lang)
        self.assertEqual(code, DONE, given.stderr.getvalue())
        self.participant_machine.token("claude-code")
        return given

    def own_words(self, given) -> str:
        shown = given.stdout.getvalue() + given.stderr.getvalue()
        return "\n".join(
            line
            for line in shown.splitlines()
            if line not in self.participant_machine.spoken
        )

    def confirmed_targets(self, given) -> list[str]:
        shown = self.masked(given.stdout.getvalue())
        return [line for line in shown.splitlines() if TARGET_LINE.match(line)]


class ServerWithoutTheFlagTests(ServerLanguageCase):
    def assert_no_russian(self, given):
        shown = self.stdout(given) + self.stderr(given)
        self.assertTrue(shown)
        self.assertIsNone(CYRILLIC.search(shown), shown)

    def test_a_full_server_install_prints_no_russian(self):
        code, given = self.everything(lang="en")
        self.assertEqual(code, DONE, self.stderr(given))
        self.assert_no_russian(given)

    def test_a_server_removal_prints_no_russian(self):
        self.installed_in("en")
        code, given = self.remove(lang="en")
        self.assertEqual(code, DONE, self.stderr(given))
        self.assert_no_russian(given)

    def test_a_server_purge_with_the_typed_word_prints_no_russian(self):
        self.installed_in("en")
        code, given = self.purge(lang="en")
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(f"To continue, type {WORD} and press Enter.", self.stdout(given))
        self.assert_no_russian(given)

    def test_a_server_purge_that_is_refused_prints_no_russian(self):
        self.installed_in("en")
        code, given = self.remove("--purge", stdin="no\n", lang="en")
        self.assertEqual(code, CANCELLED)
        self.assert_no_russian(given)

    def test_a_usage_error_of_the_server_role_prints_no_russian(self):
        code, given = self.install("--purge", lang="en")
        self.assertEqual(code, USAGE)
        self.assertTrue(self.stderr(given).startswith("AGENTSCHAT: "))
        self.assert_no_russian(given)

    def test_a_failure_report_of_the_server_role_prints_no_russian(self):
        self.machine.fail_pip = True
        code, given = self.everything(lang="en")
        self.assertEqual(code, FAILED)
        self.assertIn('Failed at step "Create bridge/.venv".', self.stderr(given))
        self.assert_no_russian(given)


class BothRolesWithoutTheFlagTests(BothRolesCase):
    def assert_no_russian(self, given):
        shown = self.own_words(given)
        self.assertTrue(shown)
        self.assertIsNone(CYRILLIC.search(shown), shown)

    def test_a_full_install_of_both_roles_prints_no_russian(self):
        code, given = self.install_everything(lang="en")
        self.assertEqual(code, DONE, given.stderr.getvalue())
        self.assert_no_russian(given)

    def test_a_removal_of_both_roles_prints_no_russian(self):
        self.installed_both("en")
        code, given = self.both("--remove", lang="en")
        self.assertEqual(code, DONE, given.stderr.getvalue())
        self.assert_no_russian(given)

    def test_a_purge_of_both_roles_with_the_typed_word_prints_no_russian(self):
        self.installed_both("en")
        code, given = self.both("--remove", "--purge", stdin=f"{WORD}\n", lang="en")
        self.assertEqual(code, DONE, given.stderr.getvalue())
        self.assert_no_russian(given)


class SameScenarioInBothLanguagesTests(BothRolesCase):
    def completed_in(self, scenario):
        seen = {}
        for lang in LANGUAGES:
            self.setUp()
            code, _ = scenario(lang)
            seen[lang] = (code, self.spy.completed_steps)
        return seen

    def assert_same_ending(self, scenario, expected):
        seen = self.completed_in(scenario)
        self.assertEqual(seen["en"][0], expected)
        self.assertEqual(seen["en"], seen["ru"])
        return seen["en"][1]

    def test_a_full_server_install_ends_the_same_way(self):
        steps = self.assert_same_ending(
            lambda lang: self.install_everything("server", lang=lang), DONE
        )
        self.assertIn("create_bot_accounts", steps)

    def test_a_full_participant_install_ends_the_same_way(self):
        def scenario(lang):
            self.machine.broker_up = True
            return self.install_everything("participant", lang=lang)

        steps = self.assert_same_ending(scenario, DONE)
        self.assertIn(participant.PackageStep().name, steps)

    def test_an_install_of_both_roles_ends_the_same_way(self):
        steps = self.assert_same_ending(
            lambda lang: self.install_everything(lang=lang), DONE
        )
        self.assertIn(server.StartStep().name, steps)
        self.assertIn(participant.PackageStep().name, steps)

    def test_a_removal_of_both_roles_ends_the_same_way(self):
        def scenario(lang):
            self.installed_both(lang)
            return self.both("--remove", lang=lang)

        self.assert_same_ending(scenario, DONE)

    def test_a_purge_of_both_roles_ends_the_same_way(self):
        def scenario(lang):
            self.installed_both(lang)
            return self.both("--remove", "--purge", stdin=f"{WORD}\n", lang=lang)

        steps = self.assert_same_ending(scenario, DONE)
        self.assertIn("remove_stand_volumes", steps)

    def test_a_refused_purge_of_both_roles_ends_the_same_way(self):
        def scenario(lang):
            self.installed_both(lang)
            return self.both("--remove", "--purge", stdin="no\n", lang=lang)

        self.assert_same_ending(scenario, CANCELLED)

    def test_a_usage_error_ends_the_same_way(self):
        self.assert_same_ending(lambda lang: self.both("--purge", lang=lang), USAGE)

    def test_a_failure_ends_the_same_way(self):
        def scenario(lang):
            self.machine.fail_pip = True
            return self.install_everything(lang=lang)

        self.assert_same_ending(scenario, FAILED)


class RecordsAcrossLanguagesTests(BothRolesCase):
    def purged_after(self, written, purged):
        self.setUp()
        self.installed_both(written)
        code, given = self.both("--remove", "--purge", stdin=f"{WORD}\n", lang=purged)
        self.assertEqual(code, DONE, given.stderr.getvalue())
        return self.confirmed_targets(given)

    def test_the_purge_lists_the_same_targets_whichever_language_wrote_the_records(
        self,
    ):
        listed = {
            (written, purged): self.purged_after(written, purged)
            for written in LANGUAGES
            for purged in LANGUAGES
        }
        self.assertEqual(len({tuple(lines) for lines in listed.values()}), 1)

    def test_the_listed_targets_name_both_roles(self):
        lines = self.purged_after("ru", "en")
        roles = {TARGET_LINE.match(line).group(1) for line in lines}
        self.assertEqual(roles, {"server", "participant"})

    def test_a_server_record_written_in_one_language_is_purged_in_the_other(self):
        for written, purged in (("en", "ru"), ("ru", "en")):
            with self.subTest(written=written, purged=purged):
                self.setUp()
                code, _ = self.install_everything("server", lang=written)
                self.assertEqual(code, DONE)
                code, given = self.command(
                    "server", "--remove", "--purge", stdin=f"{WORD}\n", lang=purged
                )
                self.assertEqual(code, DONE, given.stderr.getvalue())
                self.assertFalse(self.record_file().exists())
                self.assertFalse(self.toml().exists())

    def test_a_participant_record_written_in_one_language_is_purged_in_the_other(
        self,
    ):
        for written, purged in (("en", "ru"), ("ru", "en")):
            with self.subTest(written=written, purged=purged):
                self.setUp()
                self.machine.broker_up = True
                code, _ = self.install_everything("participant", lang=written)
                self.assertEqual(code, DONE)
                self.participant_machine.token("claude-code")
                code, given = self.command(
                    "participant",
                    "--remove",
                    "--purge",
                    stdin=f"{WORD}\n",
                    lang=purged,
                )
                self.assertEqual(code, DONE, given.stderr.getvalue())
                self.assertFalse(participant.record_path(given).exists())
                self.assertFalse(
                    (self.home / participant.STORE / "claude-code.json").exists()
                )


class HelpOfTheRealInstallerTests(unittest.TestCase):
    def helped(self, *argv):
        done = language_tests.InstallerModuleTests.installer(None, *argv, "--help")
        self.assertEqual(done.returncode, DONE, done.stderr)
        return " ".join(done.stdout.split())

    def test_the_help_has_no_russian_anywhere_with_the_english_flag(self):
        shown = self.helped("--lang", "en")
        self.assertIsNone(CYRILLIC.search(shown), shown)

    def test_the_help_has_no_russian_anywhere_without_the_flag(self):
        shown = self.helped()
        self.assertIsNone(CYRILLIC.search(shown), shown)

    def test_the_help_describes_every_role_option_in_english(self):
        shown = self.helped("--lang", "en")
        for role, phrases in ENGLISH_HELP.items():
            for phrase in phrases:
                with self.subTest(role=role, phrase=phrase):
                    self.assertIn(phrase, shown)

    def test_the_help_describes_every_role_option_in_russian_with_the_flag(self):
        shown = self.helped("--lang", "ru")
        for role, phrases in RUSSIAN_HELP.items():
            for phrase in phrases:
                with self.subTest(role=role, phrase=phrase):
                    self.assertIn(phrase, shown)


if __name__ == "__main__":
    unittest.main()
