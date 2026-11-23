"""Task tray-04: the PowerShell writer of the Startup shortcut."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from quoroomtray.autostart import Shortcut
from quoroomtray.shortcut_writer import (
    LINK_ARGUMENTS,
    LINK_DESCRIPTION,
    LINK_PATH,
    LINK_TARGET,
    LINK_WORKING_DIRECTORY,
    ShortcutWriteError,
    shortcut_environment,
    write_shortcut_with_powershell,
)

SHORTCUT = Shortcut(
    Path("C:/Startup/Quoroom Tray.lnk"),
    Path("C:/Project/bridge/.venv/Scripts/pythonw.exe"),
    "-m quoroomtray",
    Path("C:/Project/bridge"),
    "Quoroom tray launcher",
)


class RecordedRun:
    def __init__(self, returncode=0, stdout=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.command = None
        self.options = None

    def __call__(self, command, **options):
        self.command = command
        self.options = options
        return subprocess.CompletedProcess(command, self.returncode, self.stdout)


class ShortcutEnvironmentTests(unittest.TestCase):
    def test_every_field_of_the_shortcut_travels_in_the_environment(self):
        environment = shortcut_environment(SHORTCUT, {"PATH": "kept"})

        self.assertEqual("kept", environment["PATH"])
        self.assertEqual(str(SHORTCUT.path), environment[LINK_PATH])
        self.assertEqual(str(SHORTCUT.target), environment[LINK_TARGET])
        self.assertEqual("-m quoroomtray", environment[LINK_ARGUMENTS])
        self.assertEqual(
            str(SHORTCUT.working_directory), environment[LINK_WORKING_DIRECTORY]
        )
        self.assertEqual("Quoroom tray launcher", environment[LINK_DESCRIPTION])


class PowerShellWriterTests(unittest.TestCase):
    def test_the_script_is_passed_without_any_path_pasted_into_it(self):
        run = RecordedRun()

        write_shortcut_with_powershell(SHORTCUT, run, {})

        script = run.command[-1]
        self.assertNotIn(str(SHORTCUT.path), script)
        self.assertNotIn(str(SHORTCUT.target), script)

    def test_the_shortcut_fields_reach_the_process_through_its_environment(self):
        run = RecordedRun()

        write_shortcut_with_powershell(SHORTCUT, run, {"PATH": "kept"})

        self.assertEqual(
            shortcut_environment(SHORTCUT, {"PATH": "kept"}), run.options["env"]
        )

    def test_a_nonzero_exit_raises_with_the_exit_code_and_the_output(self):
        run = RecordedRun(5, b"access denied")

        with self.assertRaises(ShortcutWriteError) as failure:
            write_shortcut_with_powershell(SHORTCUT, run, {})

        self.assertIn("5", str(failure.exception))
        self.assertIn("access denied", str(failure.exception))

    def test_the_failure_is_an_oserror_so_the_command_reports_it(self):
        self.assertTrue(issubclass(ShortcutWriteError, OSError))


@unittest.skipUnless(sys.platform == "win32", "needs Windows PowerShell and WScript")
class RealShortcutTests(unittest.TestCase):
    def read_back(self, path: Path) -> list[str]:
        script = (
            "$link = (New-Object -ComObject WScript.Shell).CreateShortcut("
            "$env:READ_BACK_PATH); "
            "$link.TargetPath; $link.Arguments; $link.WorkingDirectory"
        )
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            env={**os.environ, "READ_BACK_PATH": str(path)},
            capture_output=True,
            check=True,
        )
        return completed.stdout.decode("utf-8", errors="replace").splitlines()

    def test_a_shortcut_is_written_into_a_temporary_folder_with_its_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            shortcut = Shortcut(
                Path(directory) / "Quoroom Tray.lnk",
                Path(directory) / "pythonw.exe",
                "-m quoroomtray",
                Path(directory),
                "Quoroom tray launcher",
            )

            write_shortcut_with_powershell(shortcut)

            self.assertTrue(shortcut.path.is_file())
            self.assertEqual(
                [str(shortcut.target), "-m quoroomtray", str(Path(directory))],
                self.read_back(shortcut.path),
            )


if __name__ == "__main__":
    unittest.main()
