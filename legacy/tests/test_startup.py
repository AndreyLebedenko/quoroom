import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from nio import RoomGetStateEventError, RoomGetStateEventResponse

from matrix_bridge import AgentBridge


class StartupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bridge = AgentBridge(
            "https://example.invalid",
            True,
            "!general",
            "test",
            {
                "user_id": "@test:example.invalid",
                "access_token": "test-token",
                "workdir": ".",
                "command": ["test-cli", "{prompt}"],
            },
        )
        self.bridge.client = AsyncMock()
        self.bridge.client.add_event_callback = unittest.mock.Mock()
        self.bridge._join_room = AsyncMock(return_value="!general")

    async def test_normal_room_starts_sync(self):
        self.bridge.client.room_get_state_event.return_value = (
            RoomGetStateEventResponse(
                {"room_version": "12"}, "m.room.create", "", "!general"
            )
        )
        await self.bridge.run()
        self.bridge.client.sync_forever.assert_awaited_once_with(
            timeout=30000, full_state=True
        )

    async def test_space_is_rejected_before_sync(self):
        self.bridge.client.room_get_state_event.return_value = (
            RoomGetStateEventResponse(
                {"type": "m.space"}, "m.room.create", "", "!general"
            )
        )
        with self.assertRaisesRegex(RuntimeError, "пространство"):
            await self.bridge.run()
        self.bridge.client.sync_forever.assert_not_awaited()

    async def test_unreadable_room_state_is_reported(self):
        self.bridge.client.room_get_state_event.return_value = RoomGetStateEventError(
            "Forbidden", "M_FORBIDDEN"
        )
        with self.assertRaisesRegex(RuntimeError, "тип комнаты"):
            await self.bridge.run()
        self.bridge.client.sync_forever.assert_not_awaited()

    async def test_failed_join_does_not_start_sync(self):
        self.bridge._join_room.return_value = None
        await self.bridge.run()
        self.bridge.client.room_get_state_event.assert_not_awaited()
        self.bridge.client.sync_forever.assert_not_awaited()

    async def test_cli_has_no_interactive_stdin(self):
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (b"OK", b"")
        with patch(
            "matrix_bridge.asyncio.create_subprocess_exec", return_value=process
        ) as spawn:
            self.assertEqual(await self.bridge._run_cli("hello"), "OK")
        self.assertEqual(
            spawn.call_args.kwargs.get("stdin"), asyncio.subprocess.DEVNULL
        )


if __name__ == "__main__":
    unittest.main()
