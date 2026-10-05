"""Task english-release-04: say, inbox, status and room notices in the room language."""

import io
import time
import types
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from sessionchat import client
from sessionchat.broker import Broker, Registration
from sessionchat.i18n import LANGUAGES
from sessionchat.protocol import MAX_DEPTH, MAX_SENDS_PER_MINUTE
from tests.catalogue_contract import CYRILLIC
from tests.result_line import without_result
from tests.test_broker_refusals import english_config
from tests.test_client_language import Answer, ClientLanguageTestCase
from tests.test_sessionchat import StoreBackedBrokerMixin

AGENT = "claude-code"
OTHER = "opencode"
LABEL = "refactoring"
CODES_OF_THE_BROKER = (
    "empty_message",
    "depth_limit",
    "rate_limit",
    "unaddressed",
    "addressed_to_person",
    "not_connected",
)


class RoomCase(StoreBackedBrokerMixin, unittest.IsolatedAsyncioTestCase):
    async def serve(self, language: str) -> tuple[TestClient, Broker, list]:
        broker = Broker(english_config(language), self.make_store_path())
        published: list[tuple[str, str, int]] = []

        async def publish(agent, text, depth):
            published.append((agent, text, depth))
            return "$published"

        broker.publish = publish
        client_ = TestClient(TestServer(broker.app()))
        await client_.start_server()
        self.addAsyncCleanup(client_.close)
        self.addAsyncCleanup(self.close_matrix_clients, broker)
        return client_, broker, published

    async def close_matrix_clients(self, broker: Broker) -> None:
        for matrix_client in broker.clients.values():
            await matrix_client.close()

    async def connected(self, language: str):
        web, broker, published = await self.serve(language)
        answer = await web.post("/login", json={"agent": AGENT, "label": LABEL})
        token = (await answer.json())["token"]
        return web, broker, published, token

    async def say(self, web: TestClient, token: str, text: str):
        return await web.post(
            "/say", json={"agent": AGENT, "token": token, "text": text}
        )

    def neighbour(self, broker: Broker, agent: str = OTHER) -> None:
        broker.registrations[agent] = Registration(
            agent, "next door", "t2", time.time()
        )


class SayRefusalTests(RoomCase):
    SCENARIOS = {
        "empty_message": {
            "status": 400,
            "params": {},
            "ru": "пустое сообщение",
            "en": "The message is empty.",
        },
        "depth_limit": {
            "status": 403,
            "params": {"max_depth": MAX_DEPTH},
            "ru": (
                f"достигнута предельная глубина цепочки ({MAX_DEPTH}) без участия "
                "человека. Сообщение не отправлено: нужен человек. Об этом "
                "сказано в комнате, повторять не надо."
            ),
            "en": (
                f"The chain depth limit ({MAX_DEPTH}) was reached without a human. "
                "The message was not sent: a human is needed. The room has been "
                "told about it, there is no need to repeat."
            ),
        },
        "rate_limit": {
            "status": 429,
            "params": {"limit": MAX_SENDS_PER_MINUTE},
            "ru": f"превышен предел {MAX_SENDS_PER_MINUTE} сообщений в минуту",
            "en": f"The limit of {MAX_SENDS_PER_MINUTE} messages per minute was exceeded.",
        },
    }

    async def provoke(self, code: str, language: str):
        web, broker, published, token = await self.connected(language)
        registration = broker.registrations[AGENT]
        text = "hello"
        if code == "empty_message":
            text = "   "
        if code == "depth_limit":
            registration.depth = broker.max_depth
        if code == "rate_limit":
            registration.sends.extend([time.time()] * MAX_SENDS_PER_MINUTE)
        return await self.say(web, token, text), published

    async def test_every_refusal_in_both_languages(self):
        for code, expected in self.SCENARIOS.items():
            for language in LANGUAGES:
                with self.subTest(code=code, language=language):
                    response, _ = await self.provoke(code, language)
                    body = await response.json()
                    self.assertEqual(response.status, expected["status"])
                    self.assertEqual(response.content_type, "application/json")
                    self.assertEqual(set(body), {"code", "message", "params"})
                    self.assertEqual(body["code"], code)
                    self.assertEqual(body["message"], expected[language])
                    self.assertEqual(body["params"], expected["params"])

    async def test_the_english_refusals_have_no_cyrillic(self):
        for code in self.SCENARIOS:
            with self.subTest(code=code):
                response, _ = await self.provoke(code, "en")
                self.assertIsNone(CYRILLIC.search(await response.text()))

    async def test_the_code_and_the_params_do_not_depend_on_the_language(self):
        for code in self.SCENARIOS:
            seen = []
            for language in LANGUAGES:
                response, _ = await self.provoke(code, language)
                body = await response.json()
                seen.append((response.status, body["code"], body["params"]))
            with self.subTest(code=code):
                self.assertEqual(seen[0], seen[1])

    async def test_the_refusal_text_is_not_escaped_for_a_reader_of_the_raw_body(self):
        response, _ = await self.provoke("empty_message", "ru")
        self.assertIn("пустое сообщение", await response.text())

    async def test_only_the_depth_limit_posts_a_notice_into_the_room(self):
        for code in self.SCENARIOS:
            with self.subTest(code=code):
                _, published = await self.provoke(code, "en")
                self.assertEqual(len(published), 1 if code == "depth_limit" else 0)


class RoomNoticeTests(RoomCase):
    DEPTH = {
        "ru": (
            f"(цепочка достигла предела глубины {MAX_DEPTH} без участия человека, "
            "дальше агенты продолжать не могут. Напишите что-нибудь в комнату "
            "— это обнулит счётчик.)"
        ),
        "en": (
            f"(The chain reached the depth limit of {MAX_DEPTH} without a human, "
            "so agents cannot continue. Write anything in the room to reset "
            "the counter.)"
        ),
    }
    NOT_CONNECTED = {
        "ru": (
            f"(сессия {OTHER} не подключена, сообщение не доставлено. "
            f"Выполните @chatlogin в нужной сессии {OTHER}.)"
        ),
        "en": (
            f"(The session {OTHER} is not connected, so the message was not "
            f"delivered. Run @chatlogin in the {OTHER} session you need.)"
        ),
    }

    async def depth_notice(self, language: str):
        web, broker, published, token = await self.connected(language)
        broker.registrations[AGENT].depth = broker.max_depth
        await self.say(web, token, "again")
        return published

    async def not_connected_notice(self, language: str):
        _, broker, published = await self.serve(language)
        human = types.SimpleNamespace(
            body=f"@{OTHER} are you there?",
            sender="@human:local",
            event_id="$event",
            server_timestamp=int(time.time() * 1000) + 1000,
            source={"content": {"body": f"@{OTHER} are you there?"}},
        )
        await broker.on_message(types.SimpleNamespace(room_id="!room:local"), human)
        return published

    async def test_the_depth_notice_is_in_the_room_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                published = await self.depth_notice(language)
                self.assertEqual(published, [(AGENT, self.DEPTH[language], 0)])

    async def test_the_not_connected_notice_is_in_the_room_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                published = await self.not_connected_notice(language)
                self.assertEqual(published, [(OTHER, self.NOT_CONNECTED[language], 0)])

    async def test_the_english_notices_have_no_cyrillic(self):
        for notice in (self.depth_notice, self.not_connected_notice):
            with self.subTest(notice=notice.__name__):
                (_, text, _) = (await notice("en"))[0]
                self.assertIsNone(CYRILLIC.search(text))

    async def test_no_code_reaches_the_matrix_body(self):
        for language in LANGUAGES:
            for notice in (self.depth_notice, self.not_connected_notice):
                with self.subTest(language=language, notice=notice.__name__):
                    (_, text, _) = (await notice(language))[0]
                    for code in CODES_OF_THE_BROKER:
                        self.assertNotIn(code, text)
                    self.assertNotIn("broker.", text)
                    self.assertNotIn("{", text)

    async def test_a_message_that_is_published_carries_the_sender_text_untouched(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                web, _, published, token = await self.connected(language)
                await self.say(web, token, "@opencode hello there")
                self.assertEqual(published, [(AGENT, "@opencode hello there", 1)])


class SayRemarkTests(RoomCase):
    NOTE = {
        "ru": (
            "агентам сообщение не доставлено: обращение в нём не к агенту. "
            "Человек видит его в комнате."
        ),
        "en": (
            "The message was not delivered to agents: it is not addressed to "
            "an agent. The human can see it in the room."
        ),
    }

    def warning(self, language: str, tail: str) -> str:
        if language == "ru":
            return (
                "сообщение опубликовано, но НИ ОДИН агент его не получил: в нём "
                "нет обращения. Адресуй явно — @имя или @room. " + tail
            )
        return (
            "The message was published, but NO agent received it: it has no "
            "addressee. Address an agent explicitly with @name, or everyone "
            "with @room. " + tail
        )

    async def answer(self, language: str, text: str, neighbours=(OTHER,)):
        web, broker, _, token = await self.connected(language)
        for agent in neighbours:
            self.neighbour(broker, agent)
        response = await self.say(web, token, text)
        self.assertEqual(response.status, 200)
        return await response.json()

    async def test_answering_a_person_gets_a_note_with_a_code(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                answer = await self.answer(language, "@human Claude Code: opus")
                self.assertEqual(answer["note"], self.NOTE[language])
                self.assertEqual(answer["note_code"], "addressed_to_person")
                self.assertNotIn("warning", answer)
                self.assertNotIn("warning_code", answer)

    async def test_an_unaddressed_message_gets_a_warning_with_a_code(self):
        tails = {
            "ru": f"Сейчас подключены: {OTHER}.",
            "en": f"Connected right now: {OTHER}.",
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                answer = await self.answer(language, "thinking out loud")
                self.assertEqual(
                    answer["warning"], self.warning(language, tails[language])
                )
                self.assertEqual(answer["warning_code"], "unaddressed")
                self.assertNotIn("note", answer)
                self.assertNotIn("note_code", answer)

    async def test_the_warning_lists_the_other_sessions_sorted(self):
        tails = {
            "ru": f"Сейчас подключены: alpha, {OTHER}, zeta.",
            "en": f"Connected right now: alpha, {OTHER}, zeta.",
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                answer = await self.answer(
                    language, "thinking out loud", ("zeta", OTHER, "alpha")
                )
                self.assertEqual(
                    answer["warning"], self.warning(language, tails[language])
                )

    async def test_the_warning_says_when_nobody_else_is_connected(self):
        tails = {
            "ru": "Сейчас других подключённых сессий нет.",
            "en": "There are no other connected sessions right now.",
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                answer = await self.answer(language, "thinking out loud", ())
                self.assertEqual(
                    answer["warning"], self.warning(language, tails[language])
                )

    async def test_a_message_to_oneself_still_warns(self):
        answer = await self.answer("en", f"@{AGENT} a note for myself", ())
        self.assertEqual(answer["warning_code"], "unaddressed")

    async def test_an_addressed_message_carries_neither_remark_nor_code(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                answer = await self.answer(language, "@opencode here is the plan")
                self.assertEqual(set(answer), {"event_id", "depth", "language"})

    async def test_the_codes_do_not_depend_on_the_language(self):
        for text in ("@human hi", "thinking out loud"):
            seen = []
            for language in LANGUAGES:
                answer = await self.answer(language, text)
                seen.append(
                    (
                        answer.get("note_code"),
                        answer.get("warning_code"),
                        answer["depth"],
                    )
                )
            with self.subTest(text=text):
                self.assertEqual(seen[0], seen[1])

    async def test_the_english_remarks_have_no_cyrillic(self):
        for text in ("@human hi", "thinking out loud"):
            with self.subTest(text=text):
                answer = await self.answer("en", text)
                self.assertIsNone(CYRILLIC.search(str(answer)))

    async def test_the_remark_text_is_not_escaped_for_a_reader_of_the_raw_body(self):
        web, broker, _, token = await self.connected("ru")
        self.neighbour(broker)
        raw = await (await self.say(web, token, "thinking out loud")).text()
        self.assertIn("НИ ОДИН агент", raw)

    async def test_a_successful_say_names_the_room_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                answer = await self.answer(language, "@opencode plan")
                self.assertEqual(answer["language"], language)


class InboxTests(RoomCase):
    async def test_the_inbox_names_the_room_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                web, _, _, token = await self.connected(language)
                response = await web.get(
                    "/inbox", params={"agent": AGENT, "token": token}
                )
                self.assertEqual(
                    await response.json(), {"language": language, "pending": []}
                )

    async def test_an_inbox_refusal_is_the_coded_refusal_of_task_03(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                web, _, _, _ = await self.connected(language)
                response = await web.get(
                    "/inbox", params={"agent": AGENT, "token": "wrong"}
                )
                body = await response.json()
                self.assertEqual(response.status, 409)
                self.assertEqual(body["code"], "session_not_registered")


class StatusCase(RoomCase):
    WORDS = {
        "ru": {
            "listening": "слушает",
            "processing": "обрабатывает",
            "not_listening": "НЕ СЛУШАЕТ",
        },
        "en": {
            "listening": "listening",
            "processing": "processing",
            "not_listening": "NOT LISTENING",
        },
    }
    WIDTH = {"ru": 12, "en": 13}

    async def state_of(self, language: str, state: str):
        web, broker, _, _ = await self.connected(language)
        registration = broker.registrations[AGENT]
        if state == "listening":
            registration.open_waits = 1
        if state == "processing":
            registration.last_delivery = time.time() - 30
        answer = await (await web.get("/status")).json()
        return answer, registration

    def expected_line(self, language: str, state: str, entry: dict) -> str:
        word = self.WORDS[language][state].ljust(self.WIDTH[language])
        frame = {
            "ru": "(подключена {registered}, тишина {quiet}с)",
            "en": "(connected {registered}, quiet for {quiet}s)",
        }[language].format(**entry)
        return f"{AGENT:<14} {word} {LABEL} {frame}"


class StatusTests(StatusCase):
    async def test_every_state_in_both_languages(self):
        for language in LANGUAGES:
            for state in self.WORDS[language]:
                with self.subTest(language=language, state=state):
                    answer, registration = await self.state_of(language, state)
                    entry = answer["sessions"][0]
                    stamp = datetime.fromtimestamp(registration.registered_at)
                    self.assertEqual(entry["state"], state)
                    self.assertEqual(entry["registered"], stamp.strftime("%H:%M:%S"))
                    self.assertEqual(
                        entry["line"], self.expected_line(language, state, entry)
                    )

    async def test_an_agent_without_a_session_is_not_connected_in_both_languages(self):
        expected = {
            "ru": f"{OTHER:<14} не подключён",
            "en": f"{OTHER:<14} not connected",
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                answer, _ = await self.state_of(language, "not_listening")
                self.assertEqual(
                    answer["sessions"][1],
                    {
                        "agent": OTHER,
                        "state": "not_connected",
                        "line": expected[language],
                    },
                )

    async def test_the_answer_is_the_language_and_one_entry_per_configured_agent(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                answer, _ = await self.state_of(language, "listening")
                self.assertEqual(set(answer), {"language", "sessions"})
                self.assertEqual(answer["language"], language)
                self.assertEqual(
                    [entry["agent"] for entry in answer["sessions"]], [AGENT, OTHER]
                )

    async def test_a_connected_entry_has_exactly_the_documented_fields(self):
        answer, _ = await self.state_of("en", "listening")
        self.assertEqual(
            set(answer["sessions"][0]),
            {"agent", "state", "label", "registered", "quiet", "line"},
        )

    async def test_the_quiet_time_is_counted_in_seconds_since_the_last_sign_of_life(
        self,
    ):
        web, broker, _, _ = await self.connected("en")
        broker.registrations[AGENT].registered_at = time.time() - 100
        entry = (await (await web.get("/status")).json())["sessions"][0]
        self.assertIn(entry["quiet"], range(100, 103))
        self.assertIn(f"quiet for {entry['quiet']}s", entry["line"])

    async def test_the_state_codes_and_fields_do_not_depend_on_the_language(self):
        for state in ("listening", "processing", "not_listening"):
            seen = []
            for language in LANGUAGES:
                answer, _ = await self.state_of(language, state)
                entry = answer["sessions"][0]
                seen.append(
                    (
                        entry["state"],
                        entry["label"],
                        len(entry["registered"]),
                        [session["state"] for session in answer["sessions"]],
                    )
                )
            with self.subTest(state=state):
                self.assertEqual(seen[0], seen[1])

    async def test_the_status_is_json_whatever_the_client_asks_for(self):
        web, _, _, _ = await self.connected("en")
        for headers in ({}, {"Accept": "*/*"}, {"Accept": "text/plain"}):
            with self.subTest(headers=headers):
                response = await web.get("/status", headers=headers)
                self.assertEqual(response.content_type, "application/json")
                self.assertEqual(set(await response.json()), {"language", "sessions"})

    async def test_the_status_text_is_not_escaped_for_a_reader_of_the_raw_body(self):
        web, _, _, _ = await self.connected("ru")
        self.assertIn("не подключён", await (await web.get("/status")).text())

    async def test_the_english_status_has_no_cyrillic(self):
        for state in self.WORDS["en"]:
            with self.subTest(state=state):
                answer, _ = await self.state_of("en", state)
                self.assertIsNone(CYRILLIC.search(str(answer)))

    async def test_the_state_column_is_as_wide_as_the_widest_word_of_the_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                broker = Broker(english_config(language), self.make_store_path())
                self.addAsyncCleanup(self.close_matrix_clients, broker)
                self.assertEqual(broker.state_width, self.WIDTH[language])


class StatusAsTheClientPrintsItTests(StatusCase, ClientLanguageTestCase):
    async def printed(self, language: str, state: str) -> str:
        answer, _ = await self.state_of(language, state)
        output = io.StringIO()
        with (
            patch.object(client.requests, "get", return_value=Answer(answer)),
            redirect_stdout(output),
        ):
            client.do_status(types.SimpleNamespace())
        return without_result(output.getvalue())

    async def test_the_client_prints_the_rendered_lines_one_per_agent(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                answer, _ = await self.state_of(language, "listening")
                lines = [entry["line"] for entry in answer["sessions"]]
                self.assertEqual(
                    await self.printed(language, "listening"), "\n".join(lines) + "\n"
                )

    async def test_the_russian_output_is_what_the_client_printed_before(self):
        text = await self.printed("ru", "listening")
        first, second = text.splitlines()
        self.assertRegex(
            first,
            r"^claude-code    слушает      refactoring "
            r"\(подключена \d\d:\d\d:\d\d, тишина \d+с\)$",
        )
        self.assertEqual(second, "opencode       не подключён")

    async def test_the_client_remembers_the_language_the_status_named(self):
        await self.printed("ru", "listening")
        self.assertEqual(self.language_file.read_text(encoding="utf-8").strip(), "ru")

    async def test_the_client_prints_whatever_sentences_the_broker_rendered(self):
        answer = {
            "language": "en",
            "sessions": [
                {"agent": AGENT, "state": "listening", "line": "other words entirely"}
            ],
        }
        output = io.StringIO()
        with (
            patch.object(client.requests, "get", return_value=Answer(answer)),
            redirect_stdout(output),
        ):
            client.do_status(types.SimpleNamespace())
        self.assertEqual(without_result(output.getvalue()), "other words entirely\n")

    async def test_an_answer_without_sessions_prints_an_empty_line(self):
        output = io.StringIO()
        with (
            patch.object(
                client.requests, "get", return_value=Answer({"language": "en"})
            ),
            redirect_stdout(output),
        ):
            client.do_status(types.SimpleNamespace())
        self.assertEqual(without_result(output.getvalue()), "\n")


class SayAsTheClientPrintsItTests(RoomCase, ClientLanguageTestCase):
    async def printed(self, language: str, text: str) -> str:
        web, broker, _, token = await self.connected(language)
        self.neighbour(broker)
        answer = await (await self.say(web, token, text)).json()
        self.store_credentials()
        output = io.StringIO()
        with (
            patch.object(client.requests, "post", return_value=Answer(answer)),
            redirect_stdout(output),
        ):
            client.do_say(types.SimpleNamespace(agent=AGENT, text="hi", file=None))
        return output.getvalue()

    async def test_the_russian_warning_is_printed_as_before(self):
        lines = (await self.printed("ru", "thinking out loud")).splitlines()
        self.assertRegex(lines[0], r"^AGENTSCHAT: отправлено \(.+\)\.$")
        self.assertEqual(
            lines[1],
            "AGENTSCHAT: ВНИМАНИЕ — сообщение опубликовано, но НИ ОДИН агент его "
            "не получил: в нём нет обращения. Адресуй явно — @имя или @room. "
            f"Сейчас подключены: {OTHER}.",
        )

    async def test_the_russian_note_is_printed_as_before(self):
        lines = (await self.printed("ru", "@human fine")).splitlines()
        self.assertEqual(
            lines[1],
            "AGENTSCHAT: агентам сообщение не доставлено: обращение в нём не к "
            "агенту. Человек видит его в комнате.",
        )

    async def test_the_client_remembers_the_language_the_say_answer_named(self):
        await self.printed("ru", "@opencode plan")
        self.assertEqual(self.language_file.read_text(encoding="utf-8").strip(), "ru")


if __name__ == "__main__":
    unittest.main()
