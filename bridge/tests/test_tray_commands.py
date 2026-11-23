"""Task tray-04: the command line of the tray and the autostart report."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from quoroomtray.autostart import Autostart, AutostartOutcome, Shortcut
from quoroomtray.commands import (
    OUTCOME_KEYS,
    TrayCommand,
    parse_command,
    run_autostart_command,
)
from quoroomtray.texts import TrayTexts


class ParseCommandTests(unittest.TestCase):
    def parse_quietly(self, argv):
        with contextlib.redirect_stderr(io.StringIO()):
            return parse_command(argv)

    def test_no_arguments_run_the_tray(self):
        self.assertEqual(TrayCommand.RUN, parse_command([]))

    def test_install_autostart_is_recognised(self):
        self.assertEqual(
            TrayCommand.INSTALL_AUTOSTART, parse_command(["--install-autostart"])
        )

    def test_remove_autostart_is_recognised(self):
        self.assertEqual(
            TrayCommand.REMOVE_AUTOSTART, parse_command(["--remove-autostart"])
        )

    def test_install_and_remove_together_are_refused(self):
        with self.assertRaises(SystemExit) as refused:
            self.parse_quietly(["--install-autostart", "--remove-autostart"])

        self.assertEqual(2, refused.exception.code)

    def test_an_unknown_flag_is_refused_rather_than_starting_the_tray(self):
        with self.assertRaises(SystemExit) as refused:
            self.parse_quietly(["--install-autostrat"])

        self.assertEqual(2, refused.exception.code)


class FakeWriter:
    def __init__(self, failure: OSError | None = None):
        self.failure = failure

    def __call__(self, shortcut: Shortcut) -> None:
        if self.failure is not None:
            raise self.failure
        shortcut.path.write_bytes(b"shortcut")


class AutostartCommandTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.target = root / "pythonw.exe"
        self.target.write_bytes(b"interpreter")
        self.shortcut = Shortcut(
            root / "Startup" / "Quoroom Tray.lnk",
            self.target,
            "-m quoroomtray",
            root,
            "Quoroom tray launcher",
        )
        self.echoed: list[str] = []

    def run_command(self, command, language="en", writer=None):
        autostart = Autostart(self.shortcut, writer or FakeWriter())
        return run_autostart_command(
            command, autostart, TrayTexts(language), self.echoed.append
        )

    def test_install_succeeds_and_names_the_shortcut(self):
        code = self.run_command(TrayCommand.INSTALL_AUTOSTART)

        self.assertEqual(0, code)
        self.assertEqual([f"Autostart installed: {self.shortcut.path}"], self.echoed)

    def test_remove_succeeds_and_names_the_shortcut(self):
        self.run_command(TrayCommand.INSTALL_AUTOSTART)
        self.echoed.clear()

        code = self.run_command(TrayCommand.REMOVE_AUTOSTART)

        self.assertEqual(0, code)
        self.assertEqual([f"Autostart removed: {self.shortcut.path}"], self.echoed)

    def test_removing_what_was_never_installed_still_succeeds_and_says_so(self):
        code = self.run_command(TrayCommand.REMOVE_AUTOSTART)

        self.assertEqual(0, code)
        self.assertIn("nothing to remove", self.echoed[0])

    def test_a_missing_interpreter_fails_and_names_it(self):
        self.target.unlink()

        code = self.run_command(TrayCommand.INSTALL_AUTOSTART)

        self.assertEqual(1, code)
        self.assertIn(str(self.target), self.echoed[0])

    def test_a_writer_failure_fails_and_reports_its_detail(self):
        code = self.run_command(
            TrayCommand.INSTALL_AUTOSTART, writer=FakeWriter(OSError("COM refused"))
        )

        self.assertEqual(1, code)
        self.assertEqual(["Autostart failed: COM refused"], self.echoed)

    def test_the_report_is_in_the_tray_language(self):
        self.run_command(TrayCommand.INSTALL_AUTOSTART, language="ru")

        russian = TrayTexts("ru").text(
            "autostart.installed", shortcut=self.shortcut.path
        )
        english = TrayTexts("en").text(
            "autostart.installed", shortcut=self.shortcut.path
        )
        self.assertEqual([russian], self.echoed)
        self.assertNotEqual(english, russian)

    def test_every_outcome_has_a_message_in_both_languages(self):
        for outcome in AutostartOutcome:
            for language in ("en", "ru"):
                with self.subTest(outcome=outcome, language=language):
                    text = TrayTexts(language).text(
                        OUTCOME_KEYS[outcome],
                        shortcut=self.shortcut.path,
                        target=self.target,
                    )
                    self.assertTrue(text)


if __name__ == "__main__":
    unittest.main()
