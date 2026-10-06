"""Task english-release-05: broker startup, English logs and coded store errors."""

import ast
import contextlib
import io
import re
import socket
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from sessionchat import broker as broker_module
from sessionchat import store as store_module
from sessionchat.broker import (
    BROKER_CATALOGUE,
    Broker,
    StartRefused,
    build_parser,
    configured_path,
    only_agents,
    run,
    startup_language,
)
from sessionchat.i18n import DEFAULT_LANGUAGE, LANGUAGES
from sessionchat.protocol import STALE_SECONDS
from sessionchat.store import (
    STORE_ERROR_CODES,
    DuplicateAgent,
    StoreError,
    StoreOpenError,
    StoreSchemaTooNew,
    UnknownRegistration,
    UnknownSubscription,
    add_subscription,
    insert_registration,
    open_read_only,
    open_store,
    record_ack,
    update_registration,
)
from tests.catalogue_contract import CYRILLIC
from tests.test_sessionchat import CONFIG as RUSSIAN_CONFIG

BROKER_SOURCE = Path(broker_module.__file__)
STORE_SOURCE = Path(store_module.__file__)
AGENT = "claude-code"
LABEL = "refactoring"
PORT = 18770
SQLITE_DETAIL = "file is not a database"
STORE_PATH = "/state/agentschat.db"
RECOVERY = {
    "ru": "удалите файл и заново выполните /chatlogin в каждой сессии",
    "en": "delete the file and run /chatlogin again in every session",
}


def configured(language: str | None, **values) -> dict:
    base = {key: value for key, value in RUSSIAN_CONFIG.items() if key != "language"}
    if language is not None:
        base["language"] = language
    return {**base, **values}


def write_config(directory: str, config: dict) -> Path:
    path = Path(directory) / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def normalised(text: str) -> str:
    return " ".join(text.split())


class TemporaryStoreTestCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = directory.name
        self.path = Path(directory.name) / "state" / "agentschat.db"
        patcher = patch.object(broker_module, "REGISTRATIONS_DB", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def corrupt_store(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"not a database at all" * 100)


class StoreErrorCodeTests(TemporaryStoreTestCase):
    def raised(self, operation) -> StoreError:
        with self.assertRaises(StoreError) as raised:
            operation()
        return raised.exception

    def make_store(self) -> None:
        with open_store(self.path):
            pass

    def set_meta_version(self, value: str) -> None:
        self.make_store()
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                "UPDATE meta SET value = ? WHERE key = 'schema_version'", (value,)
            )
        connection.close()

    def trigger(self, code: str) -> StoreError:
        def missing_file():
            with open_read_only(self.path):
                pass

        def open_it():
            with open_store(self.path):
                pass

        def corrupted():
            self.corrupt_store()
            open_it()

        def bad_version():
            self.set_meta_version("abc")
            open_it()

        def too_new():
            self.set_meta_version("99")
            open_it()

        def duplicate():
            with open_store(self.path) as store:
                insert_registration(store, AGENT, LABEL, "t", 1.0)
                insert_registration(store, AGENT, LABEL, "t", 1.0)

        def unknown_registration():
            with open_store(self.path) as store:
                update_registration(store, AGENT, label=LABEL)

        def unknown_subscription():
            with open_store(self.path) as store:
                record_ack(store, AGENT, "@room", "$e", 1.0)

        def orphan_subscription():
            with open_store(self.path) as store:
                add_subscription(store, AGENT, "@room", 1.0, "$seed")

        scenarios = {
            "missing_file": missing_file,
            "corrupted": corrupted,
            "bad_schema_version": bad_version,
            "schema_too_new": too_new,
            "duplicate_agent": duplicate,
            "unknown_registration": unknown_registration,
            "unknown_subscription": unknown_subscription,
            "subscription_without_registration": orphan_subscription,
        }
        self.assertEqual(set(scenarios), set(STORE_ERROR_CODES))
        return self.raised(scenarios[code])

    def test_every_raise_site_carries_its_code(self):
        for code in STORE_ERROR_CODES:
            with self.subTest(code=code):
                self.path.unlink(missing_ok=True)
                self.assertEqual(self.trigger(code).code, code)

    def test_each_error_carries_the_parameters_its_sentence_needs(self):
        expected = {
            "missing_file": {"path"},
            "corrupted": {"path", "error"},
            "bad_schema_version": {"path", "value"},
            "schema_too_new": {"path", "version", "supported"},
            "duplicate_agent": {"agent"},
            "unknown_registration": {"agent"},
            "unknown_subscription": {"agent", "topic"},
            "subscription_without_registration": {"agent", "topic", "error"},
        }
        for code, names in expected.items():
            with self.subTest(code=code):
                self.path.unlink(missing_ok=True)
                self.assertEqual(set(self.trigger(code).params), names)

    def test_the_text_of_an_error_is_an_english_sentence_for_the_developer(self):
        for code in STORE_ERROR_CODES:
            with self.subTest(code=code):
                self.path.unlink(missing_ok=True)
                text = str(self.trigger(code))
                self.assertTrue(text.isascii(), text)
                self.assertIsNone(CYRILLIC.search(text))

    def test_the_text_of_a_file_error_names_the_file_and_the_way_out(self):
        for code in ("missing_file", "corrupted", "bad_schema_version"):
            with self.subTest(code=code):
                self.path.unlink(missing_ok=True)
                text = str(self.trigger(code))
                self.assertIn(str(self.path), text)
                self.assertIn("/chatlogin", text)

    def test_the_classes_callers_catch_keep_their_codes(self):
        for error_class, code in (
            (DuplicateAgent, "duplicate_agent"),
            (UnknownRegistration, "unknown_registration"),
            (UnknownSubscription, "unknown_subscription"),
            (StoreSchemaTooNew, "schema_too_new"),
        ):
            with self.subTest(error_class=error_class):
                self.path.unlink(missing_ok=True)
                error = self.trigger(code)
                self.assertIsInstance(error, error_class)
        self.path.unlink(missing_ok=True)
        self.assertIsInstance(self.trigger("corrupted"), StoreOpenError)

    def test_an_error_built_with_an_explicit_code_uses_it(self):
        error = StoreError("duplicate_agent", agent="x")
        self.assertEqual(error.code, "duplicate_agent")
        self.assertEqual(error.params, {"agent": "x"})
        self.assertIn("x", str(error))

    def test_an_unknown_code_is_a_programming_error(self):
        with self.assertRaises(KeyError):
            StoreError("no_such_code")


class StoreModuleSourceTests(unittest.TestCase):
    def test_the_store_has_no_cyrillic_anywhere(self):
        text = STORE_SOURCE.read_text(encoding="utf-8")
        self.assertEqual(CYRILLIC.findall(text), [])

    def test_the_store_imports_neither_the_broker_nor_the_catalogue(self):
        imported = []
        for node in ast.walk(ast.parse(STORE_SOURCE.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                imported.append(f"{'.' * node.level}{node.module or ''}")
            elif isinstance(node, ast.Import):
                imported += [alias.name for alias in node.names]
        offenders = [
            name for name in imported if re.search(r"broker|i18n|sessionchat", name)
        ]
        self.assertEqual(offenders, [])


class StoreMessageCases:
    PARAMS = {
        "missing_file": {"path": STORE_PATH},
        "corrupted": {"path": STORE_PATH, "error": SQLITE_DETAIL},
        "bad_schema_version": {"path": STORE_PATH, "value": "abc"},
        "schema_too_new": {"path": STORE_PATH, "version": 99, "supported": 1},
        "duplicate_agent": {"agent": AGENT},
        "unknown_registration": {"agent": AGENT},
        "unknown_subscription": {"agent": AGENT, "topic": "@room"},
        "subscription_without_registration": {
            "agent": AGENT,
            "topic": "@room",
            "error": "FOREIGN KEY constraint failed",
        },
    }
    RUSSIAN = {
        "missing_file": f"{STORE_PATH}: файла нет; {RECOVERY['ru']}.",
        "corrupted": (
            f"{STORE_PATH}: файл повреждён или не является базой ({SQLITE_DETAIL}). "
            f"{RECOVERY['ru']}."
        ),
        "bad_schema_version": (
            f"{STORE_PATH}: в meta лежит не версия: 'abc'. {RECOVERY['ru']}."
        ),
        "schema_too_new": (
            f"{STORE_PATH}: схема версии 99 новее, чем знает код (1); читать её нельзя"
        ),
        "duplicate_agent": (
            "агент claude-code уже имеет регистрацию; перезапись запрещена"
        ),
        "unknown_registration": "регистрации claude-code нет, обновлять нечего",
        "unknown_subscription": (
            "подписка claude-code на @room не существует, подтверждать нечего"
        ),
        "subscription_without_registration": (
            "подписка claude-code на @room невозможна: нет регистрации "
            "(FOREIGN KEY constraint failed)"
        ),
    }
    ENGLISH = {
        "missing_file": f"{STORE_PATH}: the file does not exist; {RECOVERY['en']}.",
        "corrupted": (
            f"{STORE_PATH}: the file is damaged or is not a database "
            f"({SQLITE_DETAIL}); {RECOVERY['en']}."
        ),
        "bad_schema_version": (
            f"{STORE_PATH}: the meta table holds a value that is not a version: "
            f"'abc'; {RECOVERY['en']}."
        ),
        "schema_too_new": (
            f"{STORE_PATH}: schema version 99 is newer than the code supports "
            "(1); it cannot be read."
        ),
        "duplicate_agent": (
            "Agent claude-code already has a registration; overwriting is refused."
        ),
        "unknown_registration": (
            "There is no registration for claude-code; nothing to update."
        ),
        "unknown_subscription": (
            "There is no subscription of claude-code to @room; nothing to acknowledge."
        ),
        "subscription_without_registration": (
            "A subscription of claude-code to @room is impossible: the agent has "
            "no registration (FOREIGN KEY constraint failed)."
        ),
    }
    EXPECTED = {"ru": RUSSIAN, "en": ENGLISH}


class StoreMessageTests(StoreMessageCases, unittest.TestCase):
    def broker(self, language: str) -> Broker:
        return Broker(configured(language), Path(STORE_PATH))

    def test_the_cases_cover_every_code(self):
        self.assertEqual(set(self.PARAMS), set(STORE_ERROR_CODES))

    def test_every_code_renders_under_both_languages(self):
        for language in LANGUAGES:
            broker = self.broker(language)
            for code in STORE_ERROR_CODES:
                with self.subTest(language=language, code=code):
                    error = StoreError(code, **self.PARAMS[code])
                    self.assertEqual(
                        self.EXPECTED[language][code], broker.store_message(error)
                    )

    def test_the_english_texts_have_no_cyrillic(self):
        broker = self.broker("en")
        for code in STORE_ERROR_CODES:
            with self.subTest(code=code):
                text = broker.store_message(StoreError(code, **self.PARAMS[code]))
                self.assertIsNone(CYRILLIC.search(text))

    def test_the_catalogue_has_one_store_key_per_code_and_nothing_else(self):
        keys = {
            key.removeprefix("broker.store_")
            for key in BROKER_CATALOGUE.templates("en")
            if key.startswith("broker.store_")
        }
        self.assertEqual(keys, set(STORE_ERROR_CODES))

    def test_the_text_does_not_depend_on_the_developer_sentence(self):
        broker = self.broker("ru")
        error = StoreError("duplicate_agent", agent=AGENT)
        self.assertNotIn(str(error), broker.store_message(error))


class StoreFailureAtStartTests(TemporaryStoreTestCase):
    def refusal_for(self, language: str) -> tuple[StartRefused, str]:
        self.corrupt_store()
        with self.assertRaises(StartRefused) as raised:
            Broker(configured(language), self.path)
        return raised.exception, raised.exception.__cause__.params["error"]

    def test_a_damaged_store_refuses_the_start_in_the_room_language(self):
        refusal, detail = self.refusal_for("ru")
        self.assertEqual(
            f"{self.path}: файл повреждён или не является базой ({detail}). "
            f"{RECOVERY['ru']}.",
            str(refusal),
        )

    def test_a_damaged_store_refuses_the_start_in_english_by_default(self):
        for language in ("en", None):
            with self.subTest(language=language):
                self.corrupt_store()
                with self.assertRaises(StartRefused) as raised:
                    Broker(configured(language), self.path)
                detail = raised.exception.__cause__.params["error"]
                self.assertEqual(
                    f"{self.path}: the file is damaged or is not a database "
                    f"({detail}); {RECOVERY['en']}.",
                    str(raised.exception),
                )

    def test_the_refusal_is_a_value_error_so_the_start_ends_without_a_traceback(self):
        refusal, _ = self.refusal_for("en")
        self.assertIsInstance(refusal, ValueError)

    def test_main_prints_the_prefixed_refusal_in_each_language(self):
        prefix = {"ru": "БРОКЕР НЕ ЗАПУЩЕН: ", "en": "BROKER NOT STARTED: "}
        for language in LANGUAGES:
            with self.subTest(language=language):
                refusal, _ = self.refusal_for(language)
                config = write_config(self.directory, configured(language))
                with patch("sys.argv", ["broker", "--config", str(config)]):
                    with self.assertRaises(SystemExit) as raised:
                        broker_module.main()
                self.assertEqual(prefix[language] + str(refusal), raised.exception.code)


class StartupRefusalCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = directory.name
        patcher = patch.object(
            broker_module, "REGISTRATIONS_DB", Path(directory.name) / "none.db"
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        joiner = patch.object(Broker, "join_all", AsyncMock())
        joiner.start()
        self.addCleanup(joiner.stop)

    def config(self, language: str | None, **values) -> Path:
        return write_config(self.directory, configured(language, **values))


class PortInUseTests(StartupRefusalCase):
    EXPECTED = {
        "ru": (
            f"БРОКЕР НЕ ЗАПУЩЕН: порт {PORT} занят (Address already in use).\n"
            "Скорее всего, брокер уже работает в другом окне. Проверьте: "
            f"curl http://127.0.0.1:{PORT}/status — и остановите прежний, "
            "если хотите запустить этот с другими ключами."
        ),
        "en": (
            f"BROKER NOT STARTED: Port {PORT} is already in use "
            "(Address already in use).\n"
            "Most likely the broker is already running in another window. "
            f"Check with: curl http://127.0.0.1:{PORT}/status - and stop the "
            "previous one if you want to start this one with different keys."
        ),
    }

    async def refused(self, config: Path) -> str:
        busy = OSError(98, "Address already in use")
        with patch.object(web.TCPSite, "start", AsyncMock(side_effect=busy)):
            with self.assertRaises(SystemExit) as raised:
                await run(config)
        return raised.exception.code

    async def test_a_taken_port_is_refused_in_the_room_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                text = await self.refused(self.config(language))
                self.assertEqual(self.EXPECTED[language], text)

    async def test_a_taken_port_is_refused_in_english_when_no_language_is_set(self):
        self.assertEqual(self.EXPECTED["en"], await self.refused(self.config(None)))

    async def test_the_english_refusal_has_no_cyrillic(self):
        text = await self.refused(self.config("en"))
        self.assertIsNone(CYRILLIC.search(text))
        self.assertTrue(text.isascii())

    async def test_a_port_really_held_by_another_listener_is_refused(self):
        with socket.socket() as holder:
            holder.bind(("127.0.0.1", 0))
            holder.listen()
            port = holder.getsockname()[1]
            config = self.config("en", sessionchat_port=port)
            with self.assertRaises(SystemExit) as raised:
                await run(config)
        text = raised.exception.code
        self.assertTrue(text.startswith(f"BROKER NOT STARTED: Port {port} is already"))
        self.assertIn(f"curl http://127.0.0.1:{port}/status", text)

    async def test_the_hint_names_the_url_that_answers_json_about_the_room(self):
        self.assertIn("/status", self.EXPECTED["en"])
        broker = Broker(configured("en"), Path(self.directory) / "none.db")
        self.addAsyncCleanup(self.close_matrix_clients, broker)
        client = TestClient(TestServer(broker.app()))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        response = await client.get("/status")
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["language"], "en")

    async def close_matrix_clients(self, broker: Broker) -> None:
        for client in broker.clients.values():
            await client.close()


class AgentSelectionRefusalTests(TemporaryStoreTestCase):
    def test_unknown_agents_are_refused_in_each_language(self):
        expected = {
            "ru": "нет таких агентов в конфиге: codex, opencode2",
            "en": "No such agents in the config: codex, opencode2",
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                with self.assertRaises(StartRefused) as raised:
                    only_agents(configured(language), "claude-code,codex,opencode2")
                self.assertEqual(expected[language], str(raised.exception))

    def test_the_default_language_is_english(self):
        with self.assertRaises(StartRefused) as raised:
            only_agents(configured(None), "nobody")
        self.assertEqual("No such agents in the config: nobody", str(raised.exception))

    def test_main_prefixes_the_refusal_in_the_room_language(self):
        expected = {
            "ru": "БРОКЕР НЕ ЗАПУЩЕН: нет таких агентов в конфиге: nobody",
            "en": "BROKER NOT STARTED: No such agents in the config: nobody",
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                config = write_config(self.directory, configured(language))
                argv = ["broker", "--config", str(config), "--agents", "nobody"]
                with patch("sys.argv", argv):
                    with self.assertRaises(SystemExit) as raised:
                        broker_module.main()
                self.assertEqual(expected[language], raised.exception.code)


class JoinAndPublishFailureTests(unittest.IsolatedAsyncioTestCase):
    async def broker(self, language: str) -> Broker:
        broker = Broker(configured(language), Path("/none/agentschat.db"))
        self.addAsyncCleanup(self.close_matrix_clients, broker)
        return broker

    async def close_matrix_clients(self, broker: Broker) -> None:
        for client in broker.clients.values():
            await client.close()

    async def test_a_failed_join_is_reported_in_the_room_language(self):
        expected = {
            "ru": f"{AGENT}: не удалось войти в !room:local: boom",
            "en": f"{AGENT}: could not join !room:local: boom",
        }
        for language in LANGUAGES:
            with self.subTest(language=language):
                broker = await self.broker(language)
                broker.clients[AGENT]._send = AsyncMock(return_value="boom")
                with self.assertRaises(RuntimeError) as raised:
                    await broker.join_all()
                self.assertEqual(expected[language], str(raised.exception))

    async def test_a_failed_publish_is_an_english_developer_error_in_every_room(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                broker = await self.broker(language)
                broker.clients[AGENT].room_send = AsyncMock(return_value="boom")
                with self.assertRaises(RuntimeError) as raised:
                    await broker.publish(AGENT, "text", 0)
                self.assertEqual("publishing failed: boom", str(raised.exception))


class StartupLanguageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def file(self, content: bytes) -> Path:
        path = self.directory / "config.yaml"
        path.write_bytes(content)
        return path

    def test_a_readable_config_gives_its_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                config = write_config(str(self.directory), configured(language))
                self.assertEqual(language, startup_language(config))

    def test_a_config_without_the_key_gives_the_default(self):
        config = write_config(str(self.directory), configured(None))
        self.assertEqual(DEFAULT_LANGUAGE, startup_language(config))

    def test_a_config_that_cannot_be_used_gives_english(self):
        unusable = {
            "missing file": self.directory / "nothing.yaml",
            "not yaml": self.file(b"a: [unclosed"),
            "not utf-8": self.file(b"\xff\xfe\x00bad"),
            "empty": self.file(b""),
            "a list": self.file(b"- ru\n- en\n"),
            "bad language": self.file(b"language: fr\n"),
            "non-text language": self.file(b"language: 5\n"),
        }
        for name, path in unusable.items():
            with self.subTest(name=name):
                self.assertEqual("en", startup_language(path))

    def test_the_config_path_is_found_before_the_full_parse(self):
        self.assertEqual(
            Path("/x/c.yaml").resolve(), configured_path(["--config", "/x/c.yaml"])
        )
        self.assertEqual(
            Path("/x/c.yaml").resolve(),
            configured_path(["--agents", "a", "--config=/x/c.yaml", "--verbose"]),
        )
        self.assertEqual(Path("config.yaml").resolve(), configured_path([]))

    def test_the_config_path_search_ignores_the_help_flag(self):
        self.assertEqual(Path("config.yaml").resolve(), configured_path(["--help"]))


class ArgumentHelpTests(unittest.TestCase):
    AGENTS_HELP = {
        "ru": "обслуживать только этих агентов, через запятую (по умолчанию всех)",
        "en": "serve only these agents, comma-separated (all by default)",
    }

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = directory.name

    def help_of_main(self, *arguments: str) -> str:
        output = io.StringIO()
        with patch("sys.argv", ["broker", *arguments, "--help"]):
            with contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as raised:
                    broker_module.main()
        self.assertEqual(0, raised.exception.code)
        return normalised(output.getvalue())

    def test_the_parser_help_is_in_the_given_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                text = normalised(build_parser(language).format_help())
                self.assertIn(self.AGENTS_HELP[language], text)
                self.assertIn("Quoroom session broker", text)

    def test_the_english_help_has_no_cyrillic(self):
        self.assertIsNone(CYRILLIC.search(build_parser("en").format_help()))

    def test_the_help_of_main_follows_the_language_of_a_readable_config(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                config = write_config(self.directory, configured(language))
                text = self.help_of_main("--config", str(config))
                self.assertIn(self.AGENTS_HELP[language], text)

    def test_the_help_of_main_is_english_when_the_config_cannot_be_read(self):
        text = self.help_of_main("--config", str(Path(self.directory) / "none.yaml"))
        self.assertIn(self.AGENTS_HELP["en"], text)

    def test_the_help_of_main_is_english_when_the_language_is_refused(self):
        config = write_config(self.directory, configured("fr"))
        self.assertIn(
            self.AGENTS_HELP["en"], self.help_of_main("--config", str(config))
        )

    def test_the_help_of_main_is_english_when_no_language_is_configured(self):
        config = write_config(self.directory, configured(None))
        self.assertIn(
            self.AGENTS_HELP["en"], self.help_of_main("--config", str(config))
        )


class LogLineTests(unittest.IsolatedAsyncioTestCase):
    async def serve(self) -> tuple[TestClient, Broker]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        broker = Broker(
            configured("ru"), Path(directory.name) / "state" / "agentschat.db"
        )
        client = TestClient(TestServer(broker.app()))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        self.addAsyncCleanup(self.close_matrix_clients, broker)
        return client, broker

    async def close_matrix_clients(self, broker: Broker) -> None:
        for client in broker.clients.values():
            await client.close()

    async def login(self, client: TestClient, **fields):
        return await client.post(
            "/login", json={"agent": AGENT, "label": LABEL, **fields}
        )

    async def test_the_session_lifecycle_is_logged_in_english_under_a_russian_room(
        self,
    ):
        client, broker = await self.serve()
        with self.assertLogs("agentschat.broker", level="INFO") as logged:
            first = await (await self.login(client)).json()
            await self.login(client, reconnect=True, token=first["token"])
            await client.post("/logout", json={"agent": AGENT, "token": first["token"]})
            await self.login(client)
            broker.registrations[AGENT].registered_at -= STALE_SECONDS + 100
            await self.login(client)
        messages = [record.getMessage() for record in logged.records]
        self.assertEqual(
            [
                f"session {AGENT} connected ({LABEL})",
                f"reattached to the registration of {AGENT} ({LABEL})",
                f"session {AGENT} disconnected",
                f"session {AGENT} connected ({LABEL})",
            ],
            messages[:4],
        )
        self.assertRegex(
            messages[4],
            rf"^slot {AGENT} freed: the previous session was silent for \d+s "
            rf"\({LABEL}\)$",
        )
        self.assertEqual(f"session {AGENT} connected ({LABEL})", messages[5])

    async def test_no_record_of_the_session_lifecycle_contains_cyrillic(self):
        client, broker = await self.serve()
        with self.assertLogs("agentschat.broker", level="INFO") as logged:
            first = await (await self.login(client)).json()
            await self.login(client, reconnect=True, token=first["token"])
            await client.post("/logout", json={"agent": AGENT, "force": True})
            await self.login(client)
            broker.registrations[AGENT].registered_at = time.time() - 10_000
            await self.login(client)
        for record in logged.records:
            with self.subTest(message=record.getMessage()):
                self.assertTrue(record.getMessage().isascii())

    async def test_the_ready_line_is_english_and_names_the_room_and_the_port(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        config = write_config(directory.name, configured("ru", sessionchat_port=0))
        with (
            patch.object(
                broker_module, "REGISTRATIONS_DB", Path(directory.name) / "none.db"
            ),
            patch.object(Broker, "join_all", AsyncMock()),
            patch.object(Broker, "sync_forever", AsyncMock()),
            self.assertLogs("agentschat.broker", level="INFO") as logged,
        ):
            await run(config)
        self.assertEqual(
            ["BROKER READY room=!room:local port=0"],
            [record.getMessage() for record in logged.records],
        )

    def test_the_stop_line_is_english(self):
        with (
            patch.object(broker_module, "run", lambda *arguments: None),
            patch.object(broker_module.asyncio, "run", side_effect=KeyboardInterrupt),
            patch("sys.argv", ["broker", "--config", "none.yaml"]),
            self.assertLogs("agentschat.broker", level="INFO") as logged,
        ):
            broker_module.main()
        self.assertEqual(
            ["broker stopped"], [record.getMessage() for record in logged.records]
        )


class BrokerSourceScanTests(unittest.TestCase):
    def docstring_nodes(self, tree: ast.AST) -> set[int]:
        nodes = set()
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                first = node.body[0] if node.body else None
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    nodes.add(id(first.value))
        return nodes

    def test_no_string_literal_of_the_broker_is_russian_outside_docstrings(self):
        tree = ast.parse(BROKER_SOURCE.read_text(encoding="utf-8"))
        docstrings = self.docstring_nodes(tree)
        offenders = [
            repr(node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and CYRILLIC.search(node.value)
            and id(node) not in docstrings
        ]
        self.assertEqual(offenders, [])

    def test_every_exit_message_of_the_broker_comes_from_the_catalogue(self):
        tree = ast.parse(BROKER_SOURCE.read_text(encoding="utf-8"))
        exits = [
            call
            for call in ast.walk(tree)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "SystemExit"
        ]
        for call in exits:
            with self.subTest(line=call.lineno):
                literals = [
                    node.value
                    for node in ast.walk(call)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                ]
                self.assertTrue(
                    all(literal in {"start_refused"} for literal in literals),
                    literals,
                )


if __name__ == "__main__":
    unittest.main()
