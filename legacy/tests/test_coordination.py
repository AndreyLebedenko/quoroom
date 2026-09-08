import tempfile
import unittest
from pathlib import Path

from coordination.artifacts import Artifacts
from coordination.model import Outcome, parse_outcome
from coordination.store import Store


class ProtocolTests(unittest.TestCase):
    def test_report_requires_short_summary_and_full_details(self):
        result = parse_outcome(
            '{"action":"reply","summary":"Готово","details":"Evidence","to":[]}',
            {"codex"},
        )
        self.assertEqual(result, Outcome("reply", "Готово", "Evidence", ()))

    def test_invalid_output_cannot_trigger_work(self):
        for value in (
            "{}",
            "[]",
            '{"action":"run"}',
            '{"action":"request","summary":"x","details":"y","to":["unknown"]}',
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_outcome(value, {"codex"})


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state.sqlite")
        self.addCleanup(self.store.close)

    def test_duplicate_input_is_recorded_once(self):
        self.assertTrue(self.store.accept_event("$one"))
        self.assertFalse(self.store.accept_event("$one"))

    def test_cursor_survives_restart(self):
        self.store.set_meta("sync", "batch-12")
        other = Store(self.root / "state.sqlite")
        self.addCleanup(other.close)
        self.assertEqual(other.get_meta("sync"), "batch-12")

    def test_report_is_immutable_and_idempotent(self):
        artifacts = Artifacts(self.root)
        path = artifacts.record("example", "report-1", "Evidence")
        self.assertEqual(artifacts.record("example", "report-1", "Evidence"), path)
        with self.assertRaises(ValueError):
            artifacts.record("example", "report-1", "Changed")
        self.assertEqual(path.read_text(encoding="utf-8"), "Evidence")

    def test_artifact_cannot_escape_project(self):
        with self.assertRaises(ValueError):
            Artifacts(self.root).record("../../escape", "report-1", "x")
