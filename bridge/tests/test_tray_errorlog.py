"""Task tray-03: the failure log."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from quoroomtray.errorlog import ErrorLog

NOON = datetime(2026, 11, 23, 12, 0, 0)


class ErrorLogTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "state" / "tray-errors.log"

    def failure(self, text="boom"):
        try:
            raise RuntimeError(text)
        except RuntimeError as failure:
            return failure

    def test_a_failure_is_written_with_its_time_type_and_message(self):
        ErrorLog(self.path, lambda: NOON)(self.failure("probe blew up"))

        written = self.path.read_text(encoding="utf-8")

        self.assertTrue(written.startswith("2026-11-23T12:00:00 "))
        self.assertIn("RuntimeError: probe blew up", written)

    def test_the_traceback_is_written_too(self):
        ErrorLog(self.path, lambda: NOON)(self.failure())

        self.assertIn("Traceback", self.path.read_text(encoding="utf-8"))

    def test_the_log_directory_is_created_on_demand(self):
        ErrorLog(self.path, lambda: NOON)(self.failure())

        self.assertTrue(self.path.parent.is_dir())

    def test_failures_are_appended_not_overwritten(self):
        log = ErrorLog(self.path, lambda: NOON)

        log(self.failure("first"))
        log(self.failure("second"))

        written = self.path.read_text(encoding="utf-8")
        self.assertLess(written.index("first"), written.index("second"))

    def test_a_log_that_cannot_be_written_does_not_raise(self):
        blocker = self.path.parent.parent / "state"
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_text("a file where the directory should be", encoding="utf-8")

        ErrorLog(self.path, lambda: NOON)(self.failure())


if __name__ == "__main__":
    unittest.main()
