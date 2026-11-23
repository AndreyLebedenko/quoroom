"""Task tray-04: the Startup-folder shortcut, tested against a temporary folder."""

import tempfile
import unittest
from pathlib import Path

from quoroomtray import settings
from quoroomtray.autostart import (
    Autostart,
    AutostartOutcome,
    Shortcut,
    stand_shortcut,
    startup_folder,
)

APPDATA = "C:\\Users\\someone\\AppData\\Roaming"


class RecordingWriter:
    def __init__(self, failure: OSError | None = None):
        self.failure = failure
        self.written: list[Shortcut] = []

    def __call__(self, shortcut: Shortcut) -> None:
        if self.failure is not None:
            raise self.failure
        self.written.append(shortcut)
        shortcut.path.write_bytes(b"shortcut")


class AutostartTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name) / "Startup"
        self.target = Path(directory.name) / "pythonw.exe"
        self.target.write_bytes(b"interpreter")
        self.writer = RecordingWriter()
        self.shortcut = Shortcut(
            self.folder / "Quoroom Tray.lnk",
            self.target,
            "-m quoroomtray",
            Path(directory.name) / "bridge",
            "Quoroom tray launcher",
        )
        self.autostart = Autostart(self.shortcut, self.writer)

    def test_install_hands_the_whole_shortcut_to_the_writer(self):
        outcome = self.autostart.install()

        self.assertEqual(AutostartOutcome.INSTALLED, outcome)
        self.assertEqual([self.shortcut], self.writer.written)

    def test_install_creates_the_startup_folder_when_it_is_missing(self):
        self.autostart.install()

        self.assertTrue(self.shortcut.path.is_file())

    def test_install_over_an_existing_shortcut_writes_it_again(self):
        self.autostart.install()

        outcome = self.autostart.install()

        self.assertEqual(AutostartOutcome.INSTALLED, outcome)
        self.assertEqual(2, len(self.writer.written))

    def test_install_without_the_interpreter_writes_nothing(self):
        self.target.unlink()

        outcome = self.autostart.install()

        self.assertEqual(AutostartOutcome.TARGET_MISSING, outcome)
        self.assertEqual([], self.writer.written)
        self.assertFalse(self.folder.exists())

    def test_a_writer_failure_reaches_the_caller(self):
        failing = Autostart(self.shortcut, RecordingWriter(OSError("no COM")))

        with self.assertRaises(OSError):
            failing.install()

    def test_remove_deletes_the_shortcut(self):
        self.autostart.install()

        outcome = self.autostart.remove()

        self.assertEqual(AutostartOutcome.REMOVED, outcome)
        self.assertFalse(self.shortcut.path.exists())

    def test_remove_leaves_every_other_file_of_the_startup_folder(self):
        self.autostart.install()
        neighbour = self.folder / "Another program.lnk"
        neighbour.write_bytes(b"not ours")

        self.autostart.remove()

        self.assertTrue(neighbour.is_file())

    def test_remove_without_a_shortcut_is_not_an_error(self):
        outcome = self.autostart.remove()

        self.assertEqual(AutostartOutcome.NOT_INSTALLED, outcome)

    def test_remove_does_not_need_the_interpreter(self):
        self.autostart.install()
        self.target.unlink()

        self.assertEqual(AutostartOutcome.REMOVED, self.autostart.remove())

    def test_the_shortcut_is_exposed_for_the_report(self):
        self.assertEqual(self.shortcut, self.autostart.shortcut)


class StandShortcutTests(unittest.TestCase):
    def setUp(self):
        self.shortcut = stand_shortcut({"APPDATA": APPDATA})

    def test_it_lives_in_the_startup_folder_of_the_user_profile(self):
        self.assertEqual(
            Path(APPDATA) / "Microsoft/Windows/Start Menu/Programs/Startup",
            startup_folder({"APPDATA": APPDATA}),
        )
        self.assertEqual(
            startup_folder({"APPDATA": APPDATA}), self.shortcut.path.parent
        )

    def test_it_runs_the_tray_module_under_pythonw_of_the_project_environment(self):
        self.assertEqual(
            settings.BRIDGE_DIR / ".venv" / "Scripts" / "pythonw.exe",
            self.shortcut.target,
        )
        self.assertEqual("-m quoroomtray", self.shortcut.arguments)

    def test_it_starts_in_bridge_so_the_module_and_its_config_resolve(self):
        self.assertEqual(settings.BRIDGE_DIR, self.shortcut.working_directory)
        self.assertTrue((settings.BRIDGE_DIR / "quoroomtray").is_dir())

    def test_the_module_named_in_the_arguments_is_the_package_that_exists(self):
        module = self.shortcut.arguments.split()[-1]

        self.assertTrue((settings.BRIDGE_DIR / module / "__main__.py").is_file())

    def test_the_file_is_a_lnk_named_for_the_tray(self):
        self.assertEqual("Quoroom Tray.lnk", self.shortcut.path.name)


if __name__ == "__main__":
    unittest.main()
