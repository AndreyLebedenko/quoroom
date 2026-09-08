"""Live checks: set AGENTSCHAT_LIVE=1 after starting the configured bridges.

These tests send one short request per agent to the configured Matrix room.
"""

import asyncio
import os
import time
import unittest
import uuid
from pathlib import Path

from nio import RoomMessageText, RoomSendResponse, SyncResponse

from matrix_bridge import AgentBridge, load_config


@unittest.skipUnless(os.environ.get("AGENTSCHAT_LIVE") == "1", "live checks disabled")
class LiveBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cfg = load_config(str(Path(__file__).resolve().parents[1] / "config.yaml"))
        self.observer = self.make_bridge("codex")
        self.sender = self.make_bridge("opencode")
        self.received: list[tuple[str, str, str]] = []
        self.observer.client.add_event_callback(self.on_message, RoomMessageText)
        response = await self.observer.client.sync(timeout=0, full_state=True)
        self.assertIsInstance(response, SyncResponse)
        self.received.clear()

    def make_bridge(self, name: str) -> AgentBridge:
        return AgentBridge(
            self.cfg["homeserver_url"],
            self.cfg.get("verify_ssl", True),
            self.cfg["room_id"],
            name,
            self.cfg["agents"][name],
        )

    async def asyncTearDown(self):
        await self.observer.client.close()
        await self.sender.client.close()

    async def on_message(self, room, event: RoomMessageText):
        if room.room_id == self.cfg["room_id"]:
            self.received.append((event.sender, event.event_id, event.body))

    async def check_reply(self, agent: str):
        marker = "ACHECK_" + uuid.uuid4().hex[:12]
        target = self.cfg["agents"][agent]["user_id"]
        # Send from a different bot: each production bridge ignores its own messages.
        client = self.observer.client if agent == "opencode" else self.sender.client
        sent = await client.room_send(
            self.cfg["room_id"],
            "m.room.message",
            {
                "msgtype": "m.text",
                "body": f"{target} Проверка моста. Ответь ровно {marker}. Не используй инструменты.",
                "m.mentions": {"user_ids": [target]},
            },
        )
        self.assertIsInstance(sent, RoomSendResponse)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            response = await asyncio.wait_for(
                self.observer.client.sync(timeout=1000, full_state=True), 15
            )
            self.assertIsInstance(response, SyncResponse)
            if any(
                sender == target and body.strip() == marker
                for sender, _, body in self.received
            ):
                self.assertTrue(
                    any(event_id == sent.event_id for _, event_id, _ in self.received)
                )
                return
        self.fail(f"No reply from {agent}: {self.received}")

    async def test_claude_code(self):
        await self.check_reply("claude-code")

    async def test_codex(self):
        await self.check_reply("codex")

    async def test_opencode(self):
        await self.check_reply("opencode")


if __name__ == "__main__":
    unittest.main()
