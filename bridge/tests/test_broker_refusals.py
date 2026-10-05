"""Task english-release-03: broker refusals carry a code and a localised message."""

import ast
import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from sessionchat import broker as broker_module
from sessionchat.broker import BROKER_CATALOGUE, Broker, Registration
from sessionchat.i18n import LANGUAGES
from sessionchat.protocol import LISTEN_GRACE
from sessionchat.store import insert_registration, open_store
from tests.catalogue_contract import CYRILLIC, CatalogueContract
from tests.test_sessionchat import CONFIG as RUSSIAN_CONFIG
from tests.test_sessionchat import StoreBackedBrokerMixin

BROKER_SOURCE = Path(broker_module.__file__)
AGENT = "claude-code"
ASCII_LABEL = "refactoring"
TIMED_SLOT_PARAMS = {
    "agent",
    "registered",
    "label",
    "state",
    "advice",
    "quiet",
    "left",
}


def english_config(language: str) -> dict:
    return {**RUSSIAN_CONFIG, "language": language}


class BrokerCatalogueTests(CatalogueContract, unittest.TestCase):
    catalogue = BROKER_CATALOGUE


class BrokerCatalogueUseTests(unittest.TestCase):
    def test_every_sentence_key_is_used_by_the_broker(self):
        source = BROKER_SOURCE.read_text(encoding="utf-8")
        unused = [
            key
            for key in BROKER_CATALOGUE.templates("en")
            if not key.startswith("broker.state_")
            and f'"{key.removeprefix("broker.")}"' not in source
        ]
        self.assertEqual(unused, [])

    def test_every_state_key_names_a_state_the_registration_can_report(self):
        reported = {"listening", "processing", "not_listening"}
        keys = {
            key.removeprefix("broker.state_")
            for key in BROKER_CATALOGUE.templates("en")
            if key.startswith("broker.state_")
        }
        self.assertEqual(keys, reported)

    def test_no_russian_literal_is_left_in_the_answering_code(self):
        tree = ast.parse(BROKER_SOURCE.read_text(encoding="utf-8"))
        in_scope = {
            "state_code",
            "state_word",
            "advice",
            "__init__",
            "_compose",
            "_notice",
            "_answer",
            "_refusal",
            "registration_of",
            "_refuse_taken_slot",
            "handle_login",
            "handle_logout",
            "handle_inbox",
            "handle_say",
            "_unreached",
            "handle_status",
            "_session_status",
        }
        offenders = []
        for function in ast.walk(tree):
            if (
                not isinstance(function, ast.FunctionDef)
                or function.name not in in_scope
            ):
                continue
            docstring = ast.get_docstring(function, clean=False)
            log_arguments = {
                id(argument)
                for call in ast.walk(function)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "log"
                for argument in ast.walk(call)
            }
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and CYRILLIC.search(node.value)
                    and node.value != docstring
                    and id(node) not in log_arguments
                ):
                    offenders.append(f"{function.name}: {node.value!r}")
        self.assertEqual(offenders, [])

    def test_no_text_published_into_the_room_is_a_russian_literal(self):
        tree = ast.parse(BROKER_SOURCE.read_text(encoding="utf-8"))
        offenders = []
        for call in ast.walk(tree):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "publish"
            ):
                offenders += [
                    repr(node.value)
                    for node in ast.walk(call)
                    if isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and CYRILLIC.search(node.value)
                ]
        self.assertEqual(offenders, [])


class RegistrationStateTests(unittest.TestCase):
    def registration(self) -> Registration:
        return Registration(AGENT, ASCII_LABEL, "token", time.time())

    def test_a_session_with_an_open_wait_is_listening(self):
        session = self.registration()
        session.open_waits = 1
        self.assertEqual(session.state_code(), "listening")

    def test_a_session_within_the_listen_grace_is_listening(self):
        session = self.registration()
        session.listening_until = time.time() + LISTEN_GRACE
        self.assertEqual(session.state_code(), "listening")

    def test_a_session_that_just_received_a_delivery_is_processing(self):
        session = self.registration()
        session.last_delivery = time.time() - 30
        self.assertEqual(session.state_code(), "processing")

    def test_a_session_nobody_hears_from_is_not_listening(self):
        self.assertEqual(self.registration().state_code(), "not_listening")

    def test_the_russian_state_word_is_still_what_status_prints(self):
        session = self.registration()
        broker = Broker(RUSSIAN_CONFIG)
        self.assertEqual(broker.state_word(session.state_code()), "НЕ СЛУШАЕТ")
        session.open_waits = 1
        self.assertEqual(broker.state_word(session.state_code()), "слушает")
        session.open_waits = 0
        session.last_delivery = time.time() - 30
        self.assertEqual(broker.state_word(session.state_code()), "обрабатывает")


class RefusalCase(StoreBackedBrokerMixin, unittest.IsolatedAsyncioTestCase):
    async def serve(self, language: str) -> tuple[TestClient, Broker]:
        broker = Broker(english_config(language), self.make_store_path())
        client = TestClient(TestServer(broker.app()))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        self.addAsyncCleanup(self.close_matrix_clients, broker)
        return client, broker

    async def close_matrix_clients(self, broker: Broker) -> None:
        for client in broker.clients.values():
            await client.close()

    async def login(self, client: TestClient, **fields) -> object:
        return await client.post(
            "/login", json={"agent": AGENT, "label": ASCII_LABEL, **fields}
        )

    def assert_refusal(self, status, body, code, message, params):
        self.assertEqual(status, body["status"])
        self.assertEqual(code, body["json"]["code"])
        self.assertEqual(message, body["json"]["message"])
        self.assertEqual(params, body["json"]["params"])

    async def refused(self, response) -> dict:
        text = await response.text()
        return {"status": response.status, "json": json.loads(text), "text": text}


class RefusalBodyTests(RefusalCase):
    async def test_a_refusal_is_json_with_exactly_code_message_and_params(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                client, _ = await self.serve(language)
                response = await client.post("/login", json={"agent": "nobody"})
                self.assertEqual(response.content_type, "application/json")
                body = await response.json()
                self.assertEqual(set(body), {"code", "message", "params"})

    async def test_the_message_is_not_escaped_so_a_reader_of_the_raw_body_can_read_it(
        self,
    ):
        client, _ = await self.serve("ru")
        response = await client.post("/login", json={"agent": "nobody"})
        self.assertIn("неизвестный агент: nobody", await response.text())


class UnknownAgentTests(RefusalCase):
    async def test_login_for_an_agent_the_broker_does_not_know(self):
        expected = {
            "ru": "неизвестный агент: nobody",
            "en": "Unknown agent: nobody",
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                client, _ = await self.serve(language)
                body = await self.refused(
                    await client.post("/login", json={"agent": "nobody"})
                )
                self.assert_refusal(
                    404, body, "unknown_agent", expected[language], {"agent": "nobody"}
                )


class ReconnectRefusalTests(RefusalCase):
    async def test_reconnect_when_nothing_is_registered(self):
        expected = {
            "ru": (
                f"переподключаться к регистрации {AGENT} не к чему: её нет. "
                "Повтори вход без --reconnect, и брокер заведёт новую."
            ),
            "en": (
                f"There is nothing to reconnect to for {AGENT}: it has no "
                "registration. Repeat the login without --reconnect and the "
                "broker will create a new one."
            ),
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                client, _ = await self.serve(language)
                body = await self.refused(
                    await self.login(client, reconnect=True, token="any")
                )
                self.assert_refusal(
                    409,
                    body,
                    "reconnect_without_registration",
                    expected[language],
                    {"agent": AGENT},
                )

    async def test_reconnect_with_a_token_that_does_not_match(self):
        expected = {
            "ru": (
                f"переподключиться к регистрации {AGENT} нельзя: токен не "
                "совпадает. Она заведена не этой сессией."
            ),
            "en": (
                f"Cannot reconnect to the registration of {AGENT}: the token "
                "does not match. It was created by another session."
            ),
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                client, _ = await self.serve(language)
                await self.login(client)
                body = await self.refused(
                    await self.login(client, reconnect=True, token="wrong")
                )
                self.assert_refusal(
                    409,
                    body,
                    "reconnect_token_mismatch",
                    expected[language],
                    {"agent": AGENT},
                )


class SlotTakenTests(RefusalCase):
    def tail(self, language: str) -> str:
        return {
            "ru": (
                "Не решай, что слот занят тобой же: метка и успешный inbox "
                "этого не доказывают. Доказывает только токен — если эта "
                "регистрация твоя, из неё же и заведена, повтори вход с "
                "ключом --reconnect: брокер сверит токен и вернёт тебе её. "
                "Не сверится — скажи человеку. Освободить немедленно может "
                f"он: agentschat logout --agent {AGENT} --force"
            ),
            "en": (
                "Do not assume the slot is held by you: the label and a "
                "successful inbox do not prove it. Only the token proves it: "
                "if this registration is yours, made from the same session, "
                "repeat the login with --reconnect and the broker will check "
                "the token and return the registration to you. If it does "
                "not match, tell the human. Only the human can free it at "
                f"once: agentschat logout --agent {AGENT} --force"
            ),
        }[language]

    def head(self, language: str, params: dict, state_word: str) -> str:
        if language == "ru":
            return (
                f"агент {AGENT} уже подключён с {params['registered']} "
                f"({ASCII_LABEL}, {state_word})."
            )
        return (
            f"Agent {AGENT} has been connected since {params['registered']} "
            f"({ASCII_LABEL}, {state_word})."
        )

    async def refuse_second_login(self, language: str, adjust) -> tuple[dict, Broker]:
        client, broker = await self.serve(language)
        await self.login(client)
        adjust(broker.registrations[AGENT])
        return await self.refused(await self.login(client, label="second")), broker

    def polled(self, session: Registration) -> None:
        session.registered_at = session.last_contact = time.time() - 20
        session.listening_until = time.time() + 50

    def silent(self, session: Registration) -> None:
        session.registered_at = session.last_contact = time.time() - 60

    def processing(self, session: Registration) -> None:
        session.registered_at = session.last_contact = time.time() - 60
        session.last_delivery = time.time() - 30

    def over_limit(self, session: Registration) -> None:
        session.registered_at = session.last_contact = time.time() - 600
        session.open_waits = 1
        session.listening_until = time.time() - 10

    async def test_a_session_polled_recently_keeps_its_slot_with_polling_advice(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                body, _ = await self.refuse_second_login(language, self.polled)
                params = body["json"]["params"]
                quiet, left = params["quiet"], params["left"]
                self.assertEqual(
                    {
                        "agent": AGENT,
                        "registered": params["registered"],
                        "label": ASCII_LABEL,
                        "state": "listening",
                        "advice": "polled",
                        "quiet": quiet,
                        "left": left,
                    },
                    params,
                )
                self.assertEqual(409, body["status"])
                self.assertEqual("slot_taken", body["json"]["code"])
                advice = {
                    "ru": (
                        f"Та сессия опрашивала брокера {quiet}с назад. Если она "
                        "жива, слот занят по делу; если её только что убили, он "
                        f"освободится сам через {left}с — повтори вход тогда."
                    ),
                    "en": (
                        f"That session polled the broker {quiet}s ago. If it is "
                        "alive, the slot is taken for a reason; if it was killed "
                        f"just now, the slot frees itself in {left}s - repeat "
                        "the login then."
                    ),
                }[language]
                state_word = {"ru": "слушает", "en": "listening"}[language]
                self.assertEqual(
                    f"{self.head(language, params, state_word)} {advice} "
                    f"{self.tail(language)}",
                    body["json"]["message"],
                )

    async def test_a_silent_session_keeps_its_slot_with_the_silence_advice(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                body, _ = await self.refuse_second_login(language, self.silent)
                params = body["json"]["params"]
                quiet, left = params["quiet"], params["left"]
                self.assertEqual("silent", params["advice"])
                self.assertEqual(409, body["status"])
                advice = {
                    "ru": (
                        f"Та сессия молчит {quiet}с. Если её больше нет, слот "
                        f"освободится сам через {left}с — повтори вход тогда, "
                        "перехват не нужен."
                    ),
                    "en": (
                        f"That session has been silent for {quiet}s. If it is "
                        f"gone, the slot frees itself in {left}s - repeat the "
                        "login then, no takeover is needed."
                    ),
                }[language]
                state_word = {"ru": "НЕ СЛУШАЕТ", "en": "NOT LISTENING"}[language]
                self.assertEqual("not_listening", params["state"])
                self.assertEqual(
                    f"{self.head(language, params, state_word)} {advice} "
                    f"{self.tail(language)}",
                    body["json"]["message"],
                )

    async def test_a_session_handling_a_delivery_is_named_as_processing(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                body, _ = await self.refuse_second_login(language, self.processing)
                state_word = {"ru": "обрабатывает", "en": "processing"}[language]
                self.assertEqual("processing", body["json"]["params"]["state"])
                self.assertIn(f"({ASCII_LABEL}, {state_word})", body["json"]["message"])

    async def test_a_session_silent_past_the_limit_is_told_the_slot_is_free(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                body, _ = await self.refuse_second_login(language, self.over_limit)
                params = body["json"]["params"]
                self.assertEqual("over_limit", params["advice"])
                self.assertEqual(409, body["status"])
                advice = {
                    "ru": "Та сессия молчит дольше предела; повтори вход — слот твой.",
                    "en": (
                        "That session has been silent past the limit; repeat "
                        "the login - the slot is yours."
                    ),
                }[language]
                state_word = {"ru": "слушает", "en": "listening"}[language]
                self.assertEqual("listening", params["state"])
                self.assertEqual(
                    f"{self.head(language, params, state_word)} {advice} "
                    f"{self.tail(language)}",
                    body["json"]["message"],
                )

    async def test_the_params_name_every_number_and_word_the_sentence_used(self):
        body, _ = await self.refuse_second_login("en", self.silent)
        self.assertEqual(TIMED_SLOT_PARAMS, set(body["json"]["params"]))

    async def test_neither_the_message_nor_the_params_carry_the_token(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                client, broker = await self.serve(language)
                first = await (await self.login(client)).json()
                refused = await self.refused(await self.login(client, label="second"))
                mismatch = await self.refused(
                    await self.login(client, reconnect=True, token="wrong")
                )
                for body in (refused, mismatch):
                    self.assertNotIn(first["token"], body["text"])
                    self.assertNotIn("wrong", body["text"])


class SlotHeldInStoreTests(RefusalCase):
    async def test_a_row_in_the_store_that_memory_does_not_know_holds_the_slot(self):
        expected = {
            "ru": (
                f"агент {AGENT} уже имеет регистрацию в хранилище. Повтори вход "
                "с --reconnect, если токен совпадёт, или пусть человек "
                f"освободит слот: agentschat logout --agent {AGENT} --force"
            ),
            "en": (
                f"Agent {AGENT} already has a registration in the store. "
                "Repeat the login with --reconnect if the token matches, or "
                "ask the human to free the slot: "
                f"agentschat logout --agent {AGENT} --force"
            ),
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                client, broker = await self.serve(language)
                broker.store_path.parent.mkdir(parents=True, exist_ok=True)
                with open_store(broker.store_path) as store:
                    insert_registration(
                        store, AGENT, "someone", "stored-token", time.time(), depth=0
                    )
                body = await self.refused(await self.login(client))
                self.assert_refusal(
                    409, body, "slot_in_store", expected[language], {"agent": AGENT}
                )
                self.assertNotIn("stored-token", body["text"])


class SessionNotRegisteredTests(RefusalCase):
    async def test_logout_with_a_token_the_broker_does_not_hold(self):
        expected = {
            "ru": "сессия не подключена или токен неверен",
            "en": "The session is not connected or the token is wrong.",
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                client, _ = await self.serve(language)
                await self.login(client)
                body = await self.refused(
                    await client.post(
                        "/logout", json={"agent": AGENT, "token": "wrong"}
                    )
                )
                self.assert_refusal(
                    409, body, "session_not_registered", expected[language], {}
                )

    async def test_an_agent_that_never_logged_in_gets_the_same_refusal(self):
        client, _ = await self.serve("en")
        body = await self.refused(
            await client.get("/inbox", params={"agent": AGENT, "token": "x"})
        )
        self.assertEqual("session_not_registered", body["json"]["code"])
        self.assertEqual(409, body["status"])

    async def test_a_forced_logout_is_never_refused(self):
        client, _ = await self.serve("en")
        response = await client.post("/logout", json={"agent": AGENT, "force": True})
        self.assertEqual(200, response.status)


class UnknownDeliveryTests(unittest.TestCase):
    def broken(self, language: str) -> dict:
        agents = RUSSIAN_CONFIG["agents"]
        return {
            **english_config(language),
            "agents": {
                **agents,
                "opencode": {**agents["opencode"], "delivery": "poll"},
            },
        }

    def test_the_refusal_to_start_names_the_agent_the_value_and_the_allowed_ones(self):
        expected = {
            "ru": (
                "агент opencode: неизвестный delivery: 'poll'. "
                "Допустимые значения: listener, plugin."
            ),
            "en": (
                "Agent opencode: unknown delivery: 'poll'. "
                "Allowed values: listener, plugin."
            ),
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                with self.assertRaises(ValueError) as raised:
                    Broker(self.broken(language))
                self.assertEqual(expected[language], str(raised.exception))

    def test_the_english_refusal_has_no_cyrillic(self):
        with self.assertRaises(ValueError) as raised:
            Broker(self.broken("en"))
        self.assertIsNone(CYRILLIC.search(str(raised.exception)))


class EnglishRefusalsHaveNoCyrillicTests(RefusalCase):
    async def test_every_refusal_under_en_is_english_only(self):
        client, _ = await self.serve("en")
        await self.login(client)
        responses = [
            await client.post("/login", json={"agent": "nobody"}),
            await self.login(client, label="second"),
            await self.login(client, reconnect=True, token="wrong"),
            await client.post("/logout", json={"agent": AGENT, "token": "wrong"}),
        ]
        for response in responses:
            text = await response.text()
            with self.subTest(text=text):
                self.assertIsNone(CYRILLIC.search(text))
                self.assertTrue(text.isascii())


class ReconnectStillWorksTests(RefusalCase):
    async def test_a_successful_reconnect_is_not_a_refusal(self):
        client, _ = await self.serve("en")
        first = await (await self.login(client)).json()
        with patch.object(broker_module.log, "info"):
            response = await self.login(client, reconnect=True, token=first["token"])
        self.assertEqual(200, response.status)
        self.assertTrue((await response.json())["reconnected"])
