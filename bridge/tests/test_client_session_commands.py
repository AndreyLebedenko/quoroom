"""Task english-release-08: login, logout and status - sentences and the result line."""

import argparse
import ast
import io
import itertools
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import requests

from sessionchat import client, client_language
from sessionchat.i18n import Catalogue
from tests.catalogue_contract import CYRILLIC
from tests.test_client_language import Answer
from tests.result_line import MARK as PREFIX
from tests.result_line import read_result, result_lines, without_result
from tests.test_client_refusals import refusal

LANGUAGES = ("en", "ru")
AGENT = "claude-code"
ROOM = "!room:local"
SECRET = "secret-token-0123456789abcdef"
BROKER_URL = "http://127.0.0.1:8770"
WHAT_HAPPENED = "unreachable: down"


def login_answer(language: str, mode: str = "listener", reconnected: bool = False):
    body = {"token": SECRET, "room": ROOM, "mode": mode, "language": language}
    if reconnected:
        body["reconnected"] = True
    return Answer(body)


class Outcome:
    def __init__(self, stdout: str, stderr: str, code: int):
        self.stdout, self.stderr, self.code = stdout, stderr, code

    @property
    def everything(self) -> str:
        return self.stdout + self.stderr

    @property
    def result(self) -> dict:
        return read_result(self.stdout)


class SessionCommandCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name)
        self.store = self.home / ".agentschat"
        for item in (
            patch.dict(
                os.environ,
                {
                    "HOME": str(self.home),
                    "USERPROFILE": str(self.home),
                    "AGENTSCHAT_URL": BROKER_URL,
                    "COLUMNS": "200",
                },
            ),
            patch.object(client, "STORE", self.store),
            patch.object(client, "ROOM_LANGUAGE", client_language.RoomLanguage()),
        ):
            item.start()
            self.addCleanup(item.stop)

    def remember(self, language: str) -> None:
        self.store.mkdir(parents=True, exist_ok=True)
        (self.store / "language").write_text(language, encoding="utf-8")

    def store_credentials(self, agent: str = AGENT) -> Path:
        self.store.mkdir(parents=True, exist_ok=True)
        path = self.store / f"{agent}.json"
        path.write_text(json.dumps({"agent": agent, "token": SECRET}), encoding="utf-8")
        return path

    def run_command(self, run, **arguments) -> Outcome:
        stdout, stderr = io.StringIO(), io.StringIO()
        code = 0
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                run(argparse.Namespace(**arguments))
            except SystemExit as stopped:
                code = stopped.code
        return Outcome(stdout.getvalue(), stderr.getvalue(), code)

    def login(self, posted=None, failure=None, **overrides) -> Outcome:
        arguments = {"agent": AGENT, "label": "", "reconnect": False, **overrides}
        with patch.object(
            client.requests, "post", return_value=posted, side_effect=failure
        ):
            return self.run_command(client.do_login, **arguments)

    def logout(self, posted=None, failure=None, force=False) -> Outcome:
        with patch.object(
            client.requests, "post", return_value=posted, side_effect=failure
        ):
            return self.run_command(client.do_logout, agent=AGENT, force=force)

    def status(self, got=None, failure=None) -> Outcome:
        with patch.object(
            client.requests, "get", return_value=got, side_effect=failure
        ):
            return self.run_command(client.do_status)


LOGIN_SENTENCES = {
    ("listener", False): {
        "ru": (
            f"AGENTSCHAT: сессия {AGENT} подключена к комнате {ROOM}.\n"
            "Теперь запусти listener ФОНОВОЙ командой и не жди её завершения:\n"
            f"    agentschat wait --agent {AGENT}\n"
            "Когда listener завершится, ты будешь разбужен его выводом. Первым "
            "действием после пробуждения подними listener заново.\n"
        ),
        "en": (
            f"AGENTSCHAT: session {AGENT} is connected to room {ROOM}.\n"
            "Now start the listener with a BACKGROUND command and do not wait for "
            "it to finish:\n"
            f"    agentschat wait --agent {AGENT}\n"
            "When the listener finishes, its output will wake you. As your first "
            "action after waking up, start the listener again.\n"
        ),
    },
    ("plugin", False): {
        "ru": (
            f"AGENTSCHAT: сессия {AGENT} подключена к комнате {ROOM}.\n"
            "Связь держит плагин Quoroom внутри самого OpenCode: он уже "
            "опрашивает брокера и вложит входящее сообщение прямо в эту сессию.\n"
            "Listener запускать НЕ надо — его роль исполняет плагин.\n"
        ),
        "en": (
            f"AGENTSCHAT: session {AGENT} is connected to room {ROOM}.\n"
            "The connection is held by the Quoroom plugin inside OpenCode itself: "
            "it is already polling the broker and will put an incoming message "
            "straight into this session.\n"
            "Do NOT start a listener - the plugin takes its role.\n"
        ),
    },
    ("push", False): {
        "ru": (
            f"AGENTSCHAT: сессия {AGENT} подключена к комнате {ROOM}.\n"
            "Доставку берёт на себя брокер: входящие сообщения будут приходить "
            "тебе как обычные запросы, помеченные конвертом AGENTSCHAT.\n"
            "Listener запускать НЕ надо — он тебе не нужен и работать не будет.\n"
        ),
        "en": (
            f"AGENTSCHAT: session {AGENT} is connected to room {ROOM}.\n"
            "The broker takes care of delivery: incoming messages will reach you "
            "as ordinary requests marked with an AGENTSCHAT envelope.\n"
            "Do NOT start a listener - you do not need one and it will not work.\n"
        ),
    },
}
RECONNECT_OPENING = {
    "ru": (
        "AGENTSCHAT: это твоя прежняя регистрация, токен сверился — "
        f"сессия {AGENT} подключена к комнате {ROOM}.\n"
        "Новой регистрации не заводилось, слот остался за тобой.\n"
    ),
    "en": (
        "AGENTSCHAT: this is your earlier registration, the token matched - "
        f"session {AGENT} is connected to room {ROOM}.\n"
        "No new registration was created, the slot stayed with you.\n"
    ),
}
RECONNECT_LISTENER = {
    "ru": (
        "Listener прежнего запуска умер вместе с процессом — подними его заново "
        f"ФОНОВОЙ командой: agentschat wait --agent {AGENT}\n"
    ),
    "en": (
        "The listener of the previous run died with its process - start it again "
        f"with a BACKGROUND command: agentschat wait --agent {AGENT}\n"
    ),
}
for _mode in ("listener", "plugin", "push"):
    LOGIN_SENTENCES[(_mode, True)] = {
        language: RECONNECT_OPENING[language]
        + (RECONNECT_LISTENER[language] if _mode == "listener" else "")
        for language in LANGUAGES
    }


def login_result(mode: str, reconnected: bool) -> dict:
    return {
        "command": "login",
        "ok": True,
        "agent": AGENT,
        "mode": mode,
        "reconnected": reconnected,
    }


class LoginSentencesTests(SessionCommandCase):
    def test_every_variant_prints_its_sentences_then_the_result_in_both_languages(
        self,
    ):
        for (mode, reconnected), by_language in LOGIN_SENTENCES.items():
            for language in LANGUAGES:
                with self.subTest(
                    mode=mode, reconnected=reconnected, language=language
                ):
                    self.fresh()
                    outcome = self.login(login_answer(language, mode, reconnected))
                    self.assertEqual(outcome.code, 0)
                    self.assertEqual(
                        without_result(outcome.stdout), by_language[language]
                    )
                    self.assertTrue(outcome.stdout.endswith("\n"))
                    self.assertEqual(outcome.result, login_result(mode, reconnected))

    def fresh(self):
        client.ROOM_LANGUAGE = client_language.RoomLanguage()
        language_file = self.store / "language"
        if language_file.exists():
            language_file.unlink()

    def test_the_russian_words_the_opencode_plugin_still_looks_for_are_kept(self):
        for (mode, reconnected), by_language in LOGIN_SENTENCES.items():
            with self.subTest(mode=mode, reconnected=reconnected):
                self.assertIn("подключена к комнате", by_language["ru"])

    def test_the_russian_word_the_plugin_looks_for_after_a_logout_is_kept(self):
        self.store_credentials()
        self.remember("ru")
        outcome = self.logout(Answer({"ok": True}))
        self.assertIn("отключена", without_result(outcome.stdout))

    def test_the_result_line_is_the_last_line(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.fresh()
                outcome = self.login(login_answer(language))
                last = outcome.stdout.splitlines()[-1]
                self.assertTrue(last.startswith(PREFIX))

    def test_the_result_line_is_the_same_in_both_languages(self):
        for (mode, reconnected), language in itertools.product(
            LOGIN_SENTENCES, LANGUAGES
        ):
            self.fresh()
            outcome = self.login(login_answer(language, mode, reconnected))
            with self.subTest(mode=mode, reconnected=reconnected, language=language):
                self.assertEqual(
                    result_lines(outcome.stdout),
                    [
                        PREFIX
                        + json.dumps(
                            login_result(mode, reconnected), separators=(",", ":")
                        )
                    ],
                )

    def test_the_exact_result_line_of_a_listener_login(self):
        outcome = self.login(login_answer("en"))
        self.assertEqual(
            result_lines(outcome.stdout),
            [
                'AGENTSCHAT-RESULT {"command":"login","ok":true,'
                f'"agent":"{AGENT}","mode":"listener","reconnected":false}}'
            ],
        )

    def test_the_language_comes_from_the_remembered_file_when_the_answer_has_none(
        self,
    ):
        self.remember("ru")
        answer = login_answer("ru")
        del answer._data["language"]
        outcome = self.login(answer)
        self.assertEqual(
            without_result(outcome.stdout), LOGIN_SENTENCES[("listener", False)]["ru"]
        )

    def test_with_nothing_known_the_sentences_are_english(self):
        answer = login_answer("en")
        del answer._data["language"]
        outcome = self.login(answer)
        self.assertEqual(
            without_result(outcome.stdout), LOGIN_SENTENCES[("listener", False)]["en"]
        )

    def test_english_output_has_no_cyrillic(self):
        for mode, reconnected in LOGIN_SENTENCES:
            self.fresh()
            outcome = self.login(login_answer("en", mode, reconnected))
            with self.subTest(mode=mode, reconnected=reconnected):
                self.assertIsNone(CYRILLIC.search(outcome.everything))

    def test_the_credentials_are_stored_and_never_printed(self):
        for language in LANGUAGES:
            self.fresh()
            outcome = self.login(login_answer(language))
            with self.subTest(language=language):
                self.assertNotIn(SECRET, outcome.everything)
                stored = json.loads((self.store / f"{AGENT}.json").read_text("utf-8"))
                self.assertEqual(stored, {"agent": AGENT, "token": SECRET})

    def test_a_reconnect_sends_the_token_from_the_disk(self):
        self.store_credentials()
        with patch.object(client.requests, "post") as post:
            post.return_value = login_answer("en", "listener", True)
            self.run_command(client.do_login, agent=AGENT, label="", reconnect=True)
        self.assertEqual(
            post.call_args.kwargs["json"],
            {"agent": AGENT, "label": "", "reconnect": True, "token": SECRET},
        )


class LoginRefusalTests(SessionCommandCase):
    def refused(self, code: str, message: str, status: int = 409, language="en"):
        self.remember(language)
        return self.login(refusal(status, code, message))

    def test_the_message_of_the_broker_is_shown_and_its_code_is_in_the_result(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                outcome = self.refused("slot_taken", "the slot is taken", 409, language)
                self.assertEqual(outcome.code, 1)
                self.assertEqual(outcome.stderr, "AGENTSCHAT: the slot is taken\n")
                self.assertEqual(
                    outcome.result,
                    {
                        "command": "login",
                        "ok": False,
                        "agent": AGENT,
                        "code": "slot_taken",
                    },
                )
                self.assertEqual(len(result_lines(outcome.stdout)), 1)

    def test_the_result_does_not_depend_on_the_words_of_the_message(self):
        first = self.refused("unknown_agent", "no such agent")
        second = self.refused("unknown_agent", "completely different words")
        self.assertEqual(first.result, second.result)

    def test_the_result_names_the_code_not_the_status(self):
        first = self.refused("slot_taken", "words", 409)
        second = self.refused("slot_taken", "words", 418)
        self.assertEqual(first.result["code"], second.result["code"])

    def test_an_answer_that_is_not_the_brokers_gets_a_generic_code(self):
        self.remember("en")
        outcome = self.login(Answer(None, status=502, text="Bad Gateway"))
        self.assertEqual(outcome.stderr, "AGENTSCHAT: Bad Gateway\n")
        self.assertEqual(outcome.result["code"], "broker_refused")
        self.assertEqual(outcome.code, 1)

    def test_a_refusal_writes_no_credentials(self):
        self.refused("slot_taken", "taken")
        self.assertFalse((self.store / f"{AGENT}.json").exists())

    def test_an_unreachable_broker_is_reported_in_both_languages(self):
        expected = {
            "en": f"AGENTSCHAT: The broker is unreachable at {BROKER_URL}: down\n",
            "ru": f"AGENTSCHAT: брокер недоступен на {BROKER_URL}: down\n",
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.remember(language)
                outcome = self.login(failure=requests.ConnectionError("down"))
                self.assertEqual(outcome.code, 1)
                self.assertEqual(outcome.stderr, expected[language])
                self.assertEqual(
                    outcome.result,
                    {
                        "command": "login",
                        "ok": False,
                        "agent": AGENT,
                        "code": "broker_unreachable",
                    },
                )
                self.assertEqual(len(result_lines(outcome.stdout)), 1)

    def test_english_refusals_and_unreachable_broker_have_no_cyrillic(self):
        outcome = self.login(failure=requests.ConnectionError("down"))
        self.assertIsNone(CYRILLIC.search(outcome.everything))


class LogoutTests(SessionCommandCase):
    def test_a_logout_prints_the_sentence_then_the_result_in_both_languages(self):
        expected = {
            "ru": f"AGENTSCHAT: сессия {AGENT} отключена.\n",
            "en": f"AGENTSCHAT: session {AGENT} is disconnected.\n",
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.store_credentials()
                self.remember(language)
                outcome = self.logout(Answer({"ok": True}))
                self.assertEqual(outcome.code, 0)
                self.assertEqual(without_result(outcome.stdout), expected[language])
                self.assertEqual(
                    outcome.result, {"command": "logout", "ok": True, "agent": AGENT}
                )
                self.assertTrue(outcome.stdout.endswith("\n"))
                self.assertEqual(len(result_lines(outcome.stdout)), 1)
                self.assertFalse((self.store / f"{AGENT}.json").exists())

    def test_the_exact_result_line(self):
        self.store_credentials()
        outcome = self.logout(Answer({"ok": True}))
        self.assertEqual(
            result_lines(outcome.stdout),
            [f'AGENTSCHAT-RESULT {{"command":"logout","ok":true,"agent":"{AGENT}"}}'],
        )

    def test_the_token_goes_to_the_broker_and_not_to_the_screen(self):
        self.store_credentials()
        with patch.object(client.requests, "post") as post:
            post.return_value = Answer({"ok": True})
            outcome = self.run_command(client.do_logout, agent=AGENT, force=False)
        self.assertEqual(post.call_args.kwargs["json"]["token"], SECRET)
        self.assertNotIn(SECRET, outcome.everything)

    def test_a_forced_logout_keeps_the_file_and_sends_no_token(self):
        path = self.store_credentials()
        with patch.object(client.requests, "post") as post:
            post.return_value = Answer({"ok": True})
            outcome = self.run_command(client.do_logout, agent=AGENT, force=True)
        self.assertEqual(post.call_args.kwargs["json"], {"agent": AGENT, "force": True})
        self.assertTrue(path.exists())
        self.assertEqual(outcome.result["ok"], True)

    def test_the_broker_refusal_shows_its_message_and_gives_its_code(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                path = self.store_credentials()
                self.remember(language)
                outcome = self.logout(refusal(409, "session_not_registered", "words"))
                self.assertEqual(outcome.code, 1)
                self.assertEqual(outcome.stderr, "AGENTSCHAT: words\n")
                self.assertEqual(
                    outcome.result,
                    {
                        "command": "logout",
                        "ok": False,
                        "agent": AGENT,
                        "code": "session_not_registered",
                    },
                )
                self.assertTrue(path.exists())

    def test_an_unreachable_broker_is_reported_in_both_languages(self):
        expected = {
            "en": "AGENTSCHAT: The broker is unreachable: down\n",
            "ru": "AGENTSCHAT: брокер недоступен: down\n",
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.store_credentials()
                self.remember(language)
                outcome = self.logout(failure=requests.ConnectionError("down"))
                self.assertEqual(outcome.code, 1)
                self.assertEqual(outcome.stderr, expected[language])
                self.assertEqual(
                    outcome.result,
                    {
                        "command": "logout",
                        "ok": False,
                        "agent": AGENT,
                        "code": "broker_unreachable",
                    },
                )

    def test_a_session_that_never_logged_in_is_told_how_to_do_it(self):
        expected = {
            "en": (
                f"AGENTSCHAT: Session {AGENT} is not connected to the chat. "
                f"Run this first: agentschat login --agent {AGENT}\n"
            ),
            "ru": (
                f"AGENTSCHAT: сессия {AGENT} не подключена к чату. "
                f"Сначала выполните: agentschat login --agent {AGENT}\n"
            ),
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.remember(language)
                with patch.object(client.requests, "post") as post:
                    outcome = self.run_command(
                        client.do_logout, agent=AGENT, force=False
                    )
                post.assert_not_called()
                self.assertEqual(outcome.code, 1)
                self.assertEqual(outcome.stderr, expected[language])
                self.assertEqual(
                    outcome.result,
                    {
                        "command": "logout",
                        "ok": False,
                        "agent": AGENT,
                        "code": "not_logged_in",
                    },
                )
                self.assertEqual(len(result_lines(outcome.stdout)), 1)

    def test_english_output_has_no_cyrillic(self):
        self.store_credentials()
        for outcome in (
            self.logout(Answer({"ok": True})),
            self.logout(failure=requests.ConnectionError("down")),
            self.logout(force=True, failure=requests.ConnectionError("down")),
        ):
            self.assertIsNone(CYRILLIC.search(outcome.everything))
        (self.store / f"{AGENT}.json").unlink(missing_ok=True)
        self.assertIsNone(
            CYRILLIC.search(
                self.run_command(client.do_logout, agent=AGENT, force=False).everything
            )
        )


def status_answer(language: str = "ru") -> dict:
    return {
        "language": language,
        "sessions": [
            {
                "agent": "claude-code",
                "state": "listening",
                "label": "refactoring",
                "registered": "10:00:00",
                "quiet": 12,
                "line": "claude-code  СЛУШАЕТ  (refactoring)",
            },
            {
                "agent": "opencode",
                "state": "not_connected",
                "line": "opencode     не подключён",
            },
        ],
    }


class StatusTests(SessionCommandCase):
    def test_the_lines_of_the_broker_are_printed_as_they_are_and_the_result_follows(
        self,
    ):
        outcome = self.status(Answer(status_answer()))
        self.assertEqual(outcome.code, 0)
        self.assertEqual(
            without_result(outcome.stdout),
            "claude-code  СЛУШАЕТ  (refactoring)\nopencode     не подключён\n",
        )
        self.assertTrue(outcome.stdout.splitlines()[-1].startswith(PREFIX))

    def test_the_result_lists_the_sessions_by_code_without_the_sentences(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                outcome = self.status(Answer(status_answer(language)))
                self.assertEqual(
                    outcome.result,
                    {
                        "command": "status",
                        "ok": True,
                        "language": language,
                        "sessions": [
                            {
                                "agent": "claude-code",
                                "state": "listening",
                                "label": "refactoring",
                                "registered": "10:00:00",
                                "quiet": 12,
                            },
                            {"agent": "opencode", "state": "not_connected"},
                        ],
                    },
                )
                self.assertEqual(len(result_lines(outcome.stdout)), 1)

    def test_the_result_line_is_pure_ascii_whatever_the_label(self):
        answer = status_answer()
        answer["sessions"][0]["label"] = "рефакторинг"
        outcome = self.status(Answer(answer))
        line = result_lines(outcome.stdout)[0]
        line.encode("ascii")
        self.assertEqual(outcome.result["sessions"][0]["label"], "рефакторинг")

    def test_a_plain_text_answer_is_printed_and_reported_as_unexpected(self):
        answer = Answer(
            text="claude-code  не подключён\n", content_type="text/plain; charset=utf-8"
        )
        outcome = self.status(answer)
        self.assertEqual(outcome.code, 0)
        self.assertEqual(without_result(outcome.stdout), "claude-code  не подключён\n")
        self.assertEqual(
            outcome.result,
            {"command": "status", "ok": False, "code": "unexpected_answer"},
        )

    def test_a_refusal_shaped_answer_shows_its_message_and_gives_its_code(self):
        outcome = self.status(refusal(500, "broken", "the broker is unwell"))
        self.assertEqual(without_result(outcome.stdout), "the broker is unwell\n")
        self.assertEqual(
            outcome.result, {"command": "status", "ok": False, "code": "broken"}
        )

    def test_an_unreachable_broker_is_reported_in_both_languages(self):
        expected = {
            "en": f"AGENTSCHAT: The broker is unreachable at {BROKER_URL}: down\n",
            "ru": f"AGENTSCHAT: брокер недоступен на {BROKER_URL}: down\n",
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.remember(language)
                outcome = self.status(failure=requests.ConnectionError("down"))
                self.assertEqual(outcome.code, 1)
                self.assertEqual(outcome.stderr, expected[language])
                self.assertEqual(
                    outcome.result,
                    {"command": "status", "ok": False, "code": "broker_unreachable"},
                )
                self.assertEqual(len(result_lines(outcome.stdout)), 1)

    def test_english_failure_has_no_cyrillic(self):
        outcome = self.status(failure=requests.ConnectionError("down"))
        self.assertIsNone(CYRILLIC.search(outcome.everything))


class ReaderOfTheResultTests(SessionCommandCase):
    def catalogue_of_other_words(self) -> Catalogue:
        real = client.CATALOGUE
        replaced = {
            language: {
                key: f"WORDS {key}"
                if not key.startswith(("failure", "envelope"))
                else value
                for key, value in real.templates(language).items()
            }
            for language in LANGUAGES
        }
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for language, templates in replaced.items():
            (Path(folder.name) / f"{language}.json").write_text(
                json.dumps(templates), encoding="utf-8"
            )
        return Catalogue.from_path(Path(folder.name))

    def scenarios(self):
        yield "login", lambda: self.login(login_answer("en"))
        yield "login", lambda: self.login(login_answer("en", "plugin"))
        yield "login", lambda: self.login(login_answer("en", "listener", True))
        yield "login", lambda: self.login(refusal(409, "slot_taken", "taken"))
        yield "login", lambda: self.login(failure=requests.ConnectionError("down"))
        yield "logout", lambda: self.logout(Answer({"ok": True}))
        yield "logout", lambda: self.logout(refusal(409, "unknown_agent", "no"))
        yield "logout", lambda: self.logout(failure=requests.ConnectionError("down"))
        yield "status", lambda: self.status(Answer(status_answer("en")))
        yield "status", lambda: self.status(failure=requests.ConnectionError("down"))

    def test_the_reader_gets_the_same_result_when_every_sentence_is_other_words(self):
        for index, (command, scenario) in enumerate(self.scenarios()):
            self.store_credentials()
            known = scenario()
            self.store_credentials()
            with patch.object(client, "CATALOGUE", self.catalogue_of_other_words()):
                changed = scenario()
            with self.subTest(index=index, command=command):
                self.assertEqual(known.result, changed.result)
                self.assertEqual(known.code, changed.code)
                self.assertEqual(known.result["command"], command)

    def test_the_substituted_catalogue_really_changes_what_the_client_says(self):
        known = self.login(login_answer("en"))
        with patch.object(client, "CATALOGUE", self.catalogue_of_other_words()):
            changed = self.login(login_answer("en"))
        self.assertNotEqual(known.stdout, changed.stdout)
        self.assertIn("WORDS login_connected", changed.stdout)

    def test_exactly_one_result_line_per_command_in_every_scenario(self):
        for index, (_, scenario) in enumerate(self.scenarios()):
            self.store_credentials()
            outcome = scenario()
            with self.subTest(index=index):
                self.assertEqual(len(result_lines(outcome.everything)), 1)
                self.assertEqual(len(result_lines(outcome.stdout)), 1)

    def test_no_result_line_carries_a_token(self):
        for index, (_, scenario) in enumerate(self.scenarios()):
            self.store_credentials()
            outcome = scenario()
            with self.subTest(index=index):
                self.assertNotIn(SECRET, outcome.everything)
                self.assertNotIn("token", result_lines(outcome.stdout)[0])

    def test_the_result_is_a_fixed_ascii_prefix_and_one_json_object(self):
        for index, (_, scenario) in enumerate(self.scenarios()):
            self.store_credentials()
            line = result_lines(scenario().stdout)[0]
            with self.subTest(index=index):
                self.assertRegex(line, r"^AGENTSCHAT-RESULT \{.*\}$")
                self.assertIsInstance(json.loads(line[len(PREFIX) :]), dict)
                self.assertNotIn("\n", line)

    def test_the_command_name_leads_and_ok_is_a_boolean(self):
        for index, (command, scenario) in enumerate(self.scenarios()):
            self.store_credentials()
            result = scenario().result
            with self.subTest(index=index):
                self.assertEqual(list(result)[:2], ["command", "ok"])
                self.assertEqual(result["command"], command)
                self.assertIsInstance(result["ok"], bool)

    def test_a_failure_carries_a_snake_case_code_and_a_success_carries_none(self):
        for index, (_, scenario) in enumerate(self.scenarios()):
            self.store_credentials()
            result = scenario().result
            with self.subTest(index=index):
                if result["ok"]:
                    self.assertNotIn("code", result)
                else:
                    self.assertRegex(result["code"], r"^[a-z][a-z0-9_]*$")


class ExitCodesTests(SessionCommandCase):
    def test_exit_codes_are_as_they_were(self):
        self.store_credentials()
        cases = [
            (self.login(login_answer("en")).code, 0),
            (self.login(refusal(409, "slot_taken", "x")).code, 1),
            (self.login(failure=requests.ConnectionError("d")).code, 1),
            (self.logout(Answer({"ok": True})).code, 0),
            (self.logout(refusal(409, "x", "x")).code, 1),
            (self.logout(failure=requests.ConnectionError("d")).code, 1),
            (self.status(Answer(status_answer())).code, 0),
            (self.status(failure=requests.ConnectionError("d")).code, 1),
            (self.status(Answer(text="x", content_type="text/plain")).code, 0),
        ]
        for index, (actual, expected) in enumerate(cases):
            with self.subTest(index=index):
                self.assertEqual(actual, expected)


class HelpTests(SessionCommandCase):
    def help_of(self, *arguments: str) -> str:
        stdout = io.StringIO()
        with (
            patch.object(sys, "argv", ["agentschat", *arguments, "-h"]),
            redirect_stdout(stdout),
            self.assertRaises(SystemExit) as stopped,
        ):
            client.main()
        self.assertEqual(stopped.exception.code, 0)
        return " ".join(stdout.getvalue().split())

    EXPECTED = {
        "ru": {
            (): [
                "подключить эту сессию к чату",
                "кто подключён и кто слушает",
                "отключить сессию",
            ],
            ("login",): [
                "чем занята сессия",
                "вернуться к своей же регистрации после перезапуска CLI; "
                "получится, только если совпадёт токен с диска",
            ],
            ("logout",): ["освободить чужой слот"],
        },
        "en": {
            (): [
                "connect this session to the chat",
                "who is connected and who is listening",
                "disconnect this session",
            ],
            ("login",): [
                "what the session is busy with",
                "return to your own registration after a CLI restart; it works "
                "only if the token on disk matches",
            ],
            ("logout",): ["free a slot that is held by someone else"],
        },
    }

    def test_the_help_of_the_three_commands_follows_the_room_language(self):
        for language, by_command in self.EXPECTED.items():
            for command, phrases in by_command.items():
                for phrase in phrases:
                    with self.subTest(
                        language=language, command=command, phrase=phrase
                    ):
                        self.remember(language)
                        client.ROOM_LANGUAGE = client_language.RoomLanguage()
                        self.assertIn(phrase, self.help_of(*command))

    def test_english_help_of_the_three_commands_has_no_cyrillic_in_their_lines(self):
        self.remember("en")
        for command in (("login",), ("logout",), ("status",)):
            with self.subTest(command=command):
                self.assertIsNone(CYRILLIC.search(self.help_of(*command)))


class NoProseLeftInTheCodeTests(unittest.TestCase):
    SESSION_FUNCTIONS = {"do_login", "do_logout", "do_status", "credentials"}
    SESSION_PARSERS = {"login", "logout", "status"}
    client_source = Path(client.__file__).read_text(encoding="utf-8")
    tree = ast.parse(client_source)

    def constants_in(self, node: ast.AST) -> list[str]:
        return [
            part.value
            for part in ast.walk(node)
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        ]

    def test_the_session_functions_hold_no_cyrillic_literal(self):
        found = {}
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name in self.SESSION_FUNCTIONS
            ):
                found[node.name] = [
                    text for text in self.constants_in(node) if CYRILLIC.search(text)
                ]
        self.assertEqual(set(found), self.SESSION_FUNCTIONS)
        self.assertEqual({name: texts for name, texts in found.items() if texts}, {})

    def test_the_parser_entries_of_the_three_commands_hold_no_cyrillic_literal(self):
        offenders = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call) or not isinstance(
                node.func, ast.Attribute
            ):
                continue
            owner = node.func.value
            names_a_session_parser = (
                node.func.attr == "add_parser"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in self.SESSION_PARSERS
            ) or (
                node.func.attr == "add_argument"
                and isinstance(owner, ast.Name)
                and owner.id in self.SESSION_PARSERS
            )
            if names_a_session_parser:
                offenders += [
                    text for text in self.constants_in(node) if CYRILLIC.search(text)
                ]
        self.assertEqual(offenders, [])

    def test_every_key_of_the_client_catalogue_is_used_by_the_client(self):
        unused = [
            key
            for key in client.CATALOGUE.templates("en")
            if not re.search(rf'"{re.escape(key)}"', self.client_source)
        ]
        self.assertEqual(unused, [])
