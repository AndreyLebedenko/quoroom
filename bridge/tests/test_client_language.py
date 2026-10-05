"""Task english-release-07: how the client knows the room language."""

import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import requests

from sessionchat import client, client_language
from sessionchat.i18n import Catalogue
from tests.catalogue_contract import CatalogueContract

TOKEN = "test-token"
STATUS_ANSWER = {
    "language": "ru",
    "sessions": [
        {
            "agent": "claude-code",
            "state": "not_connected",
            "line": "claude-code  не подключён",
        }
    ],
}


class Answer:
    def __init__(self, data=None, status=200, text="", content_type="application/json"):
        self.status_code = status
        self._data = data
        self.text = text
        self.headers = {"Content-Type": content_type}

    def json(self):
        return self._data


def write_catalogue(directory: Path, english: dict, russian: dict) -> Catalogue:
    (directory / "en.json").write_text(json.dumps(english), encoding="utf-8")
    (directory / "ru.json").write_text(
        json.dumps(russian, ensure_ascii=False), encoding="utf-8"
    )
    return Catalogue.from_path(directory)


class ClientLanguageTestCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name)
        self.store = self.home / ".agentschat"
        self.catalogue_dir = self.home / "catalogue"
        self.catalogue_dir.mkdir()
        self.catalogue = write_catalogue(
            self.catalogue_dir,
            {
                **client.CATALOGUE.templates("en"),
                "failure_line": "ERR-EN {message}",
                "probe": "English probe {name}",
            },
            {
                **client.CATALOGUE.templates("ru"),
                "failure_line": "ERR-RU {message}",
                "probe": "Русская проба {name}",
            },
        )
        for item in (
            patch.dict(
                os.environ, {"HOME": str(self.home), "USERPROFILE": str(self.home)}
            ),
            patch.object(client, "STORE", self.store),
            patch.object(client, "CATALOGUE", self.catalogue),
            patch.object(client, "ROOM_LANGUAGE", client_language.RoomLanguage()),
        ):
            item.start()
            self.addCleanup(item.stop)

    @property
    def language_file(self) -> Path:
        return self.store / "language"

    def remember(self, text: str) -> None:
        self.store.mkdir(parents=True, exist_ok=True)
        self.language_file.write_text(text, encoding="utf-8")

    def fresh_run(self) -> None:
        client.ROOM_LANGUAGE = client_language.RoomLanguage()

    def store_credentials(self, agent: str = "claude-code") -> None:
        self.store.mkdir(parents=True, exist_ok=True)
        (self.store / f"{agent}.json").write_text(
            json.dumps({"agent": agent, "token": TOKEN}), encoding="utf-8"
        )

    def say_args(self) -> argparse.Namespace:
        return argparse.Namespace(agent="claude-code", text="hi", file=None)

    def silently(self, call, *args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return call(*args)


class SpeakTests(ClientLanguageTestCase):
    def test_with_no_broker_and_no_remembered_value_the_client_speaks_english(self):
        self.assertEqual(client.speak("probe", name="x"), "English probe x")

    def test_a_missing_key_is_an_error_not_a_fallback(self):
        with self.assertRaises(KeyError):
            client.speak("no_such_key")

    def test_a_missing_parameter_is_an_error_not_a_blank(self):
        with self.assertRaises(KeyError):
            client.speak("probe")

    def test_the_remembered_value_decides_the_language(self):
        self.remember("ru\n")
        self.assertEqual(client.speak("probe", name="x"), "Русская проба x")


class PrecedenceTests(ClientLanguageTestCase):
    TABLE = [
        ("ru", "en", "en", "ru"),
        ("en", "ru", "ru", "en"),
        (None, "ru", "en", "ru"),
        (None, "en", "ru", "en"),
        (None, None, "ru", "ru"),
        (None, None, "en", "en"),
        (None, None, None, "en"),
        ("ru", None, None, "ru"),
        ("ru", "en", None, "ru"),
        (None, "ru", None, "ru"),
    ]

    def test_explicit_beats_the_answer_of_this_run_beats_the_remembered_value_beats_english(
        self,
    ):
        for explicit, answered, remembered, expected in self.TABLE:
            with self.subTest(
                explicit=explicit, answered=answered, remembered=remembered
            ):
                if self.language_file.exists():
                    self.language_file.unlink()
                if remembered:
                    self.remember(remembered)
                run = client_language.RoomLanguage()
                run.insist(explicit)
                run.answered = answered
                self.assertEqual(run.current(self.store), expected)

    def test_an_invalid_value_in_any_source_is_skipped_for_the_next_one(self):
        for bad in ("fr", "RU", "", None, 5, ["ru"], object()):
            with self.subTest(bad=bad):
                self.remember("ru")
                run = client_language.RoomLanguage()
                run.insist(bad)
                run.answered = bad
                self.assertEqual(run.current(self.store), "ru")

    def test_main_hands_an_explicit_language_flag_to_the_run(self):
        seen = []
        parsed = argparse.Namespace(
            run=lambda args: seen.append(client.speak("probe", name="x")), lang="ru"
        )
        self.remember("en")
        with patch.object(argparse.ArgumentParser, "parse_args", return_value=parsed):
            client.main()
        self.assertEqual(seen, ["Русская проба x"])

    def test_main_without_a_language_flag_leaves_the_remembered_value_in_charge(self):
        seen = []
        parsed = argparse.Namespace(
            run=lambda args: seen.append(client.speak("probe", name="x"))
        )
        self.remember("ru")
        with patch.object(argparse.ArgumentParser, "parse_args", return_value=parsed):
            client.main()
        self.assertEqual(seen, ["Русская проба x"])


class RememberedFileTests(ClientLanguageTestCase):
    def test_a_broker_answer_creates_the_file_with_the_language(self):
        client.learn_language({"language": "ru"})
        self.assertEqual(self.language_file.read_text(encoding="utf-8").strip(), "ru")

    def test_a_different_answer_replaces_the_remembered_value(self):
        self.remember("ru")
        client.learn_language({"language": "en"})
        self.assertEqual(self.language_file.read_text(encoding="utf-8").strip(), "en")

    def test_an_answer_wins_over_the_remembered_value_within_the_same_run(self):
        self.remember("ru")
        client.learn_language({"language": "en"})
        self.assertEqual(client.speak("probe", name="x"), "English probe x")

    def test_the_file_is_the_only_thing_written_and_it_is_not_per_agent(self):
        client.learn_language({"language": "ru"})
        self.assertEqual([path.name for path in self.store.iterdir()], ["language"])

    def test_an_unchanged_answer_does_not_rewrite_the_file(self):
        self.remember("ru\n")
        with patch.object(client_language.os, "replace") as replace:
            client.learn_language({"language": "ru"})
        replace.assert_not_called()

    def test_a_changed_answer_rewrites_the_file_once(self):
        self.remember("ru\n")
        with patch.object(client_language.os, "replace", wraps=os.replace) as replace:
            client.learn_language({"language": "en"})
        self.assertEqual(replace.call_count, 1)

    def test_a_failed_replacement_keeps_the_old_value_and_leaves_no_temporary_file(
        self,
    ):
        self.remember("en\n")
        with patch.object(client_language.os, "replace", side_effect=OSError("busy")):
            client.learn_language({"language": "ru"})
        self.assertEqual(
            [path.name for path in self.store.iterdir()],
            ["language"],
        )
        self.assertEqual(self.language_file.read_text(encoding="utf-8").strip(), "en")

    def test_a_store_that_cannot_be_written_does_not_break_the_command(self):
        blocker = self.home / "blocker"
        blocker.write_text("a file, not a directory", encoding="utf-8")
        with patch.object(client, "STORE", blocker / ".agentschat"):
            client.learn_language({"language": "ru"})
            self.assertEqual(client.speak("probe", name="x"), "Русская проба x")

    def test_answers_without_a_usable_language_write_nothing(self):
        for answer in (
            {},
            {"language": "fr"},
            {"language": None},
            {"language": 5},
            {"language": ["ru"]},
            ["ru"],
            "ru",
            None,
        ):
            with self.subTest(answer=answer):
                client.learn_language(answer)
                self.assertFalse(self.store.exists())


class CorruptFileTests(ClientLanguageTestCase):
    def test_an_unreadable_or_invalid_file_means_english_not_an_error(self):
        for name, content in (
            ("empty", b""),
            ("unknown code", b"klingon\n"),
            ("wrong case", b"RU\n"),
            ("binary", b"\xff\xfe\x00\x01"),
            ("two lines", b"ru\nen\n"),
            ("json", b'{"language": "ru"}'),
        ):
            with self.subTest(name):
                self.store.mkdir(parents=True, exist_ok=True)
                self.language_file.write_bytes(content)
                self.assertEqual(client.speak("probe", name="x"), "English probe x")

    def test_a_directory_in_place_of_the_file_means_english(self):
        self.language_file.mkdir(parents=True)
        self.assertEqual(client.speak("probe", name="x"), "English probe x")

    def test_a_valid_answer_repairs_a_corrupt_file(self):
        self.remember("klingon")
        client.learn_language({"language": "en"})
        self.assertEqual(self.language_file.read_text(encoding="utf-8").strip(), "en")

    def test_a_surrounding_blank_in_the_file_is_tolerated(self):
        self.remember("  ru \r\n")
        self.assertEqual(client.speak("probe", name="x"), "Русская проба x")


class FailTests(ClientLanguageTestCase):
    def test_failure_prints_the_catalogue_frame_around_the_message_and_exits_1(self):
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit) as stop:
            client.fail("something broke")
        self.assertEqual(stop.exception.code, 1)
        self.assertEqual(errors.getvalue(), "ERR-EN something broke\n")

    def test_failure_follows_the_remembered_language(self):
        self.remember("ru")
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            client.fail("something broke")
        self.assertEqual(errors.getvalue(), "ERR-RU something broke\n")

    def test_the_message_is_inserted_whole_even_with_braces(self):
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            client.fail("{token} {0}")
        self.assertEqual(errors.getvalue(), "ERR-EN {token} {0}\n")

    def test_with_the_real_catalogue_failure_text_is_the_historical_line(self):
        with patch.object(client, "CATALOGUE", client_catalogue()):
            for language in ("en", "ru"):
                with self.subTest(language=language):
                    self.remember(language)
                    errors = io.StringIO()
                    with redirect_stderr(errors), self.assertRaises(SystemExit):
                        client.fail("сессия не подключена")
                    self.assertEqual(
                        errors.getvalue(), "AGENTSCHAT: сессия не подключена\n"
                    )

    def test_an_unreachable_broker_is_reported_in_english_when_nothing_is_known(self):
        errors = io.StringIO()
        with (
            patch.object(
                client.requests, "get", side_effect=requests.ConnectionError("down")
            ),
            redirect_stderr(errors),
            self.assertRaises(SystemExit),
        ):
            client.do_status(argparse.Namespace())
        self.assertTrue(errors.getvalue().startswith("ERR-EN "), errors.getvalue())

    def test_after_one_answer_under_ru_an_unreachable_broker_is_reported_in_russian(
        self,
    ):
        with patch.object(
            client.requests,
            "get",
            return_value=Answer(STATUS_ANSWER),
        ):
            self.silently(client.do_status, argparse.Namespace())
        self.fresh_run()
        errors = io.StringIO()
        with (
            patch.object(
                client.requests, "get", side_effect=requests.ConnectionError("down")
            ),
            redirect_stderr(errors),
            self.assertRaises(SystemExit),
        ):
            client.do_status(argparse.Namespace())
        self.assertTrue(errors.getvalue().startswith("ERR-RU "), errors.getvalue())


def client_catalogue() -> Catalogue:
    return Catalogue("sessionchat", "client_messages")


class EveryBrokerAnswerRefreshesTheLanguageTests(ClientLanguageTestCase):
    def assert_refreshed(self):
        self.assertEqual(self.language_file.read_text(encoding="utf-8").strip(), "ru")

    def test_login(self):
        answer = Answer(
            {"token": TOKEN, "room": "room", "mode": "push", "language": "ru"}
        )
        with patch.object(client.requests, "post", return_value=answer):
            self.silently(
                client.do_login,
                argparse.Namespace(agent="claude-code", label="", reconnect=False),
            )
        self.assert_refreshed()

    def test_say(self):
        self.store_credentials()
        answer = Answer({"event_id": "$e", "language": "ru"})
        with patch.object(client.requests, "post", return_value=answer):
            self.silently(client.do_say, self.say_args())
        self.assert_refreshed()

    def test_inbox(self):
        self.store_credentials()
        answer = Answer({"pending": [], "language": "ru"})
        with patch.object(client.requests, "get", return_value=answer):
            self.silently(client.do_inbox, argparse.Namespace(agent="claude-code"))
        self.assert_refreshed()

    def test_wait_poll(self):
        answer = Answer({"rendered": "envelope", "language": "ru"})
        with patch.object(client.requests, "get", return_value=answer):
            self.assertEqual(client.poll_once("claude-code", TOKEN), "envelope")
        self.assert_refreshed()

    def test_an_empty_wait_window_changes_nothing(self):
        self.remember("ru")
        with patch.object(client.requests, "get", return_value=Answer(status=204)):
            self.assertIsNone(client.poll_once("claude-code", TOKEN))
        self.assert_refreshed()

    def test_status_remembers_the_language(self):
        answer = Answer(STATUS_ANSWER)
        with patch.object(client.requests, "get", return_value=answer):
            self.silently(client.do_status, argparse.Namespace())
        self.assert_refreshed()

    def test_status_prints_the_text_of_the_answer_exactly_as_before(self):
        answer = Answer(STATUS_ANSWER)
        output = io.StringIO()
        with (
            patch.object(client.requests, "get", return_value=answer),
            redirect_stdout(output),
        ):
            client.do_status(argparse.Namespace())
        self.assertEqual(output.getvalue(), "claude-code  не подключён\n")

    def test_status_prints_a_plain_text_answer_untouched_and_learns_nothing(self):
        answer = Answer(
            text="claude-code  не подключён\n", content_type="text/plain; charset=utf-8"
        )
        output = io.StringIO()
        with (
            patch.object(client.requests, "get", return_value=answer),
            redirect_stdout(output),
        ):
            client.do_status(argparse.Namespace())
        self.assertEqual(output.getvalue(), "claude-code  не подключён\n")
        self.assertFalse(self.store.exists())


class ClientCatalogueTests(CatalogueContract, unittest.TestCase):
    catalogue = client_catalogue()

    def test_the_failure_frame_is_in_both_languages(self):
        for language in ("en", "ru"):
            with self.subTest(language=language):
                self.assertEqual(
                    self.catalogue.text(language, "failure_line", message="m"),
                    "AGENTSCHAT: m",
                )


if __name__ == "__main__":
    unittest.main()
