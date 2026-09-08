import tempfile
import unittest
from pathlib import Path

from coordination.artifacts import Artifacts
from coordination.engine import Engine
from coordination.model import Incoming, RunResult
from coordination.store import Store


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.action = "reply"
        self.to = []

    async def run(self, project, prompt, session):
        import json

        self.calls.append((project, prompt, session))
        return RunResult(
            session or "session-1",
            json.dumps(
                {
                    "action": self.action,
                    "summary": "Short",
                    "details": "Full evidence",
                    "to": self.to,
                }
            ),
        )


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_discussion_has_protocol_metadata_before_worker_runs(self):
        self.request()
        await self.engine.process("codex")
        path = self.root / ".agent-comms/active/ac-task/README.md"
        self.assertIn("Coordinator: codex", path.read_text(encoding="utf-8"))

    async def test_new_round_resets_request_budget(self):
        self.request()
        self.store.db.execute("UPDATE topics SET requests=12 WHERE id='task'")
        self.runner.action, self.runner.to = "revise", ["claude-code"]
        await self.engine.process("codex")
        self.assertIsNotNone(self.store.claim("claude-code"))

    def test_late_result_cannot_dispatch_plan_superseded_by_human(self):
        from coordination.model import Outcome

        self.request()
        old_job = self.store.claim("codex")
        with self.store.atomic():
            self.engine.block(old_job, "Choose A or B", "test")
        issue = self.store.db.execute("SELECT id FROM issues").fetchone()[0]
        self.engine.ingest(
            Incoming(
                "$decision",
                "!escalations",
                "@human:local",
                f"/answer {issue} Do B only",
            )
        )
        self.engine.reconcile_answers()
        self.engine.route(
            old_job, Outcome("request", "Do A", "Old plan", ("claude-code",))
        )
        self.assertIsNone(self.store.claim("claude-code"))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state.sqlite")
        self.addCleanup(self.store.close)
        self.runner = FakeRunner()
        self.engine = Engine(
            self.store,
            Artifacts(self.root),
            {"codex": self.runner, "claude-code": self.runner},
            "!general",
            "!escalations",
            {"@human:local"},
        )

    def request(self, event="$one", body="/topic task @codex implement"):
        self.engine.ingest(Incoming(event, "!general", "@human:local", body))

    async def test_same_matrix_event_runs_only_once(self):
        self.request()
        self.request()
        self.assertTrue(await self.engine.process("codex"))
        self.assertFalse(await self.engine.process("codex"))
        self.assertEqual(len(self.runner.calls), 1)

    async def test_next_message_resumes_same_discussion(self):
        self.request()
        await self.engine.process("codex")
        self.request("$two", "/topic task @codex continue")
        await self.engine.process("codex")
        self.assertEqual(self.runner.calls[1][2], "session-1")

    async def test_peer_request_and_reply_are_delivered_without_human_relay(self):
        self.runner.action, self.runner.to = "request", ["claude-code"]
        self.request()
        await self.engine.process("codex")
        self.runner.action, self.runner.to = "reply", []
        self.assertTrue(await self.engine.process("claude-code"))
        self.assertTrue(await self.engine.process("codex"))

    async def test_escalation_blocks_until_explicit_human_answer(self):
        self.runner.action = "escalate"
        self.request()
        await self.engine.process("codex")
        issue = self.store.db.execute("SELECT id FROM issues").fetchone()[0]
        self.request("$two", "/topic task @codex more work")
        self.assertFalse(await self.engine.process("codex"))
        self.engine.ingest(
            Incoming(
                "$fake", "!escalations", "@codex:local", f"/answer {issue} approved"
            )
        )
        self.assertFalse(await self.engine.process("codex"))
        self.engine.ingest(
            Incoming(
                "$human",
                "!escalations",
                "@human:local",
                f"/answer {issue} Approved scope A",
            )
        )
        self.runner.action = "reply"
        self.assertTrue(await self.engine.process("codex"))
        self.assertTrue(
            any("Approved scope A" in p.read_text() for p in self.root.rglob("*.md"))
        )

    def test_interrupted_job_is_not_replayed_on_restart(self):
        self.request()
        self.assertIsNotNone(self.store.claim("codex"))
        self.engine.recover()
        self.assertIsNone(self.store.claim("codex"))
        self.assertEqual(len(self.store.pending_notices()), 1)

    async def test_outbox_retry_does_not_repeat_cli(self):
        self.request()
        await self.engine.process("codex")
        original = self.store.pending_notices()[0]
        self.assertEqual(self.store.pending_notices()[0].id, original.id)
        self.store.sent(original.id, "$published")
        self.assertEqual(self.store.pending_notices(), [])
        self.assertEqual(len(self.runner.calls), 1)
