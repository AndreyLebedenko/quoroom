import unittest

from nio import RoomMessageText

from coordination.transport import incoming


class TransportTests(unittest.TestCase):
    def event(self, body, extra=None):
        content = {"msgtype": "m.text", "body": body}
        content.update(extra or {})
        return RoomMessageText.from_dict(
            {
                "type": "m.room.message",
                "sender": "@human:local",
                "event_id": "$one",
                "origin_server_ts": 1,
                "content": content,
            }
        )

    def test_thread_and_reply_fallback(self):
        event = self.event(
            "> <@other:local> quoted request\n\nactual reply",
            {"m.relates_to": {"rel_type": "m.thread", "event_id": "$root"}},
        )
        result = incoming("!general", event)
        self.assertEqual((result.body, result.thread), ("actual reply", "$root"))

    def test_service_notices_never_start_more_jobs(self):
        self.assertIsNone(
            incoming(
                "!general", self.event("@codex ping", {"com.agentschat.notice": True})
            )
        )
