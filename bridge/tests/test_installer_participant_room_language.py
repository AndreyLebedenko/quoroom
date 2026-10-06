"""Task english-release-22: the participant install teaches the client the room language."""

import unittest

from tests.catalogue_contract import placeholders
from tests.test_installer_participant import Machine, ParticipantCase
from sessionchat import client_language
from sessionchat.installer import participant
from sessionchat.installer.catalogue import LANGUAGES, catalogue
from sessionchat.installer.main import DONE
from sessionchat.installer.participant import DEFAULT_BROKER, URL_VARIABLE

OTHER_BROKER = "http://10.0.0.5:8770"
STEP_LABEL = "learn_room_language"
NOT_LEARNED_KEY = "participant.language_not_learned"
NOT_LEARNED_RU = (
    f"Язык комнаты не удалось узнать у {DEFAULT_BROKER}: agentschat говорит "
    "по-английски, пока брокер не ответит на команду клиента."
)
CLAIMS_RU_AND_PRINTS_NOTHING_ELSE = "Язык комнаты: ru\n"


class RoomLanguageStepCase(ParticipantCase):
    def answering(self, language: str = "en", mode: str = "ok") -> None:
        self.machine = Machine(self.home, room_language=language, status_mode=mode)

    def store(self):
        return self.home / participant.STORE

    def remembered(self) -> str | None:
        return client_language.remembered(self.store())

    def holds(self, language: str) -> None:
        client_language.remember(self.store(), language)

    def holds_anything_but_a_language(self) -> None:
        self.store().mkdir(parents=True, exist_ok=True)
        (self.store() / "language").write_text("fr\n", encoding="utf-8")

    def status_calls(self) -> list[str]:
        return [line for line in self.machine.log if line.endswith(" status")]

    def everything(self, given) -> str:
        return given.stdout.getvalue() + given.stderr.getvalue()


class TheLanguageIsRememberedTests(RoomLanguageStepCase):
    def test_the_install_leaves_the_room_language_in_the_client_store(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.setUp()
                self.answering(language)
                code, _ = self.install()
                self.assertEqual(code, DONE)
                self.assertEqual(self.remembered(), language)

    def test_the_client_is_asked_about_the_room_language_once(self):
        self.answering()
        self.install()
        self.assertEqual(len(self.status_calls()), 1)

    def test_a_second_install_does_not_run_the_client_again(self):
        self.answering("ru")
        self.install()
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertEqual(len(self.status_calls()), 1)

    def test_a_store_that_already_holds_a_language_is_left_alone(self):
        self.answering("ru")
        self.holds("en")
        self.install()
        self.assertEqual(self.status_calls(), [])
        self.assertEqual(self.remembered(), "en")

    def test_a_store_that_holds_something_else_is_not_taken_for_a_language(self):
        self.answering()
        self.holds_anything_but_a_language()
        self.install()
        self.assertEqual(len(self.status_calls()), 1)
        self.assertEqual(self.remembered(), "en")


class TheChildGetsTheBrokersAddressTests(RoomLanguageStepCase):
    def test_the_address_of_the_installer_reaches_the_child(self):
        self.answering()
        self.install("--broker-url", OTHER_BROKER)
        self.assertEqual(self.machine.status_env, {URL_VARIABLE: OTHER_BROKER})

    def test_the_default_address_is_passed_explicitly_instead_of_inherited(self):
        self.answering()
        self.install()
        self.assertEqual(self.machine.status_env, {URL_VARIABLE: DEFAULT_BROKER})

    def test_the_home_of_the_person_is_left_to_the_child_to_inherit(self):
        self.answering()
        self.install()
        self.assertEqual(
            [name for name in self.machine.status_env if name != URL_VARIABLE], []
        )


class TheDecisionIsTheResultLineTests(RoomLanguageStepCase):
    def test_a_result_line_with_the_language_teaches_the_step_without_any_table(self):
        self.answering("ru", mode="quiet")
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertNotIn(NOT_LEARNED_RU, self.everything(given))

    def test_words_the_client_printed_about_the_language_are_not_relayed(self):
        self.answering("ru", mode="words")
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertNotIn(CLAIMS_RU_AND_PRINTS_NOTHING_ELSE, self.everything(given))
        self.assertIn(NOT_LEARNED_RU, given.stdout.getvalue())

    def test_a_result_line_of_another_command_teaches_the_step_nothing(self):
        self.answering(mode="another-command")
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(NOT_LEARNED_RU, given.stdout.getvalue())


class AFailureOfTheStepIsNotAFailureOfTheInstallTests(RoomLanguageStepCase):
    def test_a_client_that_cannot_be_run_leaves_the_install_successful(self):
        self.answering(mode="missing")
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(NOT_LEARNED_RU, given.stderr.getvalue())

    def test_a_client_whose_output_cannot_be_decoded_leaves_the_install_successful(
        self,
    ):
        self.answering(mode="undecodable")
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(NOT_LEARNED_RU, given.stderr.getvalue())

    def test_a_client_that_exits_with_a_failure_leaves_the_install_successful(self):
        self.answering(mode="refuses")
        code, _ = self.install()
        self.assertEqual(code, DONE)

    def test_a_client_that_reports_a_failure_leaves_the_install_successful(self):
        self.answering(mode="not-ok")
        code, _ = self.install()
        self.assertEqual(code, DONE)

    def test_nothing_is_remembered_when_the_client_did_not_answer(self):
        self.answering(mode="refuses")
        self.install()
        self.assertIsNone(self.remembered())

    def test_the_report_names_the_address_the_language_was_not_learned_from(self):
        self.answering(mode="refuses")
        _, given = self.install("--broker-url", OTHER_BROKER)
        self.assertIn(
            NOT_LEARNED_RU.replace(DEFAULT_BROKER, OTHER_BROKER),
            given.stdout.getvalue(),
        )

    def test_the_report_says_nothing_about_the_language_when_it_was_learned(self):
        self.answering()
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertNotIn("не удалось узнать", self.everything(given))

    def test_an_english_install_reports_a_missing_language_in_english(self):
        self.answering(mode="refuses")
        code, given = self.install(lang="en")
        self.assertEqual(code, DONE)
        self.assertIn(
            f"The room language was not learned from {DEFAULT_BROKER}",
            given.stdout.getvalue(),
        )

    def test_the_restart_hint_stays_the_last_line_of_the_report(self):
        self.answering(mode="refuses")
        _, given = self.install()
        self.assertIn("/chatlogin", given.stdout.getvalue().splitlines()[-1])


class TheStepSpeaksInBothLanguagesTests(RoomLanguageStepCase):
    def test_the_step_label_exists_in_both_languages(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                self.assertIn(f"step.{STEP_LABEL}", catalogue(lang))

    def test_the_sentence_about_a_missing_language_exists_in_both_languages(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                self.assertIn(NOT_LEARNED_KEY, catalogue(lang))

    def test_the_sentence_names_the_same_placeholder_in_both_languages(self):
        self.assertEqual(
            placeholders(catalogue("en")[NOT_LEARNED_KEY]),
            placeholders(catalogue("ru")[NOT_LEARNED_KEY]),
        )

    def test_the_run_prints_the_step_label_of_the_room_language_in_russian(self):
        self.answering()
        _, given = self.install()
        self.assertIn(
            f"{catalogue('ru')[f'step.{STEP_LABEL}']}: готово.", given.stdout.getvalue()
        )


if __name__ == "__main__":
    unittest.main()
