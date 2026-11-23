"""Task tray-04: a failure before the icon exists leaves a trace and a non-zero exit."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quoroomtray import __main__ as entry_point
from quoroomtray.guard import STARTUP_FAILED_EXIT_CODE, exit_code_after_reporting

SHELL_MODULE = "quoroomtray.shell.pystray_shell"


class ExitCodeAfterReportingTests(unittest.TestCase):
    def setUp(self):
        self.reported = []

    def test_a_normal_exit_code_is_passed_through_and_nothing_is_reported(self):
        code = exit_code_after_reporting(lambda: 0, self.reported.append)

        self.assertEqual(0, code)
        self.assertEqual([], self.reported)

    def test_a_failure_is_reported_and_the_exit_code_is_nonzero(self):
        def broken():
            raise ImportError("No module named 'pystray'")

        code = exit_code_after_reporting(broken, self.reported.append)

        self.assertEqual(STARTUP_FAILED_EXIT_CODE, code)
        self.assertNotEqual(0, code)
        self.assertEqual(["No module named 'pystray'"], [str(f) for f in self.reported])

    def test_a_report_that_itself_fails_does_not_hide_the_nonzero_exit(self):
        def broken():
            raise RuntimeError("icon failed")

        def broken_report(failure):
            raise OSError("log is locked")

        code = exit_code_after_reporting(broken, broken_report)

        self.assertEqual(STARTUP_FAILED_EXIT_CODE, code)

    def test_a_user_interrupt_is_not_swallowed(self):
        def interrupted():
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            exit_code_after_reporting(interrupted, self.reported.append)


class TrayStartUpWithoutPystrayTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.log_path = Path(directory.name) / "state" / "tray-errors.log"
        patched_modules = mock.patch.dict(sys.modules, {"pystray": None})
        patched_modules.start()
        self.addCleanup(patched_modules.stop)
        sys.modules.pop(SHELL_MODULE, None)
        patched_log = mock.patch.object(entry_point, "ERROR_LOG", self.log_path)
        patched_log.start()
        self.addCleanup(patched_log.stop)

    def test_main_exits_nonzero_when_pystray_cannot_be_imported(self):
        self.assertNotEqual(0, entry_point.main([]))

    def test_main_writes_the_import_failure_to_the_tray_error_log(self):
        entry_point.main([])

        written = self.log_path.read_text(encoding="utf-8")
        self.assertIn("ModuleNotFoundError", written)
        self.assertIn("pystray", written)

    def test_the_failed_import_claims_no_instance_so_the_next_start_is_not_blocked(
        self,
    ):
        with mock.patch.object(entry_point, "claim_named_mutex") as claim:
            entry_point.main([])

        claim.assert_not_called()


if __name__ == "__main__":
    unittest.main()
