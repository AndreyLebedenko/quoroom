"""Task installer-bilingual, slice 2: the participant role speaks English by default and Russian on request."""

import re
import unittest
from dataclasses import dataclass, replace
from pathlib import Path

from tests.installer_fakes import completed
from tests.test_installer_participant import Machine, ParticipantCase
from sessionchat import kit
from sessionchat.installer import participant
from sessionchat.installer.boundaries import Probe
from sessionchat.installer.catalogue import LANGUAGES, STEP_PREFIX, catalogue
from sessionchat.installer.confirmation import WORD
from sessionchat.installer.main import (
    CANCELLED,
    DONE,
    FAILED,
    HUMAN,
    USAGE,
    main,
)
from sessionchat.installer.ownership import PurgeTarget
from sessionchat.installer.participant import (
    participant_consequence,
    participant_role,
)
from sessionchat.installer.steps import Run, State

ROLE = participant.ROLE
STORE = participant.STORE
MANIFEST = participant.KIT_MANIFEST
CYRILLIC = re.compile("[Ѐ-ӿ]")
STABLE_STEP_NAME = re.compile(r"[a-z]+(_[a-z]+)*")
PARTICIPANT_KEY = re.compile(r"""["'](participant\.[a-z_]+)["']""")
BROKER = "http://10.0.0.5:8770"
OFFLINE = Probe(None, "connection refused")


class RecordingMachine(Machine):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.spoken: set[str] = set()

    def agentschat(self, argv):
        done = super().agentschat(argv)
        self.spoken.update(f"{done.stdout}\n{done.stderr}".splitlines())
        return done


@dataclass
class RunSpy:
    name: str = "spy"
    run: Run | None = None

    def check(self, run: Run) -> State:
        self.run = run
        return State.DONE

    def apply(self, run: Run) -> None:
        return None

    @property
    def completed_steps(self) -> list[str]:
        return list(self.run.completed) if self.run else []


def watched(role, spy: RunSpy):
    return replace(role, install=(spy, *role.install), remove=(spy, *role.remove))


class ParticipantLanguageCase(ParticipantCase):
    def setUp(self):
        super().setUp()
        self.machine = RecordingMachine(self.home)
        self.spy = RunSpy()

    def roles(self):
        self.spy = RunSpy()
        return (watched(participant_role(version=self.version), self.spy),)

    def installed(self, lang):
        code, _ = self.install(lang=lang)
        self.assertEqual(code, DONE)

    def stored(self):
        self.machine.token("claude-code")
        self.machine.token("opencode")
        self.machine.installed_by.add("pipx")
        self.machine.seed_kit(["claude"])

    def own_words(self, given) -> str:
        shown = given.stdout.getvalue() + given.stderr.getvalue()
        return "\n".join(
            line for line in shown.splitlines() if line not in self.machine.spoken
        )


class Scenarios(ParticipantLanguageCase):
    def install_plain(self, lang):
        return self.install(lang=lang)

    def install_claude_only(self, lang):
        return self.install("--claude", lang=lang)

    def install_with_a_broker_address_on_windows(self, lang):
        self.without_path()
        return self.install("--broker-url", BROKER, platform="windows", lang=lang)

    def install_with_a_broker_address_on_linux(self, lang):
        self.without_path()
        return self.install("--broker-url", BROKER, lang=lang)

    def install_again_over_an_edited_kit(self, lang):
        self.installed(lang)
        self.machine.edit_kit("claude")
        return self.install(lang=lang)

    def install_over_a_package_found_in_another_tool(self, lang):
        self.record([(participant.PACKAGE_KIND, "uv")])
        self.machine.present = {"uv": True, "pipx": True}
        self.machine.installed_by.add("pipx")
        return self.install(lang=lang)

    def install_with_the_kit_question(self, lang):
        return self.install(stdin="3\n", interactive=True, lang=lang)

    def install_with_a_misunderstood_kit_answer(self, lang):
        return self.install(stdin="what?\n", interactive=True, lang=lang)

    def install_with_an_old_python(self, lang):
        self.version = (3, 9)
        return self.install(lang=lang)

    def install_without_tools_on_linux(self, lang):
        self.machine.present = {"uv": False, "pipx": False}
        return self.install(lang=lang)

    def install_without_tools_on_windows(self, lang):
        self.machine.present = {"uv": False, "pipx": False}
        return self.install(platform="windows", lang=lang)

    def install_with_a_silent_broker(self, lang):
        self.without_path()
        return self.install(probe=lambda url: OFFLINE, lang=lang)

    def install_with_a_broken_manifest(self, lang):
        path = self.home / STORE / MANIFEST
        path.parent.mkdir(parents=True)
        path.write_text("{}", encoding="utf-8")
        return self.install(lang=lang)

    def install_with_a_missing_option_value(self, lang):
        return self.install("--broker-url", lang=lang)

    def remove_everything(self, lang):
        self.installed(lang)
        return self.remove(lang=lang)

    def remove_one_cli(self, lang):
        self.installed(lang)
        return self.remove("--claude", lang=lang)

    def remove_over_an_edited_kit(self, lang):
        self.installed(lang)
        self.machine.edit_kit("claude")
        return self.remove(lang=lang)

    def remove_without_agentschat(self, lang):
        self.installed(lang)
        self.pipx_bin.unlink()
        return self.remove(lang=lang)

    def remove_a_package_nobody_recorded(self, lang):
        self.machine.installed_by.add("pipx")
        return self.remove(lang=lang)

    def remove_a_record_of_a_vanished_package(self, lang):
        self.record([(participant.PACKAGE_KIND, "pipx")])
        return self.remove(lang=lang)

    def purge_confirmed(self, lang):
        self.installed(lang)
        self.machine.token("claude-code")
        return self.remove("--purge", stdin=f"{WORD}\n", lang=lang)

    def purge_refused(self, lang):
        self.stored()
        return self.remove("--purge", stdin="no\n", lang=lang)

    def purge_with_foreign_files(self, lang):
        self.stored()
        self.machine.other("notes.json", '{"note": "mine"}')
        self.machine.other("log.txt", "hello")
        return self.remove("--purge", stdin=f"{WORD}\n", lang=lang)

    def purge_over_an_edited_kit(self, lang):
        self.installed(lang)
        self.machine.token("claude-code")
        self.machine.edit_kit("claude")
        return self.remove("--purge", stdin=f"{WORD}\n", lang=lang)

    def purge_over_an_empty_manifest(self, lang):
        self.machine.token("claude-code")
        self.manifest().write_text('{"files": []}', encoding="utf-8")
        return self.remove("--purge", stdin=f"{WORD}\n", lang=lang)

    def purge_after_a_narrowed_removal(self, lang):
        self.installed(lang)
        self.machine.token("claude-code")
        return self.remove("--purge", "--claude", stdin=f"{WORD}\n", lang=lang)

    TABLE = (
        ("install_plain", DONE),
        ("install_claude_only", DONE),
        ("install_with_a_broker_address_on_windows", DONE),
        ("install_with_a_broker_address_on_linux", DONE),
        ("install_again_over_an_edited_kit", DONE),
        ("install_over_a_package_found_in_another_tool", DONE),
        ("install_with_the_kit_question", DONE),
        ("install_with_a_misunderstood_kit_answer", FAILED),
        ("install_with_an_old_python", HUMAN),
        ("install_without_tools_on_linux", HUMAN),
        ("install_without_tools_on_windows", HUMAN),
        ("install_with_a_silent_broker", FAILED),
        ("install_with_a_broken_manifest", FAILED),
        ("install_with_a_missing_option_value", USAGE),
        ("remove_everything", DONE),
        ("remove_one_cli", DONE),
        ("remove_over_an_edited_kit", DONE),
        ("remove_without_agentschat", DONE),
        ("remove_a_package_nobody_recorded", DONE),
        ("remove_a_record_of_a_vanished_package", DONE),
        ("purge_confirmed", DONE),
        ("purge_refused", CANCELLED),
        ("purge_with_foreign_files", DONE),
        ("purge_over_an_edited_kit", DONE),
        ("purge_over_an_empty_manifest", DONE),
        ("purge_after_a_narrowed_removal", DONE),
    )

    def run_fresh(self, name, lang):
        self.setUp()
        return getattr(self, name)(lang)

    def test_the_table_names_real_scenarios(self):
        for name, _ in self.TABLE:
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(self, name)))

    def test_the_installers_own_words_are_english_in_every_scenario(self):
        for name, expected in self.TABLE:
            with self.subTest(name=name):
                code, given = self.run_fresh(name, "en")
                self.assertEqual(code, expected, given.stderr.getvalue())
                shown = self.own_words(given)
                self.assertTrue(shown)
                self.assertIsNone(CYRILLIC.search(shown), shown)

    def test_every_scenario_ends_the_same_way_in_both_languages(self):
        for name, expected in self.TABLE:
            with self.subTest(name=name):
                seen = {}
                for lang in LANGUAGES:
                    code, given = self.run_fresh(name, lang)
                    seen[lang] = (code, self.spy.completed_steps)
                    self.assertEqual(code, expected, given.stderr.getvalue())
                self.assertEqual(seen["en"], seen["ru"])


class EnglishOutputTests(ParticipantLanguageCase):
    def assert_english(self, given):
        shown = self.own_words(given)
        self.assertTrue(shown)
        self.assertIsNone(CYRILLIC.search(shown), shown)

    def test_a_full_install_prints_no_russian(self):
        code, given = self.install(lang="en")
        self.assertEqual(code, DONE)
        self.assert_english(given)

    def test_a_full_install_ends_with_the_restart_and_the_login(self):
        _, given = self.install(lang="en")
        self.assertEqual(
            given.stdout.getvalue().splitlines()[-1],
            "Restart the open Claude Code and OpenCode sessions: running ones do "
            "not see the new kit. In an agent session, run /chatlogin and name the "
            "session.",
        )

    def test_a_single_cli_install_names_only_that_cli(self):
        _, given = self.install("--claude", lang="en")
        last = given.stdout.getvalue().splitlines()[-1]
        self.assertIn("Restart the open Claude Code sessions", last)
        self.assertNotIn("OpenCode", last)

    def test_a_repeat_install_with_nothing_changed_asks_for_no_restart(self):
        self.installed("en")
        _, given = self.install(lang="en")
        self.assertIn("no need to restart the sessions", given.stdout.getvalue())

    def test_the_step_names_are_rendered_in_english(self):
        self.installed("en")
        _, given = self.install(lang="en")
        self.assertIn(
            "Install the quoroom package: already done.", given.stdout.getvalue()
        )

    def test_a_removal_prints_no_russian(self):
        self.installed("en")
        code, given = self.remove(lang="en")
        self.assertEqual(code, DONE)
        self.assert_english(given)
        self.assertIn("The kit and the package are removed.", given.stdout.getvalue())

    def test_a_removal_names_the_install_command_in_english(self):
        self.installed("en")
        _, given = self.remove(lang="en")
        self.assertIn(
            "To install it back: install.sh --role participant", given.stdout.getvalue()
        )

    def test_a_purge_accepts_the_untranslated_word_and_prints_no_russian(self):
        self.installed("en")
        self.machine.token("claude-code")
        code, given = self.remove("--purge", stdin=f"{WORD}\n", lang="en")
        self.assertEqual(code, DONE)
        self.assert_english(given)
        self.assertIn(
            f"To continue, type {WORD} and press Enter.", given.stdout.getvalue()
        )
        self.assertFalse((self.home / STORE / "claude-code.json").exists())

    def test_the_purge_confirmation_says_the_consequence_in_english(self):
        self.stored()
        _, given = self.remove("--purge", stdin="no\n", lang="en")
        shown = given.stdout.getvalue()
        self.assertIn("Consequence: the session files will be gone together", shown)
        self.assertIn(
            "The conversation in the room on the server stays in place.", shown
        )

    def test_a_refused_purge_prints_no_russian(self):
        self.stored()
        code, given = self.remove("--purge", stdin="no\n", lang="en")
        self.assertEqual(code, CANCELLED)
        self.assert_english(given)

    def test_a_usage_error_of_a_participant_option_prints_no_russian(self):
        code, given = self.install("--broker-url", lang="en")
        self.assertEqual(code, USAGE)
        self.assertTrue(given.stderr.getvalue().startswith("AGENTSCHAT: "))
        self.assert_english(given)

    def test_a_misunderstood_kit_answer_names_the_flags_in_english(self):
        code, given = self.install(stdin="what?\n", interactive=True, lang="en")
        self.assertEqual(code, FAILED)
        self.assertIn(
            "could not understand the CLI choice: 'what?'. "
            "Run again with --claude or --opencode.",
            given.stderr.getvalue(),
        )

    def test_a_failure_report_prints_no_russian(self):
        code, given = self.install(probe=lambda url: OFFLINE, lang="en")
        self.assertEqual(code, FAILED)
        self.assert_english(given)
        shown = given.stderr.getvalue()
        self.assertIn('Failed at step "Check the broker".', shown)
        self.assertIn("the broker does not answer at", shown)
        self.assertIn("    Install the quoroom package", shown)

    def test_a_kit_conflict_is_named_in_english_around_the_clients_own_words(self):
        self.machine.kit_conflict = True
        code, given = self.install(lang="en")
        self.assertEqual(code, FAILED)
        self.assertIn("Reason: Quoroom kit conflict: ", given.stderr.getvalue())

    def test_a_failed_package_install_names_the_tool_in_english(self):
        self.machine.fails = "pipx install"
        code, given = self.install(lang="en")
        self.assertEqual(code, FAILED)
        self.assertIn(
            "Reason: pipx failed to install the package: ", given.stderr.getvalue()
        )

    def test_a_missing_kit_executable_is_warned_about_in_english(self):
        self.installed("en")
        self.pipx_bin.unlink()
        _, given = self.remove(lang="en")
        self.assertIn(
            f"agentschat is not installed: the kit files and {MANIFEST} are left in "
            "place, remove them by hand.",
            given.stderr.getvalue(),
        )

    def test_the_answer_both_is_accepted_in_english(self):
        code, _ = self.install(stdin="both\n", interactive=True, lang="en")
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_the_kit_question_lists_the_english_word_for_both(self):
        _, given = self.install(stdin="1\n", interactive=True, lang="en")
        self.assertIn("    3. both", given.stdout.getvalue())
        self.assertNotIn("оба", given.stdout.getvalue())


class RussianOutputTests(ParticipantLanguageCase):
    def test_the_kit_question_lists_the_russian_word_for_both(self):
        _, given = self.install(stdin="1\n", interactive=True, lang="ru")
        self.assertIn("    3. оба", given.stdout.getvalue())

    def test_the_russian_answer_both_is_accepted(self):
        code, _ = self.install(stdin="оба\n", interactive=True, lang="ru")
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_the_english_answer_both_is_still_accepted_in_russian(self):
        code, _ = self.install(stdin="both\n", interactive=True, lang="ru")
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_the_flag_switches_a_run_that_started_english_to_russian(self):
        code, given = self.install("--lang", "ru", lang="en")
        self.assertEqual(code, DONE)
        self.assertIn("Брокер отвечает на", given.stdout.getvalue())


class RecordsAcrossLanguagesTests(ParticipantLanguageCase):
    def installed_then_purged(self, written, purged):
        code, _ = self.install("--lang", written)
        self.assertEqual(code, DONE)
        self.machine.token("claude-code")
        self.machine.log.clear()
        code, given = self.remove("--purge", "--lang", purged, stdin=f"{WORD}\n")
        self.assertEqual(code, DONE, given.stderr.getvalue())
        return given

    def assert_purged_as_recorded(self, given):
        token = self.home / STORE / "claude-code.json"
        self.assertIn(f"    participant: session {token}", given.stdout.getvalue())
        self.assertFalse(token.exists())
        self.assertIn("pipx uninstall quoroom", self.machine.log)
        self.assertFalse(participant.record_path(self.given()).exists())

    def test_a_record_written_in_russian_is_purged_in_english(self):
        self.assert_purged_as_recorded(self.installed_then_purged("ru", "en"))

    def test_a_record_written_in_english_is_purged_in_russian(self):
        self.assert_purged_as_recorded(self.installed_then_purged("en", "ru"))

    def test_the_record_does_not_depend_on_the_language(self):
        records = []
        for lang in LANGUAGES:
            self.setUp()
            self.install("--lang", lang)
            records.append(self.recorded())
        self.assertEqual(records, [["pipx"], ["pipx"]])


class ConsequenceTests(unittest.TestCase):
    def targets(self, *roles):
        return [PurgeTarget(role, "session", f"id-{role}") for role in roles]

    def test_the_consequence_follows_the_language(self):
        targets = self.targets("participant")
        self.assertIn(
            "the only way back into the room is a new login",
            participant_consequence(targets, "en"),
        )
        self.assertIn("только новым входом", participant_consequence(targets, "ru"))

    def test_the_english_consequence_has_no_russian(self):
        for roles in (("participant",), ("participant", "server")):
            with self.subTest(roles=roles):
                self.assertIsNone(
                    CYRILLIC.search(participant_consequence(self.targets(*roles), "en"))
                )

    def test_the_room_sentence_is_dropped_beside_the_server_in_english(self):
        said = participant_consequence(self.targets("participant", "server"), "en")
        self.assertNotIn("stays in place", said)


class HelpTests(ParticipantLanguageCase):
    def helped(self, *argv, lang):
        given = self.given(lang=lang)
        code = main([*argv, "--help"], given, (participant_role(),))
        self.assertEqual(code, DONE)
        return given.stdout.getvalue()

    def test_the_help_of_the_participant_options_has_no_russian_by_default(self):
        shown = self.helped(lang="en")
        self.assertIsNone(CYRILLIC.search(shown), shown)

    def test_the_help_describes_every_participant_option_in_english(self):
        shown = self.helped(lang="en")
        for phrase in (
            f"broker address (default {participant.DEFAULT_BROKER})",
            "kit for Claude Code only",
            "kit for OpenCode only",
        ):
            self.assertIn(phrase, shown)

    def test_the_help_follows_the_flag_for_the_participant_options(self):
        shown = self.helped("--lang", "ru", lang="en")
        for phrase in (
            f"адрес брокера (по умолчанию {participant.DEFAULT_BROKER})",
            "набор только для Claude Code",
            "набор только для OpenCode",
        ):
            self.assertIn(phrase, shown)


class StableIdentityTests(unittest.TestCase):
    def names(self):
        role = participant_role()
        steps = role.install + role.remove + role.purge
        return {step.name for step in steps}

    def test_every_participant_step_name_is_a_stable_english_identifier(self):
        for name in self.names():
            with self.subTest(name=name):
                self.assertRegex(name, STABLE_STEP_NAME)

    def test_every_participant_step_name_has_a_label_in_both_languages(self):
        for lang in LANGUAGES:
            for name in self.names():
                with self.subTest(lang=lang, name=name):
                    self.assertIn(f"{STEP_PREFIX}{name}", catalogue(lang))

    def test_the_labels_differ_between_the_languages(self):
        for name in self.names():
            with self.subTest(name=name):
                key = f"{STEP_PREFIX}{name}"
                self.assertNotEqual(catalogue("en")[key], catalogue("ru")[key])

    def test_every_participant_message_is_used_by_the_module(self):
        source = Path(participant.__file__).read_text(encoding="utf-8")
        used = set(PARTICIPANT_KEY.findall(source))
        defined = {key for key in catalogue("en") if key.startswith("participant.")}
        self.assertEqual(defined - used, set(), "messages nobody prints")
        self.assertEqual(used - defined, set(), "messages nobody wrote")

    def test_the_participant_module_holds_no_russian_to_recognise_the_client_by(self):
        source = Path(participant.__file__).read_text(encoding="utf-8")
        self.assertIsNone(CYRILLIC.search(source), source)


class KitFailureTests(ParticipantLanguageCase):
    def said(self, lang, result):
        run = self.run_for(self.given(lang=lang))
        return run, participant.kit_failure(run, result)

    def conflict_report(self, target: Path) -> str:
        return kit.Report(
            kit.COMMAND_INSTALL,
            kit.CODE_CONFLICT,
            (kit.Step(kit.Action.CONFLICT, target, "claude"),),
        ).as_json()

    def test_the_code_the_client_reports_tells_a_conflict_apart_in_both_languages(self):
        target = Path("some-file")
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                run, said = self.said(
                    lang, completed(self.conflict_report(target), "", 1)
                )
                self.assertEqual(
                    said, run.t("participant.kit_conflict", detail=str(target))
                )

    def test_any_other_failure_of_the_client_is_a_plain_failure_in_both_languages(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                run, said = self.said(lang, completed("", "boom", 1))
                self.assertEqual(said, run.t("participant.kit_failed", detail="boom"))

    def test_a_client_that_spells_out_a_refusal_is_a_plain_failure_in_both_languages(
        self,
    ):
        refusal = str(
            kit.KitConflict(
                [kit.Step(kit.Action.CONFLICT, Path("some-file"), "claude")]
            )
        )
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                run, said = self.said(lang, completed(refusal, "", 1))
                self.assertEqual(said, run.t("participant.kit_failed", detail=refusal))


if __name__ == "__main__":
    unittest.main()
