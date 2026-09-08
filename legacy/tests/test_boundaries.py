import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml

from coordination.artifacts import Artifacts
from coordination.cli import AgentCLI, parse_result, terminate
from coordination.model import parse_outcome
from coordination.settings import Settings
from coordination.store import Store


class BoundaryTests(unittest.TestCase):
    def test_strict_response_contract(self):
        valid = {"action": "reply", "summary": "s", "details": "d", "to": []}
        for change in (
            {"action": "unknown"},
            {"action": 4},
            {"summary": ""},
            {"summary": "x" * 601},
            {"summary": 4},
            {"details": ""},
            {"details": 4},
            {"details": "x" * 100001},
            {"to": "codex"},
            {"to": [3]},
            {"action": "request", "to": ["codex", "codex"]},
            {"to": ["codex"]},
            {"action": "request"},
        ):
            with self.subTest(change=str(change)[:100]), self.assertRaises(ValueError):
                parse_outcome(json.dumps(valid | change), {"codex"})

    def test_cli_stream_requires_a_complete_success(self):
        for provider, text in [
            ("claude-code", "[]"),
            ("claude-code", '{"is_error":false}'),
            ("codex", '{"type":"turn.failed"}'),
            ("codex", "{}"),
            ("opencode", "{}"),
            ("unknown", "{}"),
        ]:
            with (
                self.subTest(provider=provider, text=text),
                self.assertRaises(ValueError),
            ):
                parse_result(provider, text)
        for provider, text in [
            (
                "codex",
                '\n{"type":"thread.started","thread_id":"s"}\n{"type":"item.completed","item":{}}\n{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n{"type":"turn.completed"}',
            ),
            (
                "opencode",
                '{"type":"start"}\n{"type":"step_start","sessionID":"s","part":{}}\n{"type":"text","sessionID":"s","part":{"text":"ok"}}\n{"type":"step_finish","part":{"reason":"stop"}}',
            ),
        ]:
            self.assertEqual(parse_result(provider, text).text, "ok")

    def test_command_initialization_and_provider_validation(self):
        for provider in ("claude-code", "codex", "opencode"):
            self.assertTrue(AgentCLI(provider, "cli").command(""))
        with self.assertRaises(ValueError):
            AgentCLI("unknown", "cli").command("")

    def test_atomic_state_rolls_back_partial_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "state.sqlite")
            try:
                with self.assertRaises(ValueError), store.atomic():
                    store.accept_event("$one")
                    raise ValueError("abort")
                self.assertTrue(store.accept_event("$one"))
            finally:
                store.close()

    def test_link_resolution_cannot_leave_project(self):
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Artifacts(Path(directory))
            with (
                patch.object(Path, "resolve", return_value=Path(directory).parent),
                self.assertRaises(ValueError),
            ):
                artifacts.directory("topic")


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {
            "accounts_file": "accounts.yaml",
            "project_root": str(self.root),
            "state_file": "state.sqlite",
            "general_room": "!general",
            "escalations_room": "!escalations",
            "human_users": ["@human:local"],
        }
        self.account = {
            "homeserver_url": "https://matrix.invalid",
            "agents": {
                "codex": {
                    "command": [sys.executable],
                    "user_id": "@codex:local",
                    "access_token": "test-token",
                    "device_id": "test-device",
                }
            },
        }

    def load(self, config=None, account=None):
        path = self.root / "config.yaml"
        path.write_text(
            yaml.safe_dump(self.config if config is None else config), encoding="utf-8"
        )
        (self.root / "accounts.yaml").write_text(
            yaml.safe_dump(self.account if account is None else account),
            encoding="utf-8",
        )
        return Settings.load(path)

    def test_valid_config(self):
        self.assertEqual(self.load().project, self.root)

    def test_invalid_config_is_rejected_before_connecting(self):
        for change in (
            {"human_users": []},
            {"human_users": "human"},
            {"human_users": ["@codex:local"]},
            {"records_port": True},
            {"records_port": 1},
            {"general_room": "#alias"},
            {"escalations_room": "!general"},
            {"accounts_file": 0},
            {"agents": []},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.load(self.config | change)
        with self.assertRaises(ValueError):
            self.load([])
        with self.assertRaises(ValueError):
            self.load(account=self.account | {"agents": {}})
        with self.assertRaises(ValueError):
            self.load(account=self.account | {"verify_ssl": 12})
        for command in ([], "cli", ["missing-cli.exe"]):
            account = json.loads(json.dumps(self.account))
            account["agents"]["codex"]["command"] = command
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.load(account=account)
        file = self.root / "a-file"
        file.write_text("x")
        with self.assertRaises(ValueError):
            self.load(self.config | {"project_root": str(file)})


class ProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_process_reads_stdin_and_preserves_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cli = AgentCLI("claude-code", sys.executable)
            code = 'import sys,json; s=sys.stdin.buffer.read().decode("utf-8"); print(json.dumps({"session_id":"s","result":s,"is_error":False}))'
            with patch.object(
                AgentCLI, "command", return_value=[sys.executable, "-c", code]
            ):
                result = await cli.run(root, "unicode: привет", "s")
                self.assertEqual(result.text, "unicode: привет")

    async def test_process_failure_and_wrong_session_surface(self):
        process = AsyncMock()
        process.returncode = 1
        process.communicate.return_value = (b"", b"failed")
        with (
            patch(
                "coordination.cli.asyncio.create_subprocess_exec", return_value=process
            ),
            self.assertRaises(RuntimeError),
        ):
            await AgentCLI("codex", "cli").run(Path.cwd(), "x", "")
        process.returncode = 0
        process.communicate.return_value = (
            b'{"session_id":"different","result":"x","is_error":false}',
            b"",
        )
        with (
            patch(
                "coordination.cli.asyncio.create_subprocess_exec", return_value=process
            ),
            self.assertRaises(ValueError),
        ):
            await AgentCLI("claude-code", "cli").run(Path.cwd(), "x", "expected")

    async def test_timeout_terminates_owned_process(self):
        process = AsyncMock()
        process.communicate.side_effect = asyncio.TimeoutError()
        with (
            patch(
                "coordination.cli.asyncio.create_subprocess_exec", return_value=process
            ),
            patch("coordination.cli.terminate", new_callable=AsyncMock) as stop,
            self.assertRaises(asyncio.TimeoutError),
        ):
            await AgentCLI("codex", "cli").run(Path.cwd(), "x", "")
        stop.assert_awaited_once_with(process)

    async def test_windows_process_tree_cleanup_reports_failure(self):
        process = AsyncMock()
        process.returncode = 0
        await terminate(process)
        process.returncode = None
        process.pid = 123
        killer = AsyncMock()
        killer.returncode = 0
        killer.communicate.return_value = (b"ok", b"")
        with (
            patch("coordination.cli.os.name", "nt"),
            patch(
                "coordination.cli.asyncio.create_subprocess_exec", return_value=killer
            ),
        ):
            await terminate(process)
        killer.returncode = 1
        with (
            patch("coordination.cli.os.name", "nt"),
            patch(
                "coordination.cli.asyncio.create_subprocess_exec", return_value=killer
            ),
            self.assertRaises(RuntimeError),
        ):
            await terminate(process)

    async def test_posix_tree_cleanup(self):
        process = AsyncMock()
        process.returncode = None
        process.pid = 123
        with (
            patch("coordination.cli.os.name", "posix"),
            patch("coordination.cli.os.killpg", create=True) as kill,
            patch("coordination.cli.signal.SIGKILL", 9, create=True),
        ):
            await terminate(process)
        kill.assert_called_once()
