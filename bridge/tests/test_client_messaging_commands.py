"""Task english-release-09: wait, inbox, say, ask and the help of the subcommands."""

import ast
import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import requests

from sessionchat import client, client_language
from sessionchat.i18n import Catalogue
from tests.catalogue_contract import CYRILLIC
from tests.result_line import MARK, result_lines, without_result
from tests.test_client_language import Answer
from tests.test_client_refusals import refusal
from tests.test_listener import Clock
from tests.test_client_session_commands import (
    AGENT,
    BROKER_URL,
    SECRET,
    Outcome,
    SessionCommandCase,
)

LANGUAGES = ("en", "ru")
EVENT = "$event1"
ENVELOPE = "ENVELOPE TEXT\nsecond line"
FRAME = re.compile(r"^=== AGENTSCHAT: .+ ===$")
NO_ANSWER = Answer(status=204)


class TickingClock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        self.now += 1.0
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def sent(language: str, **extra) -> Answer:
    return Answer({"event_id": EVENT, "depth": 1, "language": language, **extra})


def full_envelope(language: str) -> Answer:
    return Answer({"rendered": ENVELOPE, "language": language})


class MessagingCase(SessionCommandCase):
    def start_language(self, language: str) -> None:
        self.remember(language)
        client.ROOM_LANGUAGE = client_language.RoomLanguage()

    def wait(self, side_effect, deaf: float = 9.0) -> Outcome:
        self.store_credentials()
        with (
            patch.object(client, "poll_once", side_effect=side_effect),
            patch.object(client, "time", Clock()),
            patch.object(client, "DEAF_SECONDS", deaf),
        ):
            return self.run_command(client.do_wait, agent=AGENT)

    def inbox(self, got=None, failure=None) -> Outcome:
        self.store_credentials()
        with patch.object(
            client.requests, "get", return_value=got, side_effect=failure
        ):
            return self.run_command(client.do_inbox, agent=AGENT)

    def say(self, posted=None, failure=None, text="hello", file=None) -> Outcome:
        with patch.object(
            client.requests, "post", return_value=posted, side_effect=failure
        ) as post:
            self.post = post
            return self.run_command(client.do_say, agent=AGENT, text=text, file=file)

    def ask(
        self, posted=None, polled=None, post_failure=None, timeout=3.0, text="hello"
    ) -> Outcome:
        clock = TickingClock()
        with (
            patch.object(
                client.requests, "post", return_value=posted, side_effect=post_failure
            ) as post,
            patch.object(client.requests, "get", side_effect=polled) as get,
            patch.object(client, "time", clock),
        ):
            self.post, self.get = post, get
            return self.run_command(
                client.do_ask, agent=AGENT, text=text, file=None, timeout=timeout
            )


class WaitEndingsTests(MessagingCase):
    LOST = {
        "ru": (
            "=== AGENTSCHAT: связь с брокером потеряна ===\n"
            f"Брокер {BROKER_URL} недоступен уже 9с: boom\n"
            "Listener завершился, чтобы не изображать работу вслепую.\n"
            "Проверь, запущен ли брокер, и подними listener заново.\n"
        ),
        "en": (
            "=== AGENTSCHAT: broker connection lost ===\n"
            f"The broker {BROKER_URL} has been unreachable for 9s: boom\n"
            "The listener exited instead of pretending to work blind.\n"
            "Check whether the broker is running and start the listener again.\n"
        ),
    }
    STOPPED = {
        "ru": "=== AGENTSCHAT: listener остановлен ===\nthe broker said no\n",
        "en": "=== AGENTSCHAT: listener stopped ===\nthe broker said no\n",
    }

    def lost(self) -> Outcome:
        return self.wait([requests.ConnectionError("boom")] * 50)

    def test_losing_the_broker_prints_the_frame_in_the_room_language(self):
        for language in LANGUAGES:
            self.start_language(language)
            with self.subTest(language=language):
                outcome = self.lost()
                self.assertEqual(outcome.stdout, self.LOST[language])
                self.assertEqual(outcome.stderr, "")
                self.assertEqual(outcome.code, 1)

    def test_a_stopped_listener_prints_the_frame_and_the_reason_as_it_came(self):
        for language in LANGUAGES:
            self.start_language(language)
            with self.subTest(language=language):
                outcome = self.wait([RuntimeError("the broker said no")])
                self.assertEqual(outcome.stdout, self.STOPPED[language])
                self.assertEqual(outcome.code, 1)

    def test_a_message_is_printed_as_the_broker_rendered_it_and_the_listener_ends(
        self,
    ):
        for language in LANGUAGES:
            self.start_language(language)
            with self.subTest(language=language):
                outcome = self.wait([None, ENVELOPE])
                self.assertEqual(outcome.stdout, ENVELOPE + "\n")
                self.assertEqual(outcome.code, 0)

    def test_a_reply_without_the_envelope_text_stops_the_listener_in_the_room_language(
        self,
    ):
        expected = {
            "en": "=== AGENTSCHAT: listener stopped ===\nThe broker answered without "
            "the envelope text (code: envelope_without_text).\n",
            "ru": "=== AGENTSCHAT: listener остановлен ===\nБрокер ответил без текста "
            "конверта (код: envelope_without_text).\n",
        }
        for language in LANGUAGES:
            self.start_language(language)
            self.store_credentials()
            with (
                self.subTest(language=language),
                patch.object(
                    client.requests, "get", return_value=Answer({"language": language})
                ),
            ):
                outcome = self.run_command(client.do_wait, agent=AGENT)
                self.assertEqual(outcome.stdout, expected[language])
                self.assertEqual(outcome.code, 1)

    def test_every_frame_opens_with_the_ascii_marker_in_both_languages(self):
        for language in LANGUAGES:
            self.start_language(language)
            for name, outcome in (
                ("lost", self.lost()),
                ("stopped", self.wait([RuntimeError("no")])),
            ):
                first = outcome.stdout.splitlines()[0]
                with self.subTest(language=language, frame=name):
                    self.assertRegex(first, FRAME)
                    self.assertTrue(first.startswith("=== AGENTSCHAT: "))
        self.start_language("en")
        for outcome in (self.lost(), self.wait([RuntimeError("no")])):
            self.assertTrue(outcome.stdout.splitlines()[0].isascii())

    def test_the_frame_keeps_its_shape_when_the_catalogue_uses_other_words(self):
        for language in LANGUAGES:
            self.start_language(language)
            with patch.object(client, "CATALOGUE", other_words_catalogue(self)):
                for outcome in (self.lost(), self.wait([RuntimeError("no")])):
                    with self.subTest(language=language):
                        self.assertRegex(outcome.stdout.splitlines()[0], FRAME)
                        self.assertEqual(outcome.code, 1)

    def test_the_english_frames_contain_no_cyrillic(self):
        self.start_language("en")
        for outcome in (self.lost(), self.wait([RuntimeError("no")])):
            self.assertIsNone(CYRILLIC.search(outcome.stdout))

    def test_a_short_outage_does_not_print_a_frame(self):
        outage = requests.ConnectionError("blink")
        outcome = self.wait([outage, None, ENVELOPE])
        self.assertEqual(outcome.stdout, ENVELOPE + "\n")

    def test_waiting_without_a_registration_is_refused_in_the_room_language(self):
        expected = {
            "en": f"AGENTSCHAT: Session {AGENT} is not connected to the chat. "
            f"Run this first: agentschat login --agent {AGENT}\n",
            "ru": f"AGENTSCHAT: сессия {AGENT} не подключена к чату. "
            f"Сначала выполните: agentschat login --agent {AGENT}\n",
        }
        for language in LANGUAGES:
            self.start_language(language)
            with self.subTest(language=language):
                outcome = self.run_command(client.do_wait, agent=AGENT)
                self.assertEqual(outcome.stderr, expected[language])
                self.assertEqual(outcome.code, 1)


class InboxTests(MessagingCase):
    PENDING = ["first envelope", "second envelope\nwith two lines"]
    HEADER = {
        "ru": "AGENTSCHAT: пока тебя не было, пришло сообщений: 2.",
        "en": "AGENTSCHAT: messages that arrived while you were away: 2.",
    }
    EMPTY = {
        "ru": "AGENTSCHAT: новых сообщений нет.\n",
        "en": "AGENTSCHAT: no new messages.\n",
    }
    UNREACHABLE = {
        "ru": "AGENTSCHAT: брокер недоступен: down\n",
        "en": "AGENTSCHAT: The broker is unreachable: down\n",
    }

    def test_pending_messages_are_listed_under_a_header_in_the_room_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                outcome = self.inbox(
                    Answer({"pending": self.PENDING, "language": language})
                )
                expected = (
                    f"\n{self.HEADER[language]}\n"
                    "\nfirst envelope\n"
                    "\nsecond envelope\nwith two lines\n"
                )
                self.assertEqual(outcome.stdout, expected)
                self.assertEqual(outcome.code, 0)

    def test_an_empty_inbox_says_so_in_the_room_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                outcome = self.inbox(Answer({"pending": [], "language": language}))
                self.assertEqual(outcome.stdout, self.EMPTY[language])
                self.assertEqual(outcome.code, 0)

    def test_an_answer_without_a_pending_list_counts_as_empty(self):
        outcome = self.inbox(Answer({"language": "en"}))
        self.assertEqual(outcome.stdout, self.EMPTY["en"])

    def test_an_unreachable_broker_is_reported_in_the_remembered_language(self):
        for language in LANGUAGES:
            self.start_language(language)
            with self.subTest(language=language):
                outcome = self.inbox(failure=requests.ConnectionError("down"))
                self.assertEqual(outcome.stderr, self.UNREACHABLE[language])
                self.assertEqual(outcome.code, 1)

    def test_a_refusal_is_shown_as_the_broker_rendered_it(self):
        outcome = self.inbox(refusal(409, "session_not_registered", "not connected"))
        self.assertEqual(outcome.stderr, "AGENTSCHAT: not connected\n")
        self.assertEqual(outcome.code, 1)

    def test_the_english_inbox_has_no_cyrillic(self):
        for got in (
            Answer({"pending": self.PENDING, "language": "en"}),
            Answer({"pending": [], "language": "en"}),
        ):
            self.assertIsNone(CYRILLIC.search(self.inbox(got).everything))

    def test_the_inbox_without_a_registration_is_refused(self):
        outcome = self.run_command(client.do_inbox, agent=AGENT)
        self.assertEqual(outcome.code, 1)
        self.assertIn(AGENT, outcome.stderr)


def say_result(**fields) -> dict:
    return {"command": "say", "ok": True, "agent": AGENT, **fields}


class SayTests(MessagingCase):
    SENT = {
        "ru": f"AGENTSCHAT: отправлено ({EVENT}).\n",
        "en": f"AGENTSCHAT: sent ({EVENT}).\n",
    }
    WARNING = {
        "ru": "AGENTSCHAT: ВНИМАНИЕ — {text}\n",
        "en": "AGENTSCHAT: WARNING - {text}\n",
    }

    def result_line(self, outcome: Outcome) -> str:
        return result_lines(outcome.stdout)[-1]

    def test_a_sent_message_is_confirmed_in_the_room_language(self):
        for language in LANGUAGES:
            self.store_credentials()
            with self.subTest(language=language):
                outcome = self.say(sent(language))
                self.assertEqual(without_result(outcome.stdout), self.SENT[language])
                self.assertEqual(outcome.stderr, "")
                self.assertEqual(outcome.code, 0)

    def test_a_sent_message_ends_with_exactly_this_result_line(self):
        self.store_credentials()
        outcome = self.say(sent("en"))
        self.assertEqual(
            outcome.stdout.splitlines()[-1],
            MARK + '{"command":"say","ok":true,"agent":"claude-code",'
            f'"event_id":"{EVENT}"' + "}",
        )
        self.assertEqual(len(result_lines(outcome.stdout)), 1)

    def test_the_warning_of_the_broker_is_printed_as_received(self):
        words = "no one got it {not} a template, @name %s"
        for language in LANGUAGES:
            self.store_credentials()
            answer = sent(language, warning=words, warning_code="unaddressed")
            with self.subTest(language=language):
                outcome = self.say(answer)
                self.assertEqual(
                    without_result(outcome.stdout),
                    self.SENT[language] + self.WARNING[language].format(text=words),
                )
                self.assertEqual(
                    outcome.result, say_result(event_id=EVENT, warning="unaddressed")
                )

    def test_the_note_of_the_broker_is_printed_as_received(self):
        for language in LANGUAGES:
            self.store_credentials()
            answer = sent(
                language, note="the person sees it", note_code="addressed_to_person"
            )
            with self.subTest(language=language):
                outcome = self.say(answer)
                self.assertEqual(
                    without_result(outcome.stdout),
                    self.SENT[language] + "AGENTSCHAT: the person sees it\n",
                )
                self.assertEqual(
                    outcome.result,
                    say_result(event_id=EVENT, note="addressed_to_person"),
                )

    def test_the_russian_texts_are_exactly_what_the_client_printed_before(self):
        self.store_credentials()
        warned = self.say(
            sent("ru", warning="сообщение никому не ушло", warning_code="unaddressed")
        )
        noted = self.say(sent("ru", note="человек видит", note_code="x"))
        self.assertEqual(
            without_result(warned.stdout),
            "AGENTSCHAT: отправлено ($event1).\n"
            "AGENTSCHAT: ВНИМАНИЕ — сообщение никому не ушло\n",
        )
        self.assertEqual(
            without_result(noted.stdout),
            "AGENTSCHAT: отправлено ($event1).\nAGENTSCHAT: человек видит\n",
        )

    def test_a_warning_without_a_code_prints_but_adds_nothing_to_the_result(self):
        self.store_credentials()
        outcome = self.say(sent("en", warning="old broker words"))
        self.assertIn("WARNING - old broker words", outcome.stdout)
        self.assertEqual(outcome.result, say_result(event_id=EVENT))

    def test_the_text_travels_to_the_broker_with_the_token(self):
        self.store_credentials()
        self.say(sent("en"), text="plain words")
        self.assertEqual(
            self.post.call_args.kwargs["json"],
            {"agent": AGENT, "token": SECRET, "text": "plain words"},
        )

    def test_a_refusal_prints_the_broker_message_and_reports_its_code(self):
        self.store_credentials()
        outcome = self.say(refusal(409, "session_not_registered", "not connected"))
        self.assertEqual(outcome.stderr, "AGENTSCHAT: not connected\n")
        self.assertEqual(
            outcome.result,
            {
                "command": "say",
                "ok": False,
                "agent": AGENT,
                "code": "session_not_registered",
            },
        )
        self.assertEqual(outcome.code, 1)

    def test_a_refusal_without_a_code_is_reported_as_broker_refused(self):
        self.store_credentials()
        outcome = self.say(
            Answer(None, status=502, text="Bad gateway", content_type="text/plain")
        )
        self.assertEqual(outcome.result["code"], "broker_refused")
        self.assertEqual(outcome.stderr, "AGENTSCHAT: Bad gateway\n")

    def test_an_unreachable_broker_is_reported_in_the_remembered_language(self):
        expected = {
            "ru": "AGENTSCHAT: брокер недоступен: down\n",
            "en": "AGENTSCHAT: The broker is unreachable: down\n",
        }
        for language in LANGUAGES:
            self.start_language(language)
            self.store_credentials()
            with self.subTest(language=language):
                outcome = self.say(failure=requests.ConnectionError("down"))
                self.assertEqual(outcome.stderr, expected[language])
                self.assertEqual(outcome.result["code"], "broker_unreachable")
                self.assertEqual(outcome.code, 1)

    def test_saying_without_a_registration_is_refused_with_the_code(self):
        outcome = self.say(sent("en"))
        self.assertEqual(outcome.result["code"], "not_logged_in")
        self.assertEqual(outcome.result["command"], "say")
        self.assertIn(AGENT, outcome.stderr)
        self.assertEqual(outcome.code, 1)
        self.post.assert_not_called()

    def test_nothing_to_send_is_refused_in_the_room_language_without_a_request(self):
        expected = {
            "ru": "AGENTSCHAT: нечего отправлять: укажите текст, --file или - для "
            "стандартного ввода\n",
            "en": "AGENTSCHAT: nothing to send: give the text, --file, or - for "
            "standard input\n",
        }
        for language in LANGUAGES:
            self.start_language(language)
            self.store_credentials()
            with self.subTest(language=language):
                outcome = self.say(sent(language), text=None)
                self.assertEqual(outcome.stderr, expected[language])
                self.assertEqual(
                    outcome.result,
                    {
                        "command": "say",
                        "ok": False,
                        "agent": AGENT,
                        "code": "nothing_to_send",
                    },
                )
                self.assertEqual(outcome.code, 1)
                self.post.assert_not_called()

    def test_the_text_comes_from_a_file_when_one_is_given(self):
        self.store_credentials()
        path = self.home / "letter.md"
        path.write_text("first\nsecond\n", encoding="utf-8")
        self.say(sent("en"), text=None, file=str(path))
        self.assertEqual(self.post.call_args.kwargs["json"]["text"], "first\nsecond")

    def test_no_output_carries_the_token_and_english_output_has_no_cyrillic(self):
        self.store_credentials()
        outcomes = [
            self.say(sent("en")),
            self.say(sent("en", warning="w", warning_code="unaddressed")),
            self.say(refusal(409, "session_not_registered", "not connected")),
            self.say(failure=requests.ConnectionError("down")),
            self.say(sent("en"), text=None),
        ]
        for index, outcome in enumerate(outcomes):
            with self.subTest(index=index):
                self.assertNotIn(SECRET, outcome.everything)
                self.assertIsNone(CYRILLIC.search(outcome.everything))
                self.assertEqual(len(result_lines(outcome.stdout)), 1)


def ask_result(**fields) -> dict:
    return {"command": "ask", "ok": True, "agent": AGENT, **fields}


class AskTests(MessagingCase):
    TIMEOUT = {
        "ru": "AGENTSCHAT: за 3.0с ответа не пришло. Сообщение доставлено; не жди "
        "дальше в этом ходе — ответ придёт через listener.\n",
        "en": "AGENTSCHAT: no answer arrived within 3.0s. The message was delivered; "
        "do not wait any longer in this turn - the answer will arrive through the "
        "listener.\n",
    }
    INTERRUPTED = {
        "ru": "AGENTSCHAT: ожидание ответа прервано: down\n",
        "en": "AGENTSCHAT: waiting for the answer was interrupted: down\n",
    }
    SENT = SayTests.SENT

    def test_an_answer_is_printed_after_the_confirmation_with_one_result_line(self):
        for language in LANGUAGES:
            self.store_credentials()
            with self.subTest(language=language):
                outcome = self.ask(sent(language), [NO_ANSWER, full_envelope(language)])
                self.assertEqual(
                    without_result(outcome.stdout),
                    self.SENT[language] + ENVELOPE + "\n",
                )
                self.assertEqual(
                    outcome.result, ask_result(event_id=EVENT, answered=True)
                )
                self.assertEqual(len(result_lines(outcome.stdout)), 1)
                self.assertEqual(outcome.code, 0)

    def test_the_result_line_is_the_last_line(self):
        self.store_credentials()
        outcome = self.ask(sent("en"), [full_envelope("en")])
        self.assertEqual(
            outcome.stdout.splitlines()[-1],
            MARK + '{"command":"ask","ok":true,"agent":"claude-code",'
            f'"event_id":"{EVENT}","answered":true' + "}",
        )

    def test_the_warning_is_printed_and_its_code_reaches_the_result(self):
        self.store_credentials()
        answer = sent("en", warning="nobody got it", warning_code="unaddressed")
        outcome = self.ask(answer, [full_envelope("en")])
        self.assertIn("AGENTSCHAT: WARNING - nobody got it\n", outcome.stdout)
        self.assertEqual(
            outcome.result,
            ask_result(event_id=EVENT, warning="unaddressed", answered=True),
        )

    def test_a_missing_answer_is_a_delivered_message_not_a_failure(self):
        for language in LANGUAGES:
            self.store_credentials()
            with self.subTest(language=language):
                outcome = self.ask(sent(language), [NO_ANSWER] * 20)
                self.assertEqual(
                    without_result(outcome.stdout),
                    self.SENT[language] + self.TIMEOUT[language],
                )
                self.assertEqual(
                    outcome.result, ask_result(event_id=EVENT, answered=False)
                )
                self.assertEqual(outcome.code, 0)

    def test_losing_the_broker_while_waiting_reports_the_delivered_event(self):
        for language in LANGUAGES:
            self.start_language(language)
            self.store_credentials()
            with self.subTest(language=language):
                outcome = self.ask(sent(language), [requests.ConnectionError("down")])
                self.assertEqual(outcome.stderr, self.INTERRUPTED[language])
                self.assertEqual(
                    outcome.result,
                    {
                        "command": "ask",
                        "ok": False,
                        "agent": AGENT,
                        "event_id": EVENT,
                        "code": "broker_unreachable",
                    },
                )
                self.assertEqual(outcome.code, 1)

    def test_a_refusal_while_waiting_reports_the_code_of_the_broker(self):
        self.store_credentials()
        outcome = self.ask(
            sent("en"), [refusal(409, "session_not_registered", "not connected")]
        )
        self.assertEqual(
            outcome.stderr,
            "AGENTSCHAT: waiting for the answer was interrupted: not connected\n",
        )
        self.assertEqual(outcome.result["code"], "session_not_registered")
        self.assertEqual(outcome.result["event_id"], EVENT)
        self.assertEqual(outcome.code, 1)

    def test_an_answer_without_the_envelope_text_reports_its_contract_code(self):
        expected = {
            "en": "AGENTSCHAT: waiting for the answer was interrupted: The broker "
            "answered without the envelope text (code: envelope_without_text).\n",
            "ru": "AGENTSCHAT: ожидание ответа прервано: Брокер ответил без текста "
            "конверта (код: envelope_without_text).\n",
        }
        for language in LANGUAGES:
            self.store_credentials()
            with self.subTest(language=language):
                outcome = self.ask(sent(language), [Answer({"language": language})])
                self.assertEqual(outcome.stderr, expected[language])
                self.assertEqual(outcome.result["code"], "envelope_without_text")

    def test_a_refusal_of_the_message_ends_the_ask_before_any_waiting(self):
        self.store_credentials()
        outcome = self.ask(refusal(409, "session_not_registered", "not connected"))
        self.assertEqual(
            outcome.result,
            {
                "command": "ask",
                "ok": False,
                "agent": AGENT,
                "code": "session_not_registered",
            },
        )
        self.assertEqual(len(result_lines(outcome.stdout)), 1)
        self.get.assert_not_called()

    def test_an_unreachable_broker_on_the_first_request_names_the_ask(self):
        self.store_credentials()
        outcome = self.ask(post_failure=requests.ConnectionError("down"))
        self.assertEqual(outcome.result["command"], "ask")
        self.assertEqual(outcome.result["code"], "broker_unreachable")
        self.get.assert_not_called()

    def test_asking_without_a_registration_or_a_text_names_the_ask(self):
        outcome = self.ask(sent("en"))
        self.assertEqual(outcome.result["command"], "ask")
        self.assertEqual(outcome.result["code"], "not_logged_in")
        self.store_credentials()
        outcome = self.ask(sent("en"), text=None)
        self.assertEqual(outcome.result["command"], "ask")
        self.assertEqual(outcome.result["code"], "nothing_to_send")
        self.get.assert_not_called()

    def test_no_output_carries_the_token_and_english_output_has_no_cyrillic(self):
        self.store_credentials()
        outcomes = [
            self.ask(sent("en"), [full_envelope("en")]),
            self.ask(sent("en"), [NO_ANSWER] * 20),
            self.ask(sent("en"), [requests.ConnectionError("down")]),
            self.ask(refusal(409, "session_not_registered", "not connected")),
        ]
        for index, outcome in enumerate(outcomes):
            with self.subTest(index=index):
                self.assertNotIn(SECRET, outcome.everything)
                self.assertIsNone(CYRILLIC.search(outcome.everything))
                self.assertEqual(len(result_lines(outcome.stdout)), 1)


def other_words_catalogue(case: unittest.TestCase) -> Catalogue:
    real = client.CATALOGUE
    folder = tempfile.TemporaryDirectory()
    case.addCleanup(folder.cleanup)
    for language in LANGUAGES:
        words = {
            key: value if key.startswith(("failure", "envelope")) else f"WORDS {key}"
            for key, value in real.templates(language).items()
        }
        (Path(folder.name) / f"{language}.json").write_text(
            json.dumps(words), encoding="utf-8"
        )
    return Catalogue.from_path(Path(folder.name))


class ReaderOfTheResultTests(MessagingCase):
    def scenarios(self):
        yield "say", lambda: self.say(sent("en"))
        yield (
            "say",
            lambda: self.say(sent("en", warning="w", warning_code="unaddressed")),
        )
        yield (
            "say",
            lambda: self.say(sent("en", note="n", note_code="addressed_to_person")),
        )
        yield "say", lambda: self.say(refusal(409, "session_not_registered", "no"))
        yield "say", lambda: self.say(failure=requests.ConnectionError("down"))
        yield "say", lambda: self.say(sent("en"), text=None)
        yield "ask", lambda: self.ask(sent("en"), [full_envelope("en")])
        yield "ask", lambda: self.ask(sent("en"), [NO_ANSWER] * 20)
        yield "ask", lambda: self.ask(sent("en"), [requests.ConnectionError("down")])
        yield "ask", lambda: self.ask(sent("en"), [Answer({"language": "en"})])
        yield "ask", lambda: self.ask(refusal(409, "session_not_registered", "no"))

    def test_the_reader_gets_the_same_result_when_every_sentence_is_other_words(self):
        for index, (command, scenario) in enumerate(self.scenarios()):
            self.store_credentials()
            known = scenario()
            self.store_credentials()
            with patch.object(client, "CATALOGUE", other_words_catalogue(self)):
                changed = scenario()
            with self.subTest(index=index, command=command):
                self.assertEqual(known.result, changed.result)
                self.assertEqual(known.code, changed.code)
                self.assertEqual(known.result["command"], command)

    def test_the_substituted_catalogue_really_changes_what_the_client_says(self):
        self.store_credentials()
        known = self.say(sent("en"))
        with patch.object(client, "CATALOGUE", other_words_catalogue(self)):
            changed = self.say(sent("en"))
        self.assertNotEqual(known.stdout, changed.stdout)
        self.assertIn("WORDS say_sent", changed.stdout)

    def test_the_command_name_leads_and_a_failure_ends_with_a_snake_case_code(self):
        for index, (command, scenario) in enumerate(self.scenarios()):
            self.store_credentials()
            result = scenario().result
            with self.subTest(index=index):
                self.assertEqual(list(result)[:3], ["command", "ok", "agent"])
                self.assertEqual(result["command"], command)
                if result["ok"]:
                    self.assertNotIn("code", result)
                else:
                    self.assertEqual(list(result)[-1], "code")
                    self.assertRegex(result["code"], r"^[a-z][a-z0-9_]*$")

    def test_the_result_is_a_fixed_ascii_prefix_and_one_json_object(self):
        for index, (_, scenario) in enumerate(self.scenarios()):
            self.store_credentials()
            line = result_lines(scenario().stdout)[0]
            with self.subTest(index=index):
                self.assertRegex(line, r"^AGENTSCHAT-RESULT \{.*\}$")
                self.assertTrue(line.isascii())


class HelpTests(MessagingCase):
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
                "listener: ждать сообщение и выйти",
                "отправить сообщение в чат",
                "отправить и подождать ответ",
                "забрать накопленные сообщения",
            ],
            ("say",): [
                "текст; - читать со stdin",
                "взять текст из файла (для многострочного)",
            ],
            ("ask",): [
                "текст; - читать со stdin",
                "взять текст из файла (для многострочного)",
            ],
        },
        "en": {
            (): [
                "listener: wait for a message and exit",
                "send a message to the chat",
                "send and wait for the answer",
                "collect the accumulated messages",
            ],
            ("say",): [
                "the text; - reads it from stdin",
                "take the text from a file (for multi-line text)",
            ],
            ("ask",): [
                "the text; - reads it from stdin",
                "take the text from a file (for multi-line text)",
            ],
        },
    }

    def test_the_help_of_the_messaging_commands_follows_the_room_language(self):
        for language, by_command in self.EXPECTED.items():
            for command, phrases in by_command.items():
                for phrase in phrases:
                    with self.subTest(
                        language=language, command=command, phrase=phrase
                    ):
                        self.start_language(language)
                        self.assertIn(phrase, self.help_of(*command))

    def test_the_english_help_of_each_messaging_command_has_no_cyrillic(self):
        self.start_language("en")
        for command in (("wait",), ("say",), ("ask",), ("inbox",)):
            with self.subTest(command=command):
                self.assertIsNone(CYRILLIC.search(self.help_of(*command)))


class NoProseLeftInTheCodeTests(unittest.TestCase):
    OUTSIDE_THIS_TASK_FUNCTIONS = {"do_install", "do_uninstall", "refuse", "reported"}
    OUTSIDE_THIS_TASK_PARSERS = {"install", "uninstall"}
    OUTSIDE_THIS_TASK_CONSTANTS = {"JSON_HELP"}
    source = Path(client.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    def docstrings(self) -> set[int]:
        found = set()
        for node in ast.walk(self.tree):
            if isinstance(
                node, (ast.Module, ast.FunctionDef, ast.ClassDef)
            ) and ast.get_docstring(node, clean=False):
                found.add(id(node.body[0].value))
        return found

    def outside_this_task(self, node: ast.AST) -> bool:
        if isinstance(node, ast.FunctionDef):
            return node.name in self.OUTSIDE_THIS_TASK_FUNCTIONS
        if isinstance(node, ast.Assign):
            return any(
                isinstance(target, ast.Name)
                and target.id in self.OUTSIDE_THIS_TASK_CONSTANTS
                for target in node.targets
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            first = node.args[0] if node.args else None
            if node.func.attr == "add_parser":
                return (
                    isinstance(first, ast.Constant)
                    and first.value in self.OUTSIDE_THIS_TASK_PARSERS
                )
            owner = node.func.value
            return (
                node.func.attr == "add_argument"
                and isinstance(owner, ast.Name)
                and owner.id in self.OUTSIDE_THIS_TASK_PARSERS
            )
        return False

    def test_no_cyrillic_literal_is_left_outside_install_and_uninstall(self):
        excluded = [
            (node.lineno, node.end_lineno)
            for node in ast.walk(self.tree)
            if self.outside_this_task(node)
        ]
        docstrings = self.docstrings()
        offenders = [
            f"line {node.lineno}: {node.value[:40]}"
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and CYRILLIC.search(node.value)
            and not any(start <= node.lineno <= end for start, end in excluded)
        ]
        self.assertEqual(offenders, [])

    def test_the_scan_really_excludes_something_and_really_looks_at_main(self):
        self.assertTrue(
            any(
                isinstance(node, ast.FunctionDef) and node.name == "main"
                for node in ast.walk(self.tree)
            )
        )
        self.assertTrue(
            [node for node in ast.walk(self.tree) if self.outside_this_task(node)]
        )

    def test_the_frames_of_wait_are_assembled_in_code_around_catalogued_titles(self):
        self.assertIn("=== AGENTSCHAT: {title} ===", self.source)


if __name__ == "__main__":
    unittest.main()
