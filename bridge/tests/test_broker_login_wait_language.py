"""Task english-release-08: login and wait answers name the room language."""

import types
import unittest

from aiohttp.test_utils import TestClient, TestServer

from sessionchat.broker import Broker
from tests.catalogue_contract import CYRILLIC
from tests.test_sessionchat import CONFIG as RUSSIAN_CONFIG
from tests.test_sessionchat import StoreBackedBrokerMixin, event

LANGUAGES = ("en", "ru")
AGENT = "claude-code"


class RoomCase(StoreBackedBrokerMixin, unittest.IsolatedAsyncioTestCase):
    async def serve(self, language: str) -> TestClient:
        config = {**RUSSIAN_CONFIG, "language": language}
        self.broker = Broker(config, self.make_store_path())
        web = TestClient(TestServer(self.broker.app()))
        await web.start_server()
        self.addAsyncCleanup(web.close)
        self.addAsyncCleanup(self.close_matrix_clients, self.broker)
        return web

    async def close_matrix_clients(self, broker: Broker) -> None:
        for matrix_client in broker.clients.values():
            await matrix_client.close()


class LoginNamesTheRoomLanguageTests(RoomCase):
    async def test_a_new_registration_answer_carries_the_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                web = await self.serve(language)
                response = await web.post("/login", json={"agent": AGENT})
                self.assertEqual((await response.json())["language"], language)

    async def test_a_reconnect_answer_carries_the_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                web = await self.serve(language)
                first = await web.post("/login", json={"agent": AGENT})
                token = (await first.json())["token"]
                response = await web.post(
                    "/login",
                    json={"agent": AGENT, "reconnect": True, "token": token},
                )
                answer = await response.json()
                self.assertTrue(answer["reconnected"])
                self.assertEqual(answer["language"], language)

    async def test_the_answer_keeps_the_fields_the_client_already_reads(self):
        web = await self.serve("en")
        response = await web.post("/login", json={"agent": AGENT})
        self.assertEqual(
            set(await response.json()), {"token", "room", "mode", "language"}
        )


class WaitNamesTheRoomLanguageTests(RoomCase):
    async def delivered(self, language: str) -> dict:
        web = await self.serve(language)
        login = await web.post("/login", json={"agent": AGENT})
        token = (await login.json())["token"]
        await self.broker.on_message(
            types.SimpleNamespace(room_id="!room:local"),
            event("@claude-code check the build"),
        )
        response = await web.get("/wait", params={"agent": AGENT, "token": token})
        self.assertEqual(response.status, 200)
        return await response.json()

    async def test_the_answer_carries_the_language_next_to_the_envelope(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                answer = await self.delivered(language)
                self.assertEqual(answer["language"], language)
                self.assertTrue(answer["rendered"])

    async def test_the_fields_the_plugin_reads_are_still_there(self):
        answer = await self.delivered("en")
        self.assertTrue(
            {"rendered", "text", "kind", "sender", "event_id", "stamp", "depth"}
            <= set(answer)
        )
        self.assertIsNone(CYRILLIC.search(answer["rendered"]))
