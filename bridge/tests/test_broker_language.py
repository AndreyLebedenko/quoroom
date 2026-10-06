"""Task english-release-02: the room language in config.yaml."""

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from aiohttp.test_utils import TestClient, TestServer

from sessionchat import broker as broker_module
from sessionchat.broker import Broker, LanguageRefused, room_language
from sessionchat.i18n import DEFAULT_LANGUAGE, LANGUAGES
from tests.test_sessionchat import CONFIG as RUSSIAN_CONFIG
from tests.test_sessionchat import StoreBackedBrokerMixin

EXAMPLE = Path(__file__).resolve().parents[1] / "config.example.yaml"
JSON = {"Accept": "application/json"}
CONFIG = {key: value for key, value in RUSSIAN_CONFIG.items() if key != "language"}
PRINTABLE_ASCII = re.compile(r"[\x20-\x7e]+")


def configured(**values) -> dict:
    return {**CONFIG, **values}


class RoomLanguageTests(unittest.TestCase):
    def test_a_config_without_the_key_means_the_default_language(self):
        self.assertEqual(room_language(CONFIG), DEFAULT_LANGUAGE)

    def test_the_default_language_is_english(self):
        self.assertEqual(DEFAULT_LANGUAGE, "en")

    def test_every_catalogued_language_is_accepted(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.assertEqual(room_language(configured(language=language)), language)

    def test_a_value_outside_the_catalogued_languages_is_refused(self):
        for value in ("fr", "EN", "ru ", "", "english", "ру"):
            with self.subTest(value=value):
                with self.assertRaises(LanguageRefused):
                    room_language(configured(language=value))

    def test_a_value_that_is_not_text_is_refused(self):
        for value in (None, 1, True, ["en"], {"en": "ru"}):
            with self.subTest(value=value):
                with self.assertRaises(LanguageRefused):
                    room_language(configured(language=value))

    def test_the_refusal_names_the_key_and_every_allowed_value(self):
        with self.assertRaises(LanguageRefused) as raised:
            room_language(configured(language="fr"))
        message = str(raised.exception)
        self.assertIn('"language"', message)
        for language in LANGUAGES:
            self.assertIn(language, message)
        self.assertIn("'fr'", message)

    def test_the_refusal_is_english_printable_ascii_for_any_value(self):
        for value in ("fr", "ру", None, 3):
            with self.subTest(value=value):
                with self.assertRaises(LanguageRefused) as raised:
                    room_language(configured(language=value))
                self.assertTrue(PRINTABLE_ASCII.fullmatch(str(raised.exception)))

    def test_a_refusal_is_a_value_error_so_existing_handlers_still_catch_it(self):
        self.assertTrue(issubclass(LanguageRefused, ValueError))


class BrokerLanguageTests(unittest.TestCase):
    def test_a_broker_without_the_key_speaks_the_default_language(self):
        self.assertEqual(Broker(CONFIG).language, DEFAULT_LANGUAGE)

    def test_a_broker_carries_the_configured_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.assertEqual(
                    Broker(configured(language=language)).language, language
                )

    def test_a_bad_value_stops_the_broker_before_it_builds_any_client(self):
        with patch.object(broker_module, "AsyncClient") as client:
            with self.assertRaises(LanguageRefused):
                Broker(configured(language="fr"))
        client.assert_not_called()

    def test_a_bad_value_stops_the_broker_even_in_an_otherwise_empty_config(self):
        with self.assertRaises(LanguageRefused):
            Broker({"language": "fr"})


class StatusLanguageTests(StoreBackedBrokerMixin, unittest.IsolatedAsyncioTestCase):
    async def serve(self, **values) -> TestClient:
        broker = Broker(configured(**values), self.make_store_path())
        client = TestClient(TestServer(broker.app()))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        self.addAsyncCleanup(self.close_matrix_clients, broker)
        return client

    async def close_matrix_clients(self, broker: Broker) -> None:
        for client in broker.clients.values():
            await client.close()

    async def test_status_reports_the_default_language_without_the_key(self):
        client = await self.serve()
        answer = await (await client.get("/status", headers=JSON)).json()
        self.assertEqual(answer["language"], "en")

    async def test_status_reports_the_configured_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                client = await self.serve(language=language)
                answer = await (await client.get("/status", headers=JSON)).json()
                self.assertEqual(answer["language"], language)

    async def test_the_json_status_is_served_as_json(self):
        client = await self.serve()
        response = await client.get("/status", headers=JSON)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "application/json")

    async def test_the_status_is_valid_json_with_only_the_language_and_the_sessions(
        self,
    ):
        client = await self.serve()
        body = await (await client.get("/status", headers=JSON)).text()
        self.assertEqual(set(json.loads(body)), {"language", "sessions"})


class MainRefusalTests(unittest.TestCase):
    def run_main(self, config: dict) -> SystemExit:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(yaml.safe_dump(config), encoding="utf-8")
            with patch("sys.argv", ["broker", "--config", str(path)]):
                with self.assertRaises(SystemExit) as raised:
                    broker_module.main()
        return raised.exception

    def test_a_bad_language_exits_with_an_english_message_naming_the_key(self):
        refusal = self.run_main(configured(language="fr"))
        message = str(refusal.code)
        self.assertIn("BROKER NOT STARTED", message)
        self.assertIn('"language"', message)
        self.assertIn("en, ru", message)
        self.assertTrue(PRINTABLE_ASCII.fullmatch(message.replace("\n", " ")))

    def test_the_refusal_is_not_wrapped_in_the_russian_startup_prefix(self):
        message = str(self.run_main(configured(language="fr")).code)
        self.assertNotRegex(message, "[Ѐ-ӿ]")


class ExampleConfigTests(unittest.TestCase):
    def text(self) -> str:
        return EXAMPLE.read_text(encoding="utf-8")

    def test_the_example_sets_the_default_language_at_the_top_level(self):
        loaded = yaml.safe_load(self.text())
        self.assertEqual(loaded["language"], DEFAULT_LANGUAGE)

    def test_the_example_loads_into_a_broker_without_a_language_complaint(self):
        loaded = yaml.safe_load(self.text())
        self.assertEqual(room_language(loaded), DEFAULT_LANGUAGE)

    def test_the_language_line_is_a_single_plain_line_the_installer_can_rewrite(self):
        lines = [
            line for line in self.text().splitlines() if line.startswith("language:")
        ]
        self.assertEqual(lines, [f"language: {DEFAULT_LANGUAGE}"])

    def test_the_example_explains_the_key_in_the_file(self):
        text = self.text()
        before = text.split("\nlanguage:")[0]
        self.assertIn("language of the whole room", before)
        for language in LANGUAGES:
            self.assertIn(f"{language} - ", before)

    def test_the_example_is_english_printable_ascii(self):
        for number, line in enumerate(self.text().splitlines(), 1):
            with self.subTest(line=number):
                self.assertTrue(line == "" or PRINTABLE_ASCII.fullmatch(line), line)


if __name__ == "__main__":
    unittest.main()
