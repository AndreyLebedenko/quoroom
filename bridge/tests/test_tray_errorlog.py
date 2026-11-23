"""Task tray-03: the failure log."""

import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from quoroomtray.errorlog import ErrorLog
from quoroomtray.shell_settings import ERROR_LOG_MAX_BYTES

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


def raised_ten_calls_deep(text="boom"):
    def descend(depth):
        if depth == 0:
            raise RuntimeError(text)
        descend(depth - 1)

    try:
        descend(10)
    except RuntimeError as failure:
        return failure


class ErrorLogBoundTests(unittest.TestCase):
    SMALL_CAP = 2000

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "tray-errors.log"

    def log(self, max_bytes=SMALL_CAP):
        return ErrorLog(self.path, lambda: NOON, max_bytes)

    def test_the_cap_holds_at_least_fifty_entries_of_a_deep_failure(self):
        probe = ErrorLog(self.path, lambda: NOON)

        probe(raised_ten_calls_deep())
        entry_size = self.path.stat().st_size

        self.assertGreaterEqual(ERROR_LOG_MAX_BYTES, 50 * entry_size)

    def test_a_persistent_failure_never_grows_the_log_past_the_cap(self):
        log = self.log()

        for _ in range(100):
            log(raised_ten_calls_deep())

        self.assertLessEqual(self.path.stat().st_size, self.SMALL_CAP)

    def test_the_older_entries_move_to_one_backup_that_is_also_capped(self):
        log = self.log()

        for _ in range(100):
            log(raised_ten_calls_deep())

        self.assertTrue(log.backup_path.is_file())
        self.assertLessEqual(log.backup_path.stat().st_size, self.SMALL_CAP)
        self.assertEqual(
            {self.path.name, log.backup_path.name},
            {entry.name for entry in self.path.parent.iterdir()},
        )

    def test_the_newest_failure_is_always_in_the_log_after_a_rotation(self):
        log = self.log()
        for count in range(100):
            log(raised_ten_calls_deep(f"failure number {count}"))

        self.assertIn("failure number 99", self.path.read_text(encoding="utf-8"))

    def test_the_backup_holds_only_failures_older_than_the_ones_in_the_log(self):
        log = self.log()
        for count in range(100):
            log(raised_ten_calls_deep(f"failure number {count}"))

        def numbers(path):
            text = path.read_text(encoding="utf-8")
            return [
                int(n) for n in re.findall(r"RuntimeError: failure number (\d+)", text)
            ]

        backup, current = numbers(log.backup_path), numbers(self.path)

        self.assertTrue(backup)
        self.assertLess(max(backup), min(current))

    def test_a_log_under_the_cap_is_not_rotated(self):
        log = self.log(max_bytes=10_000_000)

        for _ in range(20):
            log(raised_ten_calls_deep())

        self.assertFalse(log.backup_path.exists())

    def test_one_failure_larger_than_the_cap_is_still_written_whole(self):
        log = self.log(max_bytes=10)

        log(raised_ten_calls_deep("a failure with a long enough message"))

        self.assertIn(
            "a failure with a long enough message",
            self.path.read_text(encoding="utf-8"),
        )

    def test_a_cyrillic_failure_counts_by_its_bytes_not_its_characters(self):
        log = self.log()

        for _ in range(100):
            log(raised_ten_calls_deep(chr(0x0441) * 80))

        self.assertLessEqual(self.path.stat().st_size, self.SMALL_CAP)


if __name__ == "__main__":
    unittest.main()
