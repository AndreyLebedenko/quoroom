"""Карточка local-installers-03: install.ps1 и install.sh только передают."""

import base64
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from tests.installer_fakes import SH, posix_path
from sessionchat.installer.main import CANCELLED, DONE, FAILED, HUMAN, USAGE

REPO = Path(__file__).resolve().parent.parent.parent
PWSH_51 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / (
    r"System32\WindowsPowerShell\v1.0\powershell.exe"
)
PWSH_7 = shutil.which("pwsh")
CORE_CODES = (DONE, FAILED, USAGE, HUMAN, CANCELLED)
MISSING_PYTHON = 9
PROBE_MARKER = "quoroom-python="

STUB = """\
import os
import sys

if os.environ.get("STUB_STDERR"):
    print("noise on stderr", file=sys.stderr)
print("ARGS:" + "|".join(f"[{value}]" for value in sys.argv[1:]))
print("PYTHONPATH:" + os.environ.get("PYTHONPATH", ""))
print("UTF8MODE:" + str(sys.flags.utf8_mode))
print("ENCODING:" + str(sys.stdout.encoding))
raise SystemExit(int(os.environ.get("STUB_EXIT", "0")))
"""

NOISY_LAUNCHER = "@echo No suitable Python runtime found 1>&2\r\nexit /b 1\r\n"

STOPPED_CALLER = """\
$ErrorActionPreference = 'Stop'
& $args[0] --role both
exit $LASTEXITCODE
"""

RUSSIAN_CONSOLE_CALLER = """\
[Console]::OutputEncoding = [System.Text.Encoding]::GetEncoding(866)
& $args[0] --role both
exit $LASTEXITCODE
"""

CALLER_WATCHER = """\
$beforePath = $env:PYTHONPATH
$beforeUtf8 = $env:PYTHONUTF8
& $args[0] --role both | Out-Null
if ($env:PYTHONPATH -ne $beforePath) { Write-Host "PATH:$env:PYTHONPATH"; exit 7 }
if ($env:PYTHONUTF8 -ne $beforeUtf8) { Write-Host "UTF8:$env:PYTHONUTF8"; exit 8 }
Write-Host "UNCHANGED"
exit 0
"""


def windows() -> str | None:
    return None if PWSH_51.is_file() else f"нет Windows PowerShell 5.1: {PWSH_51}"


def seven() -> str | None:
    return None if PWSH_7 else "pwsh не найден в PATH: 7.x отдельно не проверен"


def shell() -> str | None:
    return None if SH else "posix sh не найден в PATH"


class EntryPointCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)

    def repo(self, name: str) -> Path:
        root = self.tmp / name
        package = root / "bridge" / "sessionchat" / "installer"
        package.mkdir(parents=True)
        (root / "bridge" / "sessionchat" / "__init__.py").write_text(
            "", encoding="utf-8"
        )
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "__main__.py").write_text(STUB, encoding="utf-8")
        return root

    def windows_repo(self) -> Path:
        return self.repo("Quoroom с пробелами")

    def posix_repo(self) -> Path:
        return self.repo("Quoroom with spaces")

    def copy(self, script: str, root: Path) -> Path:
        target = root / script
        shutil.copy(REPO / script, target)
        return target

    def tool_dir(self) -> Path:
        directory = self.tmp / "bin"
        directory.mkdir(exist_ok=True)
        launcher = directory / "dirname"
        launcher.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            '  */*) printf "%s\\n" "${1%/*}" ;;\n'
            '  *) printf "%s\\n" "." ;;\n'
            "esac\n",
            encoding="utf-8",
        )
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        return directory

    def powershell(
        self,
        root: Path,
        argv: list[str],
        env: dict[str, str],
        shell_path: Path = PWSH_51,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                str(shell_path),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(root / "install.ps1"),
                *argv,
            ],
            cwd=self.tmp,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def sh(
        self, root: Path, argv: list[str], env: dict[str, str]
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [SH, posix_path(root / "install.sh"), *argv],
            cwd=str(self.tmp),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def sh_with_arguments(
        self, root: Path, argv: list[str], env: dict[str, str]
    ) -> subprocess.CompletedProcess:
        wrapper = self.tmp / "вызов.sh"
        literals = " ".join("'" + value.replace("'", "'\\''") + "'" for value in argv)
        wrapper.write_text(
            f'#!/bin/sh\nexec "{posix_path(Path(SH))}" '
            f'"{posix_path(root / "install.sh")}" {literals}\n',
            encoding="utf-8",
        )
        return subprocess.run(
            [SH, posix_path(wrapper)],
            cwd=str(self.tmp),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def stub_env(self, **extra: str) -> dict[str, str]:
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.update({"STUB_EXIT": "0", **extra})
        return env

    def without_python(self) -> dict[str, str]:
        empty = self.tmp / "пусто"
        empty.mkdir(exist_ok=True)
        return {
            "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
            "PATHEXT": os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD"),
            "PATH": str(empty),
        }

    def arguments_of(self, done: subprocess.CompletedProcess) -> list[str]:
        line = next(row for row in done.stdout.splitlines() if row.startswith("ARGS:"))
        return line[len("ARGS:") :].split("|")

    def value_of(self, done: subprocess.CompletedProcess, key: str) -> str:
        for row in done.stdout.splitlines():
            if row.startswith(f"{key}:"):
                return row[len(key) + 1 :]
        self.fail(f"в выводе нет {key}:\n{done.stdout}\n{done.stderr}")


class WindowsEntryPointTests(EntryPointCase):
    def setUp(self):
        super().setUp()
        skipped = windows()
        if skipped:
            self.skipTest(skipped)

    def test_arguments_reach_the_shared_layer_unchanged(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        wanted = [
            "--role",
            "server",
            "",
            'q"uote',
            "C:\\dir with space\\",
            "tail\\",
            'x\\"y',
            "Мои документы",
        ]
        done = self.powershell(root, wanted, self.stub_env())
        self.assertEqual(done.returncode, DONE, done.stderr)
        self.assertEqual(self.arguments_of(done), [f"[{value}]" for value in wanted])

    def test_the_repository_path_with_spaces_and_cyrillic_works(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        done = self.powershell(root, ["--role", "both"], self.stub_env())
        self.assertIn(str(root / "bridge"), self.value_of(done, "PYTHONPATH"))

    def test_a_successful_run_exits_zero(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        self.assertEqual(
            self.powershell(root, [], self.stub_env(STUB_EXIT=str(DONE))).returncode,
            DONE,
        )

    def test_every_exit_code_of_the_core_passes_through(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        for code in CORE_CODES:
            if code == DONE:
                continue
            with self.subTest(code=code):
                done = self.powershell(root, [], self.stub_env(STUB_EXIT=str(code)))
                self.assertEqual(done.returncode, code, done.stderr)

    def test_a_layer_writing_to_stderr_keeps_its_exit_code(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        done = self.powershell(
            root, [], self.stub_env(STUB_EXIT=str(FAILED), STUB_STDERR="1")
        )
        self.assertEqual(done.returncode, FAILED, done.stdout + done.stderr)
        self.assertIn("noise on stderr", done.stderr)

    def noisy_launcher(self) -> Path:
        launcher = self.tmp / "launcher"
        launcher.mkdir(exist_ok=True)
        (launcher / "py.cmd").write_text(NOISY_LAUNCHER, encoding="utf-8")
        return launcher

    def through_caller(
        self, caller_source: str, root: Path, env: dict[str, str]
    ) -> subprocess.CompletedProcess:
        caller = self.tmp / "caller.ps1"
        caller.write_text(caller_source, encoding="utf-8-sig")
        return subprocess.run(
            [
                str(PWSH_51),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(caller),
                str(root / "install.ps1"),
            ],
            cwd=self.tmp,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def test_a_launcher_failing_loudly_falls_back_to_the_next_candidate(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        env = self.stub_env()
        env["PATH"] = str(self.noisy_launcher()) + os.pathsep + env["PATH"]
        done = self.powershell(root, ["--role", "both"], env)
        self.assertEqual(done.returncode, DONE, done.stdout + done.stderr)
        self.assertIn("[--role]", self.value_of(done, "ARGS"))

    def test_a_caller_with_stop_in_its_session_still_probes_a_noisy_launcher(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        env = self.stub_env(STUB_EXIT=str(FAILED), STUB_STDERR="1")
        env["PATH"] = str(self.noisy_launcher()) + os.pathsep + env["PATH"]
        done = self.through_caller(STOPPED_CALLER, root, env)
        self.assertEqual(done.returncode, FAILED, done.stdout + done.stderr)
        self.assertIn("[--role]", done.stdout)
        self.assertIn("noise on stderr", done.stderr)

    def test_a_launcher_pointing_nowhere_never_exits_zero(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        launcher = self.tmp / "broken"
        launcher.mkdir()
        nowhere = str(root / "нет" / "nowhere-python.exe").encode("utf-8")
        answer = PROBE_MARKER + base64.b64encode(nowhere).decode("ascii")
        (launcher / "python.bat").write_text(
            f"@echo {answer}\r\n@exit /b 0\r\n", encoding="utf-8"
        )
        done = self.powershell(root, [], self.launcher_env(launcher))
        said = done.stdout + done.stderr
        self.assertEqual(done.returncode, MISSING_PYTHON, said)
        self.assertIn("nowhere-python.exe", said)

    def test_a_bat_launcher_forwarding_to_a_real_interpreter_reaches_the_layer(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        launcher = self.tmp / "bat"
        launcher.mkdir()
        (launcher / "python.bat").write_text(
            f'@"{sys.executable}" %*\r\n', encoding="utf-8"
        )
        done = self.powershell(root, ["--role", "both"], self.launcher_env(launcher))
        self.assertEqual(done.returncode, DONE, done.stdout + done.stderr)
        self.assertIn("[--role]", self.value_of(done, "ARGS"))

    def test_a_bat_launcher_echoing_its_commands_still_reaches_the_layer(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        launcher = self.tmp / "noisy-bat"
        launcher.mkdir()
        (launcher / "python.bat").write_text(
            f'"{sys.executable}" %*\r\nset KEPT=%ERRORLEVEL%\r\nexit /b %KEPT%\r\n',
            encoding="utf-8",
        )
        done = self.powershell(root, ["--role", "both"], self.launcher_env(launcher))
        self.assertEqual(done.returncode, DONE, done.stdout + done.stderr)
        self.assertIn("[--role]", self.value_of(done, "ARGS"))

    def launcher_env(self, launcher: Path) -> dict[str, str]:
        return {
            "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
            "PATHEXT": os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD"),
            "PATH": str(launcher),
            "STUB_EXIT": str(DONE),
        }

    def cyrillic_interpreter(self) -> Path:
        venv = self.tmp / "Андрей" / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True
        )
        return venv / "Scripts"

    def test_an_interpreter_under_a_cyrillic_profile_reaches_the_layer(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        env = self.launcher_env(self.cyrillic_interpreter())
        env["PYTHONIOENCODING"] = "cp1251"
        done = self.through_caller(RUSSIAN_CONSOLE_CALLER, root, env)
        self.assertEqual(done.returncode, DONE, done.stdout + done.stderr)
        self.assertIn("[--role]", done.stdout)

    def test_pythonpath_does_not_inherit_the_callers_value(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        done = self.powershell(
            root, [], self.stub_env(PYTHONPATH=str(self.home_path()))
        )
        self.assertEqual(self.value_of(done, "PYTHONPATH"), str(root / "bridge"))

    def home_path(self) -> str:
        return str(self.tmp / "чужая" / "папка")

    def test_python_runs_in_utf8_mode(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        done = self.powershell(root, ["--имя", "кот"], self.stub_env())
        self.assertEqual(self.value_of(done, "UTF8MODE"), "1")
        self.assertEqual(self.value_of(done, "ENCODING").lower(), "utf-8")

    def test_the_callers_environment_is_left_alone(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        watcher = self.tmp / "watcher.ps1"
        watcher.write_text(CALLER_WATCHER, encoding="utf-8-sig")
        done = subprocess.run(
            [
                str(PWSH_51),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(watcher),
                str(root / "install.ps1"),
            ],
            cwd=self.tmp,
            env=self.stub_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("UNCHANGED", done.stdout)

    def test_a_missing_python_exits_with_its_own_code(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        done = self.powershell(root, [], self.without_python())
        self.assertEqual(done.returncode, MISSING_PYTHON, done.stderr)
        self.assertNotIn(done.returncode, CORE_CODES)

    def test_a_missing_python_explains_and_does_not_start_the_layer(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        done = self.powershell(root, [], self.without_python())
        said = done.stdout + done.stderr
        self.assertIn("Python", said)
        self.assertNotIn("ARGS:", said)

    def test_a_missing_python_names_the_platform_command(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        done = self.powershell(root, [], self.without_python())
        self.assertIn("winget install Python.Python.3.11", done.stdout + done.stderr)

    def test_a_missing_shared_layer_is_reported_before_python(self):
        root = self.windows_repo()
        self.copy("install.ps1", root)
        shutil.rmtree(root / "bridge" / "sessionchat")
        done = self.powershell(root, [], self.stub_env())
        self.assertEqual(done.returncode, MISSING_PYTHON, done.stderr)
        self.assertNotIn("ARGS:", done.stdout)

    def test_the_same_flow_runs_under_powershell_7_when_present(self):
        skipped = seven()
        if skipped:
            self.skipTest(skipped)
        root = self.windows_repo()
        self.copy("install.ps1", root)
        done = self.powershell(
            root,
            ["--role", "server", "", 'q"uote'],
            self.stub_env(STUB_EXIT=str(HUMAN)),
            shell_path=Path(PWSH_7),
        )
        self.assertEqual(done.returncode, HUMAN, done.stderr)
        self.assertEqual(
            self.arguments_of(done), ["[--role]", "[server]", "[]", '[q"uote]']
        )


class PosixEntryPointTests(EntryPointCase):
    def setUp(self):
        super().setUp()
        skipped = shell()
        if skipped:
            self.skipTest(skipped)

    def shim(self) -> Path:
        directory = self.tmp / "shim"
        directory.mkdir(exist_ok=True)
        launcher = directory / "python3"
        launcher.write_text(
            f'#!/bin/sh\nexec "{posix_path(Path(sys.executable))}" "$@"\n',
            encoding="utf-8",
        )
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        return directory

    def sh_env(self, **extra: str) -> dict[str, str]:
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PATH"] = os.pathsep.join(
            [posix_path(self.shim()), posix_path(self.tool_dir())]
        )
        env.update({"STUB_EXIT": "0", **extra})
        return env

    def posix_without_python(self) -> dict[str, str]:
        return {"PATH": posix_path(self.tool_dir()), "STUB_EXIT": "0"}

    def test_arguments_reach_the_shared_layer_unchanged(self):
        root = self.posix_repo()
        self.copy("install.sh", root)
        wanted = [
            "--role",
            "server",
            "",
            'q"uote',
            "Мои документы",
            "--flag=with space",
        ]
        done = self.sh_with_arguments(root, wanted, self.sh_env())
        self.assertEqual(done.returncode, DONE, done.stderr)
        self.assertEqual(self.arguments_of(done), [f"[{value}]" for value in wanted])

    def test_the_repository_path_with_spaces_works(self):
        root = self.posix_repo()
        self.copy("install.sh", root)
        done = self.sh(root, ["--role", "both"], self.sh_env())
        self.assertIn(
            str(root / "bridge").replace("\\", "/"), self.value_of(done, "PYTHONPATH")
        )

    def test_the_repository_path_with_cyrillic_works(self):
        root = self.repo("Репо с пробелом")
        self.copy("install.sh", root)
        done = self.sh(root, ["--role", "both"], self.sh_env())
        self.assertIn(
            str(root / "bridge").replace("\\", "/"), self.value_of(done, "PYTHONPATH")
        )

    def test_pythonpath_does_not_inherit_the_callers_value(self):
        root = self.posix_repo()
        self.copy("install.sh", root)
        env = self.sh_env(PYTHONPATH=posix_path(self.tmp / "чужая"))
        done = self.sh(root, [], env)
        self.assertEqual(
            self.value_of(done, "PYTHONPATH"),
            str(root / "bridge").replace("\\", "/"),
        )

    def test_every_exit_code_of_the_core_passes_through(self):
        root = self.posix_repo()
        self.copy("install.sh", root)
        for code in CORE_CODES:
            if code == DONE:
                continue
            with self.subTest(code=code):
                done = self.sh(root, [], self.sh_env(STUB_EXIT=str(code)))
                self.assertEqual(done.returncode, code, done.stderr)

    def test_a_layer_writing_to_stderr_keeps_its_exit_code(self):
        root = self.posix_repo()
        self.copy("install.sh", root)
        done = self.sh(root, [], self.sh_env(STUB_EXIT=str(FAILED), STUB_STDERR="1"))
        self.assertEqual(done.returncode, FAILED, done.stdout + done.stderr)
        self.assertIn("noise on stderr", done.stderr)

    def test_python_runs_in_utf8_mode(self):
        root = self.posix_repo()
        self.copy("install.sh", root)
        done = self.sh(root, ["--имя", "кот"], self.sh_env())
        self.assertEqual(self.value_of(done, "UTF8MODE"), "1")
        self.assertEqual(self.value_of(done, "ENCODING").lower(), "utf-8")

    def test_a_missing_python_exits_with_its_own_code(self):
        root = self.posix_repo()
        self.copy("install.sh", root)
        done = self.sh(root, [], self.posix_without_python())
        self.assertEqual(done.returncode, MISSING_PYTHON, done.stderr)
        self.assertNotIn(done.returncode, CORE_CODES)

    def test_a_missing_python_explains_and_does_not_start_the_layer(self):
        root = self.posix_repo()
        self.copy("install.sh", root)
        done = self.sh(root, [], self.posix_without_python())
        said = done.stdout + done.stderr
        self.assertIn("python3", said)
        self.assertNotIn("ARGS:", said)

    def test_a_missing_python_names_the_platform_command(self):
        root = self.posix_repo()
        self.copy("install.sh", root)
        done = self.sh(root, [], self.posix_without_python())
        self.assertIn("sudo apt install python3", done.stdout + done.stderr)

    def test_a_missing_shared_layer_is_reported_before_python(self):
        root = self.posix_repo()
        self.copy("install.sh", root)
        shutil.rmtree(root / "bridge" / "sessionchat")
        done = self.sh(root, [], self.sh_env())
        self.assertEqual(done.returncode, MISSING_PYTHON, done.stderr)
        self.assertNotIn("ARGS:", done.stdout)


class ScriptTextTests(EntryPointCase):
    def test_the_windows_script_is_saved_with_a_bom_for_powershell_51(self):
        raw = (REPO / "install.ps1").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "install.ps1 без BOM")

    def test_the_windows_script_has_no_construct_that_powershell_51_lacks(self):
        source = (REPO / "install.ps1").read_text(encoding="utf-8-sig")
        for banned in ("&&", "||", "?? ", "?:", "?->"):
            self.assertNotIn(banned, source, f"5.1 может не знать {banned!r}")

    def test_the_posix_script_is_valid_posix_sh(self):
        skipped = shell()
        if skipped:
            self.skipTest(skipped)
        done = subprocess.run(
            [SH, "-n", posix_path(REPO / "install.sh")],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_posix_script_uses_no_bashism(self):
        source = (REPO / "install.sh").read_text(encoding="utf-8")
        for banned in ("[[", "]]", "function ", "source ", "local ", "=="):
            self.assertNotIn(banned, source, f"не POSIX sh: {banned!r}")

    def required_version(self) -> str:
        with open(REPO / "bridge" / "pyproject.toml", "rb") as source:
            return tomllib.load(source)["project"]["requires-python"]

    def pinned(self) -> str:
        return f"({self.required_version().removeprefix('>=')})".replace(".", ", ")

    def test_the_windows_probe_checks_the_version_pyproject_requires(self):
        source = (REPO / "install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn(self.pinned(), source)

    def test_the_posix_probe_checks_the_version_pyproject_requires(self):
        source = (REPO / "install.sh").read_text(encoding="utf-8")
        self.assertIn(self.pinned(), source)

    def test_windows_tries_the_launcher_before_the_bare_interpreter(self):
        source = (REPO / "install.ps1").read_text(encoding="utf-8-sig")
        self.assertLess(source.index("'py'"), source.index("'python'"))

    def test_posix_tries_python3_first(self):
        source = (REPO / "install.sh").read_text(encoding="utf-8")
        self.assertLess(source.index("python3 python"), source.index('"$python_bin"'))

    def test_the_windows_probe_answers_with_the_marker_the_tests_use(self):
        source = (REPO / "install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn(f"$marker = '{PROBE_MARKER}'", source)

    def test_the_windows_script_explicitly_survives_native_stderr(self):
        source = (REPO / "install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$ErrorActionPreference = 'Continue'", source)
        self.assertNotIn("$ErrorActionPreference = 'Stop'", source)

    def test_neither_script_explains_the_design_in_its_header(self):
        for script in ("install.ps1", "install.sh"):
            with self.subTest(script=script):
                head = (REPO / script).read_text(encoding="utf-8-sig")[:700]
                self.assertNotIn("Вся логика установки", head)


if __name__ == "__main__":
    unittest.main()
