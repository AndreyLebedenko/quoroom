"""Карточка local-installers-05: роль участника.

Ответ клиента приходит отчётом: карточка task-english-release-10.
"""

import json
import os
import re
import subprocess
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from subprocess import CompletedProcess

from tests.installer_fakes import (
    SH,
    InstallerTestCase,
    boundaries,
    completed,
    make_run,
    posix_path,
)
from sessionchat import client, client_language, client_result, kit
from sessionchat.installer import participant
from sessionchat.installer.boundaries import Probe
from sessionchat.installer.main import CANCELLED, DONE, FAILED, HUMAN, main
from sessionchat.installer.options import parse
from sessionchat.installer.ownership import Ownership
from sessionchat.installer.participant import participant_role
from sessionchat.installer.roles import built_in_roles

ROLE = "participant"
STATUS = "/status"
STATUS_COMMAND = "status"
STORE = participant.STORE
MANIFEST = participant.KIT_MANIFEST
RESTART = "Перезапустите открытые сессии"
NOISE = "погода в Казани дождливая, ничего не значит"
WRAP_BEFORE = "отчёт клиента ниже, прочитайте сами:\n"
WRAP_AFTER = "\nэто был отчёт."


class Machine:
    """Подставной исполнитель команд: помнит, что и чем установлено."""

    def __init__(
        self,
        home: Path,
        platform: str = "linux",
        present: dict[str, bool] | None = None,
        kit_conflict: bool = False,
        fails: str = "",
        kit_conflict_code: int = client.REFUSED,
        kit_answers: str = "document",
        kit_claims_no_writes: bool = False,
        kit_code: str = kit.CODE_NONE,
        room_language: str = "en",
        status_mode: str = "ok",
    ) -> None:
        self.home = home
        self.platform = platform
        self.present = {"uv": False, "pipx": True, "dsh": True} | (present or {})
        self.kit_conflict = kit_conflict
        self.kit_conflict_code = kit_conflict_code
        self.kit_answers = kit_answers
        self.kit_claims_no_writes = kit_claims_no_writes
        self.kit_code = kit_code
        self.fails = fails
        self.log: list[str] = []
        self.installed_by: set[str] = set()
        self.status_env: dict[str, str] = {}
        self.room_language = room_language
        self.status_mode = status_mode
        self.dsh_plugin_added = False
        self.pnpm_added = False
        self.pnpm_cwd: Path | None = None

    def __call__(self, argv, env=None, stdin=None, output=None, cwd=None):
        argv = [str(part) for part in argv]
        name = Path(argv[0]).name
        if name in ("uv", "pipx"):
            if env is not None:
                raise TypeError(f"{name} must not be given an environment")
            return self.tool(name, argv)
        if name.startswith("agentschat"):
            return self.agentschat(argv, env)
        if name == "dsh":
            return self.dsh(argv)
        if name == "pnpm":
            return self.pnpm(argv, cwd)
        raise AssertionError(f"непредусмотренный вызов: {' '.join(argv)}")

    def dsh(self, argv: list[str]):
        self.log.append(" ".join(argv))
        if not self.present.get("dsh", True):
            raise FileNotFoundError("dsh")
        if argv[1] == "--version":
            return completed("dsh 1.0.0")
        if "plugin" in argv[1:]:
            self.dsh_plugin_added = True
            return completed("plugin added")
        return completed("")

    def pnpm(self, argv: list[str], cwd: Path | None):
        self.log.append(" ".join(argv))
        if "add" in argv[1:]:
            self.pnpm_added = True
            self.pnpm_cwd = cwd
            return completed("added")
        return completed("")

    def tool(self, name: str, argv: list[str]):
        if not self.present.get(name, False):
            raise FileNotFoundError(name)
        self.log.append(" ".join(argv))
        if argv[1] == "--version":
            return completed(f"{name} 1.0.0")
        if "install" in argv[1:]:
            if self.fails == f"{name} install":
                return completed("", "прервано пользователем", 1)
            self.installed_by.add(name)
            self.binary(name)
            return completed("installed quoroom")
        if "uninstall" in argv[1:]:
            self.installed_by.discard(name)
            return completed("removed quoroom")
        if tuple(argv[1:]) == self.bin_query(name):
            if self.fails == f"{name} bin":
                return completed("", "неизвестная опция", 2)
            return completed(str(self.bin_dir(name)))
        if name in self.installed_by:
            return completed(self.default_listing(name))
        return completed("")

    def bin_query(self, name: str) -> tuple[str, ...]:
        return (
            ("tool", "dir", "--bin")
            if name == "uv"
            else ("environment", "--value", "PIPX_BIN_DIR")
        )

    def default_listing(self, name: str) -> str:
        if name == "uv":
            return f"{participant.PACKAGE} v1.0.0rc1\n- {participant.PACKAGE}\n"
        return f"{participant.PACKAGE} 1.0.0rc1\n"

    def agentschat(self, argv: list[str], env=None):
        self.log.append(" ".join(argv))
        if STATUS_COMMAND in argv[1:]:
            return self.status(env)
        if self.fails == "kit install":
            return completed("", "agentschat: сбой установки", 1)
        if self.fails == "kit uninstall":
            return completed("", "agentschat: сбой удаления", 1)
        if "install" in argv[1:]:
            if self.kit_conflict:
                return completed(self.conflict_kit(), NOISE, self.kit_conflict_code)
            if self.kit_answers == "words":
                return completed(self.refusal_words(), NOISE, 1)
            if self.kit_answers == "nothing":
                return completed("", "", 0)
            document = self.install_kit(argv[2:])
            if self.kit_answers == "wrapped":
                return completed(f"{WRAP_BEFORE}{document}{WRAP_AFTER}", NOISE, 0)
            return completed(document, NOISE)
        return completed(self.uninstall_kit(argv[2:]), NOISE)

    def status(self, env) -> CompletedProcess:
        self.status_env = dict(env or {})
        if self.status_mode == "missing":
            raise FileNotFoundError("agentschat")
        if self.status_mode == "undecodable":
            raise UnicodeDecodeError("utf-8", b"", 0, 1, "invalid start byte")
        if self.status_mode == "refuses":
            return completed(
                client_result.line("status", False, code="broker_unreachable"),
                "брокер недоступен",
                1,
            )
        if self.status_mode == "not-ok":
            return completed(
                f"{NOISE}\n{client_result.line('status', False, code='unexpected_answer')}"
            )
        if self.status_mode == "words":
            return completed("Язык комнаты: ru\n")
        if self.status_mode == "another-command":
            return completed(
                client_result.line("login", True, language=self.room_language)
            )
        client_language.remember(self.store(), self.room_language)
        answer = client_result.line(
            "status", True, language=self.room_language, sessions=[]
        )
        if self.status_mode == "quiet":
            return completed(answer)
        return completed(f"{answer}\n{NOISE}")

    def clis_for(self, flags: list[str]) -> list[str]:
        picked = [flag[2:] for flag in flags if flag[2:] in kit.CLIS]
        return picked or list(kit.CLIS)

    def target_for(self, cli: str) -> Path:
        root = ".claude" if cli == "claude" else ".config/opencode"
        return (
            self.home.joinpath(*root.split("/")) / "skills" / "chatlogin" / "SKILL.md"
        )

    def kit_content(self) -> bytes:
        return b"chatlogin skill\n"

    def report(self, command: str, code: str, steps: list[kit.Step]) -> str:
        return kit.Report(command, code, tuple(steps)).as_json()

    def refusal_words(self) -> str:
        return str(
            kit.KitConflict(
                [kit.Step(kit.Action.CONFLICT, self.target_for("claude"), "claude")],
                "ru",
            )
        )

    def foreign_kit(self) -> kit.Step:
        target = self.target_for("claude")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("// чужой навык\n", encoding="utf-8")
        return kit.Step(kit.Action.CONFLICT, target, "claude")

    def conflict_kit(self) -> str:
        return self.report(kit.COMMAND_INSTALL, kit.CODE_CONFLICT, [self.foreign_kit()])

    def install_kit(self, flags: list[str]) -> str:
        steps = []
        for cli in self.clis_for(flags):
            target = self.target_for(cli)
            if target.is_file() and target.read_bytes() == self.kit_content():
                steps.append(kit.Step(kit.Action.UNCHANGED, target, cli))
                continue
            action = kit.Action.UPDATE if target.is_file() else kit.Action.INSTALL
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.kit_content())
            steps.append(kit.Step(action, target, cli))
        self.write_manifest()
        if self.kit_claims_no_writes:
            steps = [
                kit.Step(kit.Action.UNCHANGED, step.target, step.cli) for step in steps
            ]
        return self.report(kit.COMMAND_INSTALL, self.kit_code, steps)

    def uninstall_kit(self, flags: list[str]) -> str:
        steps = []
        for cli in self.clis_for(flags):
            target = self.target_for(cli)
            if not target.is_file():
                continue
            if kit.digest(target.read_bytes()) != kit.digest(self.kit_content()):
                steps.append(kit.Step(kit.Action.KEEP, target, cli))
                continue
            target.unlink()
            steps.append(kit.Step(kit.Action.REMOVE, target, cli))
        self.write_manifest()
        return self.report(kit.COMMAND_UNINSTALL, kit.CODE_NONE, steps)

    def write_manifest(self) -> None:
        files = [
            {
                "path": str(self.target_for(cli)),
                "sha256": kit.digest(self.kit_content()),
                "cli": cli,
            }
            for cli in ("claude", "opencode")
            if self.target_for(cli).is_file()
        ]
        path = self.store() / MANIFEST
        if not files:
            path.unlink(missing_ok=True)
            return
        path.write_text(json.dumps({"files": files}), encoding="utf-8")

    def seed_kit(self, clis: list[str], edited: list[str] | None = None) -> None:
        for cli in clis:
            target = self.target_for(cli)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.kit_content())
        for cli in edited or []:
            self.edit_kit(cli)
        self.write_manifest()

    def edit_kit(self, cli: str) -> None:
        target = self.target_for(cli)
        target.write_bytes(target.read_bytes() + "моя правка\n".encode())

    def kit_text(self, cli: str) -> str:
        return self.target_for(cli).read_text(encoding="utf-8")

    def binary(self, tool: str) -> Path:
        path = self.bin_dir(tool) / (
            "agentschat.exe" if self.platform == "windows" else "agentschat"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("installed\n", encoding="utf-8")
        return path

    def bin_dir(self, tool: str) -> Path:
        return self.home / tool / "bin"

    def store(self) -> Path:
        directory = self.home / STORE
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def token(self, name: str = "claude-code") -> Path:
        path = self.store() / f"{name}.json"
        path.write_text(json.dumps({"agent": name, "token": "secret"}))
        return path

    def other(self, name: str, text: str) -> Path:
        path = self.store() / name
        path.write_text(text, encoding="utf-8")
        return path


class ParticipantCase(InstallerTestCase):
    def setUp(self):
        super().setUp()
        self.env = {
            "PATH": str(self.home / "pipx" / "bin"),
            "PATHEXT": ".COM;.EXE;.BAT;.CMD",
            "UV_TOOL_DIR": str(self.home / "uv" / "tools"),
            "PIPX_HOME": str(self.home / "pipx"),
        }
        self.machine = Machine(self.home)
        self.probe: Callable[[str], Probe] = lambda url: Probe(200, None)
        self.version = (3, 12)
        self.repo = self.home / "repo"
        self.uv_bin = self.home / "uv" / "bin" / "agentschat"
        self.pipx_bin = self.home / "pipx" / "bin" / "agentschat"

    def given(self, **values) -> boundaries:
        return boundaries(
            self.home,
            repo=self.repo,
            env=self.env,
            run=self.machine,
            probe=values.pop("probe", self.probe),
            platform=values.pop("platform", "linux"),
            **values,
        )

    def without_path(self) -> None:
        self.env["PATH"] = str(self.home / "nowhere")

    def roles(self):
        return (participant_role(version=self.version),)

    def install(self, *flags: str, **values):
        given = self.given(**values)
        return main(["--role", ROLE, *flags], given, self.roles()), given

    def remove(self, *flags: str, **values):
        return self.install(*flags, "--remove", **values)

    def record(self, entries: list[tuple[str, str]]) -> Path:
        path = participant.record_path(self.given())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"entries": [{"kind": kind, "id": id} for kind, id in entries]}),
            encoding="utf-8",
        )
        return path

    def recorded(self) -> list[str]:
        return Ownership.load(participant.record_path(self.given())).of_kind(
            participant.PACKAGE_KIND
        )

    def manifest(self) -> Path:
        return self.home / STORE / MANIFEST

    def plan_run(self):
        given = self.given()
        return self.run_for(
            given, {ROLE: Ownership.load(participant.record_path(given))}
        )

    def mentions(self, needle: str) -> bool:
        for path in self.home.rglob("*"):
            if path.is_file() and needle in path.read_text(
                encoding="utf-8", errors="replace"
            ):
                return True
        return False

    def leftover_block(self, given) -> list[str]:
        lines = given.stdout.getvalue().splitlines()
        return lines[lines.index("Убрано не всё, осталось в системе:") :]


class PackageMetadataTests(unittest.TestCase):
    def pyproject(self) -> str:
        root = Path(participant.__file__).resolve().parents[2]
        return (root / "pyproject.toml").read_text(encoding="utf-8")

    def test_the_python_floor_is_the_one_the_package_declares(self):
        declared = re.search(
            r'requires-python\s*=\s*">=(\d+)\.(\d+)"', self.pyproject()
        )
        self.assertEqual(
            participant.REQUIRED_PYTHON,
            (int(declared.group(1)), int(declared.group(2))),
        )

    def test_the_package_name_is_the_one_the_project_declares(self):
        self.assertIn(f'name = "{participant.PACKAGE}"', self.pyproject())


class ToolListingTests(unittest.TestCase):
    def probe(self, output: str):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)

        def run(argv):
            if Path(str(argv[0])).name != participant.PIPX.name:
                raise FileNotFoundError(argv[0])
            return completed(output)

        return make_run(
            boundaries(home, run=run),
            {ROLE: Ownership(participant.record_path(boundaries(home)))},
        )

    def test_a_listing_naming_the_package_reports_it_installed(self):
        self.assertTrue(
            participant.tool_reports_package(
                self.probe("quoroom 1.0.0rc1\n"), participant.PIPX
            )
        )

    def test_a_bulleted_uv_listing_reports_it_installed(self):
        self.assertTrue(
            participant.tool_reports_package(
                self.probe("- quoroom v1.0.0rc1\n"), participant.PIPX
            )
        )

    def test_a_listing_where_the_package_is_only_inside_a_path_is_not_an_installation(
        self,
    ):
        self.assertFalse(
            participant.tool_reports_package(
                self.probe("- /home/lab/quoroom-old v1\n"), participant.PIPX
            )
        )

    def test_a_listing_naming_another_package_is_not_an_installation(self):
        self.assertFalse(
            participant.tool_reports_package(
                self.probe("othertool 1.0\n"), participant.PIPX
            )
        )

    def test_a_uv_listing_names_the_package_on_the_first_line(self):
        self.assertEqual(
            participant.listed_names("quoroom v1.0.0rc1\n- quoroom\n"), {"quoroom"}
        )

    def test_a_pipx_listing_names_the_package_on_its_only_line(self):
        self.assertEqual(participant.listed_names("quoroom 1.0.0rc1\n"), {"quoroom"})

    def test_a_path_that_merely_mentions_the_package_is_not_a_match(self):
        self.assertNotIn(
            participant.PACKAGE, participant.listed_names("- /home/user/quoroom-old\n")
        )


class PrerequisiteTests(ParticipantCase):
    def test_a_python_below_the_floor_stops_before_any_command(self):
        self.version = (3, 9)
        code, given = self.install()
        self.assertEqual(code, HUMAN)
        self.assertEqual(self.machine.log, [])
        self.assertIn("requires-python", given.stdout.getvalue())

    def test_no_uv_and_no_pipx_is_a_human_step_naming_the_apt_command(self):
        self.machine.present = {"uv": False, "pipx": False}
        code, given = self.install()
        self.assertEqual(code, HUMAN)
        self.assertIn("apt install pipx", given.stdout.getvalue())

    def test_no_uv_and_no_pipx_on_windows_names_the_winget_command(self):
        self.machine.present = {"uv": False, "pipx": False}
        code, given = self.install(platform="windows")
        self.assertEqual(code, HUMAN)
        self.assertIn("winget install", given.stdout.getvalue())

    def test_uv_is_preferred_over_pipx_when_nothing_is_installed(self):
        self.machine.present = {"uv": True, "pipx": True}
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(
            f"uv tool install --editable {self.repo / 'bridge'}", self.machine.log
        )

    def test_pipx_is_used_when_uv_is_absent(self):
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(
            f"pipx install --editable {self.repo / 'bridge'}", self.machine.log
        )


class PackageInstallTests(ParticipantCase):
    def test_the_package_is_installed_editable_from_this_repositorys_bridge(self):
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertEqual(
            [line for line in self.machine.log if "install --editable" in line],
            [f"pipx install --editable {self.repo / 'bridge'}"],
        )

    def test_the_run_that_installed_the_package_records_the_tool(self):
        self.install()
        self.assertEqual(self.recorded(), ["pipx"])

    def test_a_failing_package_install_names_the_reason_and_records_nothing(self):
        self.machine.fails = "pipx install"
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn("не выполнил установку пакета", given.stderr.getvalue())
        self.assertEqual(self.recorded(), [])

    def test_an_installation_found_already_present_is_not_reinstalled(self):
        self.machine.installed_by.add("pipx")
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertFalse(any("install --editable" in line for line in self.machine.log))

    def test_an_installation_found_already_present_is_not_recorded(self):
        self.machine.installed_by.add("pipx")
        self.install()
        self.assertEqual(self.recorded(), [])

    def test_a_found_installation_is_reported_with_its_doubt(self):
        self.machine.installed_by.add("pipx")
        _, given = self.install()
        self.assertIn("другую копию репозитория", given.stderr.getvalue())
        self.assertIn("не как editable", given.stderr.getvalue())

    def test_a_pipx_installation_is_found_when_uv_is_also_present(self):
        self.machine.present = {"uv": True, "pipx": True}
        self.machine.installed_by.add("pipx")
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertFalse(any("install --editable" in line for line in self.machine.log))

    def test_a_pipx_installation_is_not_recorded_when_uv_is_also_present(self):
        self.machine.present = {"uv": True, "pipx": True}
        self.machine.installed_by.add("pipx")
        self.install()
        self.assertEqual(self.recorded(), [])

    def test_the_found_package_message_names_the_record_it_contradicts(self):
        self.record([(participant.PACKAGE_KIND, "uv")])
        self.machine.present = {"uv": True, "pipx": True}
        self.machine.installed_by.add("pipx")
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertIn("Запись установщика называет uv", given.stderr.getvalue())
        self.assertIn("уже установлен через pipx", given.stderr.getvalue())

    def test_the_recording_tool_wins_when_both_tools_report_the_package(self):
        self.record([(participant.PACKAGE_KIND, "pipx")])
        self.machine.present = {"uv": True, "pipx": True}
        self.machine.installed_by.update({"uv", "pipx"})
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )
        self.assertNotIn(f"{self.uv_bin} install", self.machine.log)

    def test_the_recording_tool_wins_over_a_uv_on_the_machine_for_the_path_hint(self):
        self.record([(participant.PACKAGE_KIND, "pipx")])
        self.machine.present = {"uv": True, "pipx": True}
        self.machine.installed_by.update({"uv", "pipx"})
        self.without_path()
        _, given = self.install()
        self.assertIn("pipx ensurepath", given.stdout.getvalue())
        self.assertNotIn("uv tool update-shell", given.stdout.getvalue())

    def test_the_kit_is_taken_from_the_tool_that_reports_the_package(self):
        self.machine.present = {"uv": True, "pipx": True}
        self.machine.installed_by.add("pipx")
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )
        self.assertNotIn(
            f"{self.uv_bin} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_the_path_hint_names_the_tool_that_reports_the_package(self):
        self.machine.present = {"uv": True, "pipx": True}
        self.machine.installed_by.add("pipx")
        self.without_path()
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertIn("pipx ensurepath", given.stdout.getvalue())
        self.assertNotIn("uv tool update-shell", given.stdout.getvalue())

    def test_a_recorded_package_is_verified_before_it_is_trusted(self):
        self.record([(participant.PACKAGE_KIND, "pipx")])
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(
            f"pipx install --editable {self.repo / 'bridge'}", self.machine.log
        )

    def test_a_repeat_install_installs_no_package_again(self):
        self.install()
        self.machine.log.clear()
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertFalse(any("install --editable" in line for line in self.machine.log))

    def test_a_repeat_install_says_the_package_step_is_already_done(self):
        self.install()
        _, given = self.install()
        self.assertIn("Поставить пакет quoroom: уже сделано.", given.stdout.getvalue())

    def test_a_repeat_install_keeps_the_record_it_wrote(self):
        self.install()
        self.install()
        self.assertEqual(self.recorded(), ["pipx"])


class KitInstallTests(ParticipantCase):
    def test_agentschat_is_called_by_the_absolute_path_of_the_installed_tool(self):
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_the_tool_is_asked_where_it_keeps_the_executable(self):
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertIn("pipx environment --value PIPX_BIN_DIR", self.machine.log)

    def test_uv_is_asked_where_it_keeps_the_executable(self):
        self.machine.present = {"uv": True, "pipx": False}
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertIn("uv tool dir --bin", self.machine.log)

    def test_a_tool_that_cannot_answer_falls_back_to_the_local_bin_directory(self):
        self.machine.fails = "pipx bin"
        given = self.given()
        run = self.run_for(
            given, {ROLE: Ownership.load(participant.record_path(given))}
        )
        self.assertEqual(
            participant.bin_dir(run, participant.PIPX),
            self.home / ".local" / "bin",
        )

    def test_agentschat_is_never_called_by_its_bare_name(self):
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertFalse(
            [line for line in self.machine.log if line.startswith("agentschat ")]
        )

    def test_an_install_after_a_partial_run_uses_the_recorded_tools_path(self):
        self.record([(participant.PACKAGE_KIND, "uv")])
        self.machine.present = {"uv": True, "pipx": True}
        self.machine.installed_by.add("uv")
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.uv_bin} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_an_install_after_a_partial_run_does_not_reinstall_the_package(self):
        self.record([(participant.PACKAGE_KIND, "pipx")])
        self.machine.installed_by.add("pipx")
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertFalse(any("install --editable" in line for line in self.machine.log))

    def test_only_claude_is_chosen_by_flag(self):
        code, _ = self.install("--claude")
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --claude {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_only_opencode_is_chosen_by_flag(self):
        code, _ = self.install("--opencode")
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_an_interactive_run_without_flags_asks_which_clis(self):
        code, given = self.install(stdin="1\n", interactive=True)
        self.assertEqual(code, DONE)
        self.assertIn("Какие CLI получают набор?", given.stdout.getvalue())
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --claude {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_an_interactive_run_can_be_answered_with_both_clis(self):
        code, _ = self.install(stdin="3\n", interactive=True)
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_an_interactive_repeat_run_is_not_asked_again(self):
        self.install("--claude", "--opencode")
        code, given = self.install(stdin="", interactive=True)
        self.assertEqual(code, DONE)
        self.assertNotIn("Какие CLI получают набор?", given.stdout.getvalue())

    def test_an_unreadable_answer_to_the_cli_question_names_the_flags(self):
        code, given = self.install(stdin="чем\n", interactive=True)
        self.assertEqual(code, FAILED)
        self.assertIn("--claude", given.stderr.getvalue())
        self.assertIn("--opencode", given.stderr.getvalue())

    def test_a_conflict_is_reported_as_the_reason_of_the_failed_step(self):
        self.machine.kit_conflict = True
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn("Причина: конфликт набора Quoroom", given.stderr.getvalue())

    def test_a_conflict_never_turns_into_a_forced_install(self):
        self.machine.kit_conflict = True
        self.install()
        self.assertFalse(any("--force" in line for line in self.machine.log))

    def test_the_client_is_asked_for_its_report_by_a_flag(self):
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_the_clients_own_words_are_not_echoed_into_the_installers_report(self):
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertNotIn(NOISE, given.stdout.getvalue())
        self.assertEqual(
            [
                line
                for line in given.stdout.getvalue().splitlines()
                if line.startswith("{")
            ],
            [],
        )

    def test_the_clients_own_words_do_not_reach_a_removal_report_either(self):
        self.install()
        self.machine.log.clear()
        code, given = self.remove()
        self.assertEqual(code, DONE)
        self.assertNotIn(NOISE, given.stdout.getvalue())
        self.assertNotIn(NOISE, given.stderr.getvalue())

    def test_the_kit_is_refreshed_on_every_run(self):
        self.install()
        self.machine.log.clear()
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_the_path_comes_from_the_reporting_tool_when_the_record_names_another(self):
        self.record([(participant.PACKAGE_KIND, "uv")])
        self.machine.present = {"uv": True, "pipx": True}
        self.machine.installed_by.add("pipx")
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )
        self.assertNotIn(
            f"{self.uv_bin} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_a_refresh_covers_the_new_cli_and_the_one_the_manifest_holds(self):
        self.machine.installed_by.add("pipx")
        self.machine.seed_kit(["claude"])
        code, _ = self.install("--opencode")
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_a_refresh_covers_the_clis_the_manifest_already_holds(self):
        self.machine.installed_by.add("pipx")
        self.machine.seed_kit(["claude"])
        code, _ = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --claude {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_an_edited_listed_file_survives_a_rerun(self):
        self.install()
        self.machine.edit_kit("claude")
        self.install()
        self.assertIn("моя правка", self.machine.kit_text("claude"))

    def test_an_edited_listed_cli_is_not_reinstalled(self):
        self.install()
        self.machine.edit_kit("claude")
        self.machine.log.clear()
        self.install()
        calls = [line for line in self.machine.log if "agentschat install" in line]
        self.assertEqual(len(calls), 1)
        self.assertIn("--opencode", calls[0])
        self.assertNotIn("--claude", calls[0])

    def test_an_edited_listed_file_is_reported_by_name(self):
        self.install()
        self.machine.edit_kit("claude")
        _, given = self.install()
        self.assertIn("Набор для claude", given.stdout.getvalue())
        self.assertIn(str(self.machine.target_for("claude")), given.stdout.getvalue())
        self.assertIn("изменённые вручную, оставлены как есть", given.stdout.getvalue())

    def test_the_report_says_that_the_next_install_will_overwrite_it(self):
        self.install()
        self.machine.edit_kit("claude")
        _, given = self.install()
        self.assertIn("перезапишет", given.stdout.getvalue())

    def test_an_unedited_kit_is_still_refreshed(self):
        self.install()
        self.machine.log.clear()
        self.install()
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_a_missing_listed_file_is_treated_as_refreshable(self):
        self.install()
        self.machine.target_for("claude").unlink()
        self.machine.log.clear()
        self.install()
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_a_new_cli_is_installed_while_another_one_is_edited(self):
        self.install("--claude")
        self.machine.edit_kit("claude")
        code, _ = self.install("--opencode")
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} install --lang ru --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )
        self.assertIn("моя правка", self.machine.kit_text("claude"))

    def test_the_windows_binary_is_named_with_its_extension(self):
        code, _ = self.install(platform="windows")
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.home / 'pipx' / 'bin' / 'agentschat.exe'} install --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )


class KitReportTests(ParticipantCase):
    """Ответ клиента читается как отчёт, а не как его предложения."""

    def test_a_conflict_is_recognised_from_the_code_the_client_reports(self):
        self.machine.kit_conflict = True
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn("Причина: конфликт набора Quoroom", given.stderr.getvalue())

    def test_a_conflict_names_the_file_the_report_blames(self):
        foreign = self.machine.target_for("claude")
        self.machine.kit_conflict = True
        _, given = self.install()
        self.assertIn(str(foreign), given.stderr.getvalue())

    def test_a_conflict_is_a_conflict_whatever_code_the_client_exits_with(self):
        self.machine.kit_conflict = True
        self.machine.kit_conflict_code = 1
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn("Причина: конфликт набора Quoroom", given.stderr.getvalue())

    def test_a_refusal_spelled_out_by_the_client_is_not_read_as_a_conflict(self):
        self.machine.kit_answers = "words"
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn("Причина: agentschat не отработал", given.stderr.getvalue())
        self.assertNotIn("конфликт набора Quoroom", given.stderr.getvalue())

    def test_a_client_that_answers_with_nothing_is_not_believed_to_have_written(self):
        self.machine.kit_answers = "nothing"
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn("Причина: agentschat не отработал", given.stderr.getvalue())

    def test_unrelated_words_around_the_report_make_it_no_report_at_all(self):
        self.machine.kit_answers = "wrapped"
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn("Причина: agentschat не отработал", given.stderr.getvalue())

    def test_unrelated_words_of_the_client_change_nothing_in_a_finished_install(self):
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(RESTART, given.stdout.getvalue())

    def test_a_conflict_the_client_exits_zero_with_is_still_a_conflict(self):
        self.machine.kit_conflict = True
        self.machine.kit_conflict_code = 0
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn("Причина: конфликт набора Quoroom", given.stderr.getvalue())

    def test_a_conflict_says_that_nothing_was_written_and_how_to_force_it(self):
        self.machine.kit_conflict = True
        _, given = self.install()
        said = given.stderr.getvalue()
        self.assertIn("ничего не записано", said)
        self.assertIn("отличаются от набора Quoroom", said)
        self.assertIn("повторите с --force", said)

    def test_a_refusal_that_blames_no_file_does_not_leave_the_reason_empty(self):
        blank = kit.Report(kit.COMMAND_INSTALL, kit.CODE_CONFLICT).as_json()
        said = participant.kit_failure(
            self.plan_run(), completed(blank, "", 1), kit.COMMAND_INSTALL
        )
        self.assertIn(blank, said)

    def test_the_restart_hint_follows_the_report_rather_than_the_files_on_disk(self):
        self.machine.kit_claims_no_writes = True
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertNotIn(RESTART, given.stdout.getvalue())
        self.assertIn("Набор на месте и не менялся", given.stdout.getvalue())

    def test_the_report_of_the_removal_is_asked_for_by_a_flag(self):
        self.install()
        self.machine.log.clear()
        code, _ = self.remove()
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} uninstall --lang ru --claude --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )


class BrokerAddressTests(ParticipantCase):
    def test_the_default_address_is_named_in_the_report(self):
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(
            f"Брокер отвечает на {participant.DEFAULT_BROKER}", given.stdout.getvalue()
        )

    def test_the_default_address_writes_nothing_into_the_home(self):
        self.install()
        self.assertFalse(self.mentions("AGENTSCHAT_URL"))

    def test_the_default_address_prints_no_environment_command(self):
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertNotIn("AGENTSCHAT_URL", given.stdout.getvalue())
        self.assertNotIn("setx", given.stdout.getvalue())
        self.assertNotIn("printf", given.stdout.getvalue())

    def test_another_address_is_printed_with_the_windows_command(self):
        code, given = self.install(
            "--broker-url", "http://10.0.0.5:8770", platform="windows"
        )
        self.assertEqual(code, DONE)
        self.assertIn(
            'setx AGENTSCHAT_URL "http://10.0.0.5:8770"', given.stdout.getvalue()
        )

    def test_another_address_is_still_written_into_no_profile(self):
        self.install("--broker-url", "http://10.0.0.5:8770")
        self.assertFalse(self.mentions("AGENTSCHAT_URL"))
        self.assertFalse((self.home / ".profile").exists())

    def test_the_probe_asks_the_chosen_address(self):
        asked: list[str] = []
        self.install(
            "--broker-url",
            "http://10.0.0.5:8770/",
            probe=lambda url: asked.append(url) or Probe(200, None),
        )
        self.assertEqual(asked, ["http://10.0.0.5:8770" + STATUS])

    def test_a_trailing_slash_does_not_double_up_in_the_probe(self):
        asked: list[str] = []
        self.install(probe=lambda url: asked.append(url) or Probe(200, None))
        self.assertEqual(asked, [participant.DEFAULT_BROKER + STATUS])


class PrintedAddressCommandTests(ParticipantCase):
    """Напечатанная команда адреса должна отработать в настоящем sh."""

    def setUp(self):
        super().setUp()
        if not SH:
            self.skipTest(
                "posix sh не найден в PATH: напечатанную команду нечем выполнить"
            )

    def printed(self, url: str) -> str:
        code, given = self.install("--broker-url", url)
        self.assertEqual(code, DONE)
        row = next(
            line for line in given.stdout.getvalue().splitlines() if "printf" in line
        )
        return row.split(": ", 1)[1]

    def sh(self, script: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [SH, "-c", script],
            env={**os.environ, "HOME": posix_path(self.home)},
            capture_output=True,
            encoding="utf-8",
        )

    def profile_after(self, url: str) -> bytes:
        done = self.sh(self.printed(url))
        self.assertEqual(done.returncode, 0, done.stderr)
        return (self.home / ".profile").read_bytes()

    def test_a_plain_address_reaches_the_profile_byte_for_byte(self):
        self.assertEqual(
            self.profile_after("http://10.0.0.5:8770"),
            b"export AGENTSCHAT_URL=http://10.0.0.5:8770\n",
        )

    def test_an_address_with_a_dollar_is_not_expanded_in_the_profile(self):
        self.assertEqual(
            self.profile_after("http://10.0.0.5:8770/$x"),
            b"export AGENTSCHAT_URL='http://10.0.0.5:8770/$x'\n",
        )

    def test_an_address_with_an_ampersand_keeps_the_whole_profile_line(self):
        self.assertEqual(
            self.profile_after("http://10.0.0.5:8770/?a=1&b=2"),
            b"export AGENTSCHAT_URL='http://10.0.0.5:8770/?a=1&b=2'\n",
        )

    def test_an_address_with_a_quote_keeps_its_value_when_the_profile_is_read(self):
        self.profile_after("http://10.0.0.5:8770/a'b")
        done = self.sh('. ~/.profile; printf %s "$AGENTSCHAT_URL"')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, "http://10.0.0.5:8770/a'b")


class BrokerProbeTests(ParticipantCase):
    def offline(self, url: str) -> Probe:
        return Probe(None, "отказано в соединении")

    def test_a_reachable_broker_finishes_the_run(self):
        code, _ = self.install()
        self.assertEqual(code, DONE)

    def test_an_http_error_status_is_still_a_reachable_broker(self):
        code, _ = self.install(probe=lambda url: Probe(503, None))
        self.assertEqual(code, DONE)

    def test_an_unreachable_broker_fails_the_run(self):
        code, _ = self.install(probe=self.offline)
        self.assertEqual(code, FAILED)

    def test_an_unreachable_broker_names_the_address_and_the_reason(self):
        code, given = self.install(probe=self.offline)
        self.assertEqual(code, FAILED)
        self.assertIn(
            f"брокер не отвечает на {participant.DEFAULT_BROKER}",
            given.stderr.getvalue(),
        )
        self.assertIn("отказано в соединении", given.stderr.getvalue())

    def test_an_unreachable_broker_names_the_steps_that_survived(self):
        code, given = self.install(probe=self.offline)
        self.assertEqual(code, FAILED)
        self.assertIn("Обновить набор по CLI агентов", given.stderr.getvalue())

    def test_an_unreachable_broker_says_a_rerun_after_the_server_finishes_the_check(
        self,
    ):
        code, given = self.install(probe=self.offline)
        self.assertEqual(code, FAILED)
        self.assertIn("после запуска сервера", given.stderr.getvalue())

    def test_an_unreachable_broker_names_the_address_command_of_another_address(self):
        code, given = self.install(
            "--broker-url", "http://10.0.0.5:8770", probe=self.offline
        )
        self.assertEqual(code, FAILED)
        self.assertIn("export AGENTSCHAT_URL", given.stderr.getvalue())

    def test_an_unreachable_broker_still_hints_the_path_fix(self):
        self.without_path()
        code, given = self.install(probe=self.offline)
        self.assertEqual(code, FAILED)
        self.assertIn("pipx ensurepath", given.stderr.getvalue())

    def test_the_installed_state_survives_an_unreachable_broker(self):
        self.install(probe=self.offline)
        self.assertEqual(self.recorded(), ["pipx"])
        self.assertTrue(self.manifest().is_file())

    def test_a_rerun_after_the_broker_starts_only_finishes_the_check(self):
        self.install(probe=self.offline)
        self.machine.log.clear()
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertFalse(any("install --editable" in line for line in self.machine.log))
        self.assertIn("/chatlogin", given.stdout.getvalue())


class ReportTests(ParticipantCase):
    def test_the_report_ends_with_the_chatlogin_step(self):
        _, given = self.install()
        self.assertIn("/chatlogin", given.stdout.getvalue())

    def test_the_report_names_the_restart_before_the_chatlogin_step(self):
        _, given = self.install()
        last = given.stdout.getvalue().splitlines()[-1]
        self.assertTrue(last.endswith("выполните /chatlogin и назовите имя сессии."))
        self.assertIn(RESTART, last)

    def test_the_restart_line_names_only_the_chosen_cli(self):
        _, given = self.install("--claude")
        last = given.stdout.getvalue().splitlines()[-1]
        self.assertIn("Claude Code", last)
        self.assertNotIn("OpenCode", last)

    def test_a_repeat_install_still_names_the_chatlogin_step(self):
        self.install()
        _, given = self.install()
        self.assertIn("/chatlogin", given.stdout.getvalue())
        self.assertIn("перезапускать сессии не нужно", given.stdout.getvalue())

    def test_the_report_names_the_broker_as_answering(self):
        _, given = self.install()
        self.assertIn("Брокер отвечает на", given.stdout.getvalue())

    def test_the_report_claims_nothing_about_a_session_in_the_room(self):
        _, given = self.install()
        self.assertNotIn("в комнату", given.stdout.getvalue())

    def test_a_first_install_asks_the_sessions_to_restart(self):
        _, given = self.install()
        self.assertIn(RESTART, given.stdout.getvalue())

    def test_a_repeat_install_with_nothing_changed_asks_for_no_restart(self):
        self.install()
        _, given = self.install()
        self.assertNotIn(RESTART, given.stdout.getvalue())
        self.assertIn("Набор на месте и не менялся", given.stdout.getvalue())

    def test_the_path_hint_names_the_reporting_tool_when_the_record_names_another(self):
        self.record([(participant.PACKAGE_KIND, "uv")])
        self.machine.present = {"uv": True, "pipx": True}
        self.machine.installed_by.add("pipx")
        self.without_path()
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertIn("pipx ensurepath", given.stdout.getvalue())
        self.assertNotIn("uv tool update-shell", given.stdout.getvalue())

    def test_a_present_path_is_not_complained_about(self):
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertNotIn("не нашёлся в PATH", given.stdout.getvalue())

    def test_a_missing_path_is_reported_with_the_pipx_command(self):
        self.without_path()
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertIn("pipx ensurepath", given.stdout.getvalue())

    def test_a_missing_path_names_the_uv_command_when_uv_installed(self):
        self.machine.present = {"uv": True, "pipx": True}
        self.without_path()
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertIn("uv tool update-shell", given.stdout.getvalue())

    def test_a_missing_path_says_a_new_terminal_and_restarted_sessions(self):
        self.without_path()
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertIn(
            "откройте новый терминал и перезапустите сессии", given.stdout.getvalue()
        )

    def test_a_windows_executable_on_path_answers_through_pathext(self):
        (self.home / "elsewhere").mkdir()
        (self.home / "elsewhere" / "agentschat.exe").write_text("x", encoding="utf-8")
        self.env["PATH"] = str(self.home / "elsewhere")
        code, given = self.install(platform="windows")
        self.assertEqual(code, DONE)
        self.assertNotIn("не нашёлся в PATH", given.stdout.getvalue())

    def test_a_windows_binary_without_its_extension_on_path_is_not_found(self):
        (self.home / "elsewhere").mkdir()
        (self.home / "elsewhere" / "agentschat").write_text("x", encoding="utf-8")
        self.env["PATH"] = str(self.home / "elsewhere")
        code, given = self.install(platform="windows")
        self.assertEqual(code, DONE)
        self.assertIn("не нашёлся в PATH", given.stdout.getvalue())

    def test_the_path_is_read_from_the_environment_and_not_from_a_subprocess(self):
        self.without_path()
        self.install()
        self.assertFalse([line for line in self.machine.log if "--help" in line])

    def test_a_path_entry_that_holds_agentschat_is_found(self):
        (self.home / "elsewhere").mkdir()
        (self.home / "elsewhere" / "agentschat").write_text("x", encoding="utf-8")
        self.env["PATH"] = str(self.home / "elsewhere")
        code, given = self.install()
        self.assertEqual(code, DONE)
        self.assertNotIn("не нашёлся в PATH", given.stdout.getvalue())


class RemovalTests(ParticipantCase):
    def installed(self) -> None:
        self.assertEqual(self.install()[0], DONE)
        self.machine.log.clear()

    def test_the_kit_is_removed_before_the_package(self):
        self.installed()
        code, _ = self.remove()
        self.assertEqual(code, DONE)
        kit = self.machine.log.index(
            f"{self.pipx_bin} uninstall --lang ru --claude --opencode {participant.JSON_FLAG}"
        )
        package = self.machine.log.index("pipx uninstall quoroom")
        self.assertLess(kit, package)

    def test_the_cli_flags_narrow_the_kit_removal(self):
        self.installed()
        code, _ = self.remove("--opencode")
        self.assertEqual(code, DONE)
        self.assertIn(
            f"{self.pipx_bin} uninstall --lang ru --opencode {participant.JSON_FLAG}",
            self.machine.log,
        )

    def test_a_narrowed_removal_keeps_the_package_the_other_cli_calls(self):
        self.installed()
        code, _ = self.remove("--claude")
        self.assertEqual(code, DONE)
        self.assertNotIn("pipx uninstall quoroom", self.machine.log)

    def test_a_narrowed_removal_keeps_the_record_of_the_package(self):
        self.installed()
        self.remove("--claude")
        self.assertEqual(self.recorded(), ["pipx"])

    def test_a_narrowed_removal_says_who_still_uses_the_package(self):
        self.installed()
        _, given = self.remove("--claude")
        self.assertIn(
            "пакет quoroom оставлен: им пользуется набор для opencode",
            given.stdout.getvalue(),
        )

    def test_a_narrowed_removal_warns_on_stderr_who_still_uses_the_package(self):
        self.installed()
        _, given = self.remove("--claude")
        self.assertIn(
            "пакет quoroom оставлен: им пользуется набор для opencode",
            given.stderr.getvalue(),
        )

    def test_a_narrowed_removal_says_which_cli_it_did_not_touch(self):
        self.installed()
        _, given = self.remove("--claude")
        self.assertIn("набор для opencode не снимался", given.stdout.getvalue())

    def test_a_full_removal_with_an_edited_file_removes_the_package(self):
        self.installed()
        self.machine.edit_kit("claude")
        code, _ = self.remove()
        self.assertEqual(code, DONE)
        self.assertIn("pipx uninstall quoroom", self.machine.log)

    def test_a_full_removal_with_an_edited_file_removes_the_package_again(self):
        self.installed()
        self.machine.edit_kit("claude")
        self.remove()
        self.machine.log.clear()
        code, _ = self.remove()
        self.assertEqual(code, DONE)
        self.assertNotIn("pipx uninstall quoroom", self.machine.log)

    def test_an_edited_file_of_an_untouched_cli_still_holds_the_package(self):
        self.installed()
        self.machine.edit_kit("claude")
        code, given = self.remove("--opencode")
        self.assertEqual(code, DONE)
        self.assertNotIn("pipx uninstall quoroom", self.machine.log)
        self.assertIn(
            "пакет quoroom оставлен: им пользуется набор для claude",
            given.stdout.getvalue(),
        )

    def test_a_full_removal_that_empties_the_manifest_removes_the_package(self):
        self.installed()
        code, _ = self.remove()
        self.assertEqual(code, DONE)
        self.assertIn("pipx uninstall quoroom", self.machine.log)

    def test_a_narrowed_removal_keeps_the_other_cli_in_the_manifest(self):
        self.installed()
        code, _ = self.remove("--opencode")
        self.assertEqual(code, DONE)
        self.assertEqual(
            sorted(
                item["cli"]
                for item in json.loads(self.manifest().read_text(encoding="utf-8"))[
                    "files"
                ]
            ),
            ["claude"],
        )

    def test_the_files_the_kit_keeps_are_reported(self):
        self.installed()
        self.machine.edit_kit("claude")
        code, given = self.remove()
        self.assertEqual(code, DONE)
        self.assertIn("изменённые вручную", given.stdout.getvalue())

    def test_a_kept_manifest_survives_the_removal(self):
        self.installed()
        self.machine.edit_kit("claude")
        code, _ = self.remove()
        self.assertEqual(code, DONE)
        self.assertTrue(self.manifest().is_file())

    def test_the_package_is_removed_with_the_tool_that_installed_it(self):
        self.machine.present = {"uv": True, "pipx": True}
        self.install()
        self.machine.log.clear()
        code, _ = self.remove()
        self.assertEqual(code, DONE)
        self.assertIn("uv tool uninstall quoroom", self.machine.log)
        self.assertNotIn("pipx uninstall quoroom", self.machine.log)

    def test_a_pipx_record_wins_over_the_uv_on_the_machine(self):
        self.record([(participant.PACKAGE_KIND, "pipx")])
        self.machine.present = {"uv": True, "pipx": True}
        self.machine.installed_by.add("pipx")
        code, _ = self.remove()
        self.assertEqual(code, DONE)
        self.assertIn("pipx uninstall quoroom", self.machine.log)
        self.assertNotIn("uv tool uninstall", self.machine.log)

    def test_a_package_only_pipx_reports_is_not_removed_when_the_record_says_uv(self):
        self.record([(participant.PACKAGE_KIND, "uv")])
        self.machine.present = {"uv": True, "pipx": True}
        self.machine.installed_by.add("pipx")
        code, given = self.remove()
        self.assertEqual(code, DONE)
        self.assertNotIn("pipx uninstall quoroom", self.machine.log)
        self.assertNotIn("uv tool uninstall quoroom", self.machine.log)
        self.assertIn("а его в системе нет", given.stderr.getvalue())

    def test_the_record_of_the_removed_package_is_forgotten(self):
        self.installed()
        self.remove()
        self.assertFalse(participant.record_path(self.given()).exists())

    def test_the_empty_installer_home_is_removed_with_the_record(self):
        self.installed()
        self.remove()
        self.assertFalse((self.home / participant.INSTALLER_HOME).exists())

    def test_a_record_whose_package_is_gone_is_reported_and_dropped(self):
        self.record([(participant.PACKAGE_KIND, "pipx")])
        code, given = self.remove()
        self.assertEqual(code, DONE)
        self.assertIn("а его в системе нет", given.stderr.getvalue())
        self.assertFalse(participant.record_path(self.given()).exists())

    def test_a_package_the_installer_did_not_record_is_kept_and_reported(self):
        self.machine.installed_by.add("pipx")
        code, given = self.remove()
        self.assertEqual(code, DONE)
        self.assertNotIn("pipx uninstall quoroom", self.machine.log)
        self.assertIn("не записан за установщиком", given.stderr.getvalue())

    def test_removal_after_a_partial_install_removes_what_was_installed(self):
        self.record([(participant.PACKAGE_KIND, "pipx")])
        self.machine.installed_by.add("pipx")
        code, _ = self.remove()
        self.assertEqual(code, DONE)
        self.assertIn("pipx uninstall quoroom", self.machine.log)
        self.assertNotIn(f"{self.pipx_bin} uninstall", self.machine.log)

    def test_removal_is_repeatable_and_removes_nothing_twice(self):
        self.installed()
        self.remove()
        self.machine.log.clear()
        code, _ = self.remove()
        self.assertEqual(code, DONE)
        self.assertFalse(any("uninstall" in line for line in self.machine.log))

    def test_a_missing_agentschat_leaves_the_manifest_and_says_so(self):
        self.installed()
        self.pipx_bin.unlink()
        code, given = self.remove()
        self.assertEqual(code, DONE)
        self.assertIn("agentschat не установлен", given.stderr.getvalue())
        self.assertTrue(self.manifest().is_file())

    def test_a_missing_agentschat_is_named_as_the_reason_the_kit_stays(self):
        self.installed()
        self.pipx_bin.unlink()
        _, given = self.remove()
        self.assertIn(
            "набор не снят: agentschat не найден, поэтому его файлы и записи остались",
            given.stdout.getvalue(),
        )

    def test_a_missing_agentschat_names_the_files_it_left_behind(self):
        self.installed()
        self.pipx_bin.unlink()
        _, given = self.remove()
        for cli in ("claude", "opencode"):
            self.assertIn(str(self.machine.target_for(cli)), given.stdout.getvalue())

    def test_a_missing_agentschat_is_not_reported_as_files_the_kit_kept(self):
        self.installed()
        self.pipx_bin.unlink()
        _, given = self.remove()
        self.assertNotIn("uninstall оставил", given.stdout.getvalue())

    def test_a_missing_agentschat_keeps_the_package_that_the_kit_calls(self):
        self.installed()
        self.pipx_bin.unlink()
        code, _ = self.remove()
        self.assertEqual(code, DONE)
        self.assertNotIn("pipx uninstall quoroom", self.machine.log)

    def test_a_missing_agentschat_keeps_the_record_of_the_package(self):
        self.installed()
        self.pipx_bin.unlink()
        self.remove()
        self.assertEqual(self.recorded(), ["pipx"])

    def test_a_removal_after_the_package_is_gone_names_only_the_kit(self):
        self.installed()
        self.machine.edit_kit("claude")
        self.remove()
        self.pipx_bin.unlink()
        _, given = self.remove()
        self.assertIn("набор не снят: agentschat не найден", given.stdout.getvalue())
        self.assertNotIn(
            f"пакет {participant.PACKAGE} оставлен", given.stdout.getvalue()
        )
        self.assertNotIn(f"пакет {participant.PACKAGE} (", given.stdout.getvalue())
        self.assertNotIn(
            f"пакет {participant.PACKAGE} оставлен", given.stderr.getvalue()
        )

    def test_kept_files_are_told_that_they_call_a_missing_agentschat(self):
        self.installed()
        self.machine.edit_kit("claude")
        code, given = self.remove()
        self.assertEqual(code, DONE)
        self.assertIn(
            "Файлы набора вызывают agentschat, которого больше нет:",
            given.stdout.getvalue(),
        )

    def test_kept_files_are_named_in_the_report_under_their_reason(self):
        self.installed()
        self.machine.edit_kit("claude")
        _, given = self.remove()
        self.assertIn(
            f"        {self.machine.target_for('claude')}", self.leftover_block(given)
        )

    def test_the_missing_agentschat_warning_says_how_to_end_it(self):
        self.installed()
        self.machine.edit_kit("claude")
        _, given = self.remove()
        self.assertIn(
            "удалите их или поставьте участника снова.", given.stdout.getvalue()
        )

    def test_a_kept_package_is_not_told_that_agentschat_is_gone(self):
        self.installed()
        self.machine.edit_kit("claude")
        code, given = self.remove("--claude")
        self.assertEqual(code, DONE)
        self.assertIn(
            f"        {self.machine.target_for('claude')}", self.leftover_block(given)
        )
        self.assertNotIn("agentschat, которого больше нет", given.stdout.getvalue())

    def test_each_path_is_printed_under_the_reason_that_left_it(self):
        self.installed()
        self.machine.edit_kit("claude")
        _, given = self.remove("--claude")
        lines = given.stdout.getvalue().splitlines()
        reason = "    файлы набора для claude, изменённые вручную, uninstall оставил"
        package = "    пакет quoroom оставлен: им пользуется набор для opencode"
        path = f"        {self.machine.target_for('claude')}"
        self.assertEqual(lines[lines.index(reason) + 1], path)
        self.assertNotEqual(lines[lines.index(package) + 1], path)

    def test_an_unrecorded_package_is_not_told_that_agentschat_is_gone(self):
        self.machine.installed_by.add("pipx")
        self.machine.binary("pipx")
        self.machine.seed_kit(["claude"])
        self.machine.edit_kit("claude")
        code, given = self.remove()
        self.assertEqual(code, DONE)
        self.assertNotIn("pipx uninstall quoroom", self.machine.log)
        self.assertIn(
            f"        {self.machine.target_for('claude')}", self.leftover_block(given)
        )
        self.assertNotIn("agentschat, которого больше нет", given.stdout.getvalue())

    def test_each_leftover_is_printed_on_its_own_line(self):
        self.installed()
        self.machine.edit_kit("claude")
        _, given = self.remove("--opencode")
        lines = given.stdout.getvalue().splitlines()
        self.assertIn(
            "    набор для claude не снимался: его не называл ключ запуска", lines
        )
        self.assertIn(
            "    пакет quoroom оставлен: им пользуется набор для claude", lines
        )

    def test_a_failing_kit_removal_is_reported_and_stops_the_run(self):
        self.installed()
        self.machine.fails = "kit uninstall"
        code, given = self.remove()
        self.assertEqual(code, FAILED)
        self.assertIn("agentschat не отработал", given.stderr.getvalue())

    def test_the_removal_report_says_the_session_files_stay(self):
        self.installed()
        _, given = self.remove()
        self.assertIn(f"Файлы сессий в {STORE} оставлены", given.stdout.getvalue())

    def test_a_removed_package_sends_the_session_back_through_chatlogin(self):
        self.installed()
        _, given = self.remove()
        self.assertIn(
            f"Файлы сессий в {STORE} оставлены: после повторной установки сессия "
            "вернётся в комнату через /chatlogin.",
            given.stdout.getvalue(),
        )

    def test_a_kept_package_offers_the_new_login_right_away(self):
        self.machine.installed_by.add("pipx")
        _, given = self.remove()
        self.assertIn(
            f"Файлы сессий в {STORE} оставлены: вернуться в комнату можно новым входом.",
            given.stdout.getvalue(),
        )

    def test_a_repeat_removal_keeps_sending_the_session_back_through_chatlogin(self):
        self.installed()
        self.remove()
        _, given = self.remove()
        text = given.stdout.getvalue()
        self.assertIn(
            f"Файлы сессий в {STORE} оставлены: после повторной установки сессия "
            "вернётся в комнату через /chatlogin.",
            text,
        )
        self.assertNotIn("вернуться в комнату можно новым входом", text)

    def test_a_complete_removal_says_nothing_is_left(self):
        self.installed()
        _, given = self.remove()
        self.assertIn("Набор и пакет убраны.", given.stdout.getvalue())

    def test_the_report_does_not_claim_a_kept_package_was_removed(self):
        self.machine.installed_by.add("pipx")
        _, given = self.remove()
        self.assertNotIn("Набор и пакет убраны.", given.stdout.getvalue())

    def test_the_report_names_a_kept_package_with_its_tool(self):
        self.machine.installed_by.add("pipx")
        _, given = self.remove()
        self.assertIn(f"пакет {participant.PACKAGE} (pipx)", given.stdout.getvalue())

    def test_the_report_does_not_claim_a_kept_manifest_was_removed(self):
        self.installed()
        self.machine.edit_kit("claude")
        _, given = self.remove()
        self.assertNotIn("Набор и пакет убраны.", given.stdout.getvalue())

    def test_the_report_does_not_claim_a_package_behind_edited_files_stays(self):
        self.installed()
        self.machine.edit_kit("claude")
        _, given = self.remove()
        self.assertNotIn(
            f"пакет {participant.PACKAGE} оставлен", given.stdout.getvalue()
        )

    def test_the_report_names_the_files_the_kit_kept(self):
        self.installed()
        self.machine.edit_kit("claude")
        _, given = self.remove()
        self.assertIn(
            "файлы набора для claude, изменённые вручную, uninstall оставил",
            given.stdout.getvalue(),
        )

    def test_the_removal_report_names_the_install_command_of_the_platform(self):
        self.installed()
        _, given = self.remove()
        self.assertIn("install.sh --role participant", given.stdout.getvalue())

    def test_the_removal_report_on_windows_names_the_windows_command(self):
        self.installed()
        _, given = self.remove(platform="windows")
        self.assertIn("install.ps1 --role participant", given.stdout.getvalue())

    def test_the_broker_is_not_probed_during_a_removal(self):
        self.installed()
        asked: list[str] = []
        self.remove(probe=lambda url: asked.append(url) or Probe(200, None))
        self.assertEqual(asked, [])

    def test_a_removal_needs_no_kit_choice_answer(self):
        self.installed()
        code, _ = self.remove(stdin="", interactive=True)
        self.assertEqual(code, DONE)
        self.assertFalse(
            [line for line in self.machine.log if "agentschat install" in line]
        )


class PurgeTests(ParticipantCase):
    def stored(self) -> None:
        self.machine.token("claude-code")
        self.machine.token("opencode")
        self.machine.installed_by.add("pipx")
        self.machine.seed_kit(["claude"])

    def purge(self, answer: str = "PURGE\n", **values):
        return self.remove("--purge", stdin=answer, **values)

    def test_a_confirmed_purge_deletes_the_broker_token_files(self):
        self.stored()
        code, _ = self.purge()
        self.assertEqual(code, DONE)
        self.assertFalse((self.home / STORE / "claude-code.json").exists())
        self.assertFalse((self.home / STORE / "opencode.json").exists())

    def test_a_confirmed_purge_asks_before_anything_is_deleted(self):
        self.stored()
        _, given = self.purge(answer="нет\n")
        self.assertIn("PURGE", given.stdout.getvalue())
        self.assertIn("claude-code.json", given.stdout.getvalue())

    def test_a_cancelled_purge_changes_nothing(self):
        self.stored()
        code, _ = self.purge(answer="нет\n")
        self.assertEqual(code, CANCELLED)
        self.assertTrue((self.home / STORE / "claude-code.json").is_file())
        self.assertTrue((self.home / STORE / "opencode.json").is_file())
        self.assertTrue(self.manifest().is_file())

    def test_a_purge_never_offers_the_kit_manifest(self):
        self.stored()
        _, given = self.purge(answer="нет\n")
        self.assertNotIn(MANIFEST, given.stdout.getvalue())

    def test_the_kit_manifest_survives_a_purge_that_kept_an_edited_file(self):
        self.stored()
        self.machine.edit_kit("claude")
        code, _ = self.purge()
        self.assertEqual(code, DONE)
        self.assertTrue(self.manifest().is_file())

    def test_the_purge_report_does_not_repeat_the_removal_reasons(self):
        self.install()
        self.machine.token("claude-code")
        self.machine.edit_kit("claude")
        _, given = self.purge()
        reason = "файлы набора для claude, изменённые вручную, uninstall оставил"
        self.assertEqual(given.stdout.getvalue().count(reason), 1)

    def test_a_repeat_purge_after_the_package_is_gone_names_no_missing_agentschat(self):
        self.install()
        self.machine.token("claude-code")
        self.machine.edit_kit("claude")
        code, given = self.purge()
        self.assertEqual(code, DONE, given.stderr.getvalue())
        code, given = self.purge()
        self.assertEqual(code, DONE, given.stderr.getvalue())
        text = given.stdout.getvalue()
        self.assertIn(
            f"{MANIFEST} оставлен по причинам выше: удалите его вместе с этими файлами.",
            text,
        )
        self.assertNotIn("agentschat uninstall удалит его сам", text)

    def test_the_purge_report_says_why_the_manifest_stays(self):
        self.install()
        self.machine.token("claude-code")
        self.machine.edit_kit("claude")
        code, given = self.purge()
        self.assertEqual(code, DONE, given.stderr.getvalue())
        self.assertIn(
            f"{MANIFEST} оставлен по причинам выше: удалите его вместе с этими файлами.",
            given.stdout.getvalue(),
        )

    def test_the_purge_report_points_at_the_reason_the_manifest_stays(self):
        self.install()
        self.machine.token("claude-code")
        code, given = self.remove("--purge", "--claude", stdin="PURGE\n")
        self.assertEqual(code, DONE)
        lines = given.stdout.getvalue().splitlines()
        cross_reference = (
            f"{MANIFEST} оставлен по причинам выше: когда записей не останется, "
            "agentschat uninstall удалит его сам."
        )
        self.assertLess(
            lines.index(
                "    набор для opencode не снимался: его не называл ключ запуска"
            ),
            lines.index(cross_reference),
        )

    def test_a_kept_package_does_not_send_the_manifest_line_to_agentschat(self):
        self.install()
        self.machine.token("claude-code")
        _, given = self.remove("--purge", "--claude", stdin="PURGE\n")
        self.assertNotIn(
            f"{MANIFEST} оставлен по причинам выше: удалите его вместе с этими файлами.",
            given.stdout.getvalue(),
        )

    def test_the_purge_report_says_who_removes_an_empty_manifest_by_hand(self):
        self.manifest().parent.mkdir(parents=True, exist_ok=True)
        self.manifest().write_text(json.dumps({"files": []}), encoding="utf-8")
        self.assertIn(
            f"{MANIFEST} остался, но записей в нём нет: уберите его вручную.",
            participant.purge_lines(self.plan_run()),
        )

    def test_the_purge_report_does_not_claim_a_manifest_that_is_already_gone(self):
        self.install()
        self.machine.token("claude-code")
        code, given = self.purge()
        self.assertEqual(code, DONE)
        self.assertFalse(self.manifest().is_file())
        self.assertNotIn(f"{MANIFEST} оставлен", given.stdout.getvalue())

    def test_a_json_file_that_is_not_a_session_token_is_kept_and_reported(self):
        self.stored()
        self.machine.other("notes.json", json.dumps({"note": "моё"}))
        code, given = self.purge()
        self.assertEqual(code, DONE)
        self.assertTrue((self.home / STORE / "notes.json").is_file())
        self.assertIn("notes.json", given.stdout.getvalue())

    def test_a_token_in_a_file_that_is_not_json_is_kept(self):
        self.stored()
        self.machine.other("claude-code.txt", json.dumps({"token": "секрет"}))
        code, _ = self.purge()
        self.assertEqual(code, DONE)
        self.assertTrue((self.home / STORE / "claude-code.txt").is_file())

    def test_a_broken_json_file_in_the_store_is_kept(self):
        self.stored()
        self.machine.other("half.json", "{")
        code, _ = self.purge()
        self.assertEqual(code, DONE)
        self.assertTrue((self.home / STORE / "half.json").is_file())

    def test_a_plain_file_in_the_store_is_kept_and_reported(self):
        self.stored()
        self.machine.other("log.txt", "привет")
        code, given = self.purge()
        self.assertEqual(code, DONE)
        self.assertIn("log.txt", given.stdout.getvalue())

    def test_a_purge_after_a_full_install_empties_the_record(self):
        self.install()
        self.machine.token("claude-code")
        code, _ = self.purge()
        self.assertEqual(code, DONE)
        self.assertFalse((self.home / STORE / "claude-code.json").exists())
        self.assertFalse(participant.record_path(self.given()).exists())

    def test_a_purge_of_an_empty_store_asks_nothing(self):
        code, given = self.purge()
        self.assertEqual(code, DONE)
        self.assertNotIn("PURGE", given.stdout.getvalue())

    def test_a_purge_leaves_the_broker_alone(self):
        code, _ = self.purge()
        self.assertEqual(code, DONE)
        self.assertFalse([line for line in self.machine.log if "status" in line])

    def test_a_purge_report_starts_with_what_the_removal_left(self):
        self.install()
        self.machine.token("claude-code")
        _, given = self.purge()
        text = given.stdout.getvalue()
        self.assertLess(
            text.index("Набор и пакет убраны."),
            text.index("Файлы сессий удалены"),
        )

    def test_a_purge_report_names_a_package_the_removal_kept(self):
        self.machine.installed_by.add("pipx")
        self.machine.token("claude-code")
        _, given = self.purge()
        text = given.stdout.getvalue()
        self.assertIn(f"пакет {participant.PACKAGE} (pipx)", text)
        self.assertLess(
            text.index(f"пакет {participant.PACKAGE} (pipx)"),
            text.index("Файлы сессий удалены"),
        )

    def test_a_purge_does_not_claim_the_session_files_stay(self):
        self.install()
        self.machine.token("claude-code")
        _, given = self.purge()
        self.assertNotIn(f"Файлы сессий в {STORE} оставлены", given.stdout.getvalue())

    def test_a_purge_still_names_the_command_that_installs_the_role_back(self):
        self.install()
        self.machine.token("claude-code")
        _, given = self.purge()
        self.assertIn("install.sh --role participant", given.stdout.getvalue())


class BrokenManifestTests(ParticipantCase):
    """kit.json не той формы не должен падать с «Причина: 'files'»."""

    def broken(self, stored: str = "{}") -> Path:
        path = self.home / STORE / MANIFEST
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(stored, encoding="utf-8")
        return path

    def test_an_install_over_a_manifest_without_files_names_the_manifest(self):
        path = self.broken()
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn(
            f"Причина: {MANIFEST} не читается: {path}", given.stderr.getvalue()
        )

    def test_a_removal_over_a_manifest_without_files_names_the_manifest(self):
        self.install()
        self.pipx_bin.unlink()
        path = self.broken()
        code, given = self.remove()
        self.assertEqual(code, FAILED)
        self.assertIn(
            f"Причина: {MANIFEST} не читается: {path}", given.stderr.getvalue()
        )

    def test_the_clis_of_a_manifest_whose_entries_have_no_path_are_not_guessed(self):
        self.broken(json.dumps({"files": [{"cli": "claude", "sha256": "0" * 64}]}))
        with self.assertRaises(RuntimeError) as problem:
            participant.manifest_clis(self.plan_run())
        self.assertEqual(
            str(problem.exception),
            f"{MANIFEST} не читается: {self.home / STORE / MANIFEST}",
        )

    def test_a_manifest_that_is_not_json_at_all_is_treated_as_no_manifest(self):
        self.broken("{")
        self.assertEqual(participant.manifest_clis(self.plan_run()), set())


class DiscoveryBoundaryTests(ParticipantCase):
    def repo_with_server_data(self) -> Path:
        bridge = self.repo / "bridge"
        (bridge / "state").mkdir(parents=True)
        (bridge / "config.yaml").write_text("rooms: 1", encoding="utf-8")
        (bridge / "state" / "broker.pid").write_text("42", encoding="utf-8")
        docker = self.repo / "docker" / "continuwuity"
        docker.mkdir(parents=True)
        (docker / "continuwuity.toml").write_text("port = 8008", encoding="utf-8")
        return self.repo

    def given_home(self) -> Path:
        store = self.home / STORE
        store.mkdir(parents=True)
        (store / MANIFEST).write_text(json.dumps({"files": []}), encoding="utf-8")
        (store / "claude-code.json").write_text(
            json.dumps({"agent": "claude-code", "token": "secret"}), encoding="utf-8"
        )
        installer = self.home / participant.INSTALLER_HOME / "installer"
        installer.mkdir(parents=True)
        for role in ("participant", "server"):
            (installer / f"{role}.json").write_text(
                json.dumps({"entries": []}), encoding="utf-8"
            )
        self.repo_with_server_data()
        return store

    def test_discovery_targets_only_the_broker_token_files(self):
        store = self.given_home()
        self.assertEqual(
            participant.broker_tokens(store), [str(store / "claude-code.json")]
        )

    def test_the_roles_own_purge_step_finds_nothing_but_the_tokens(self):
        store = self.given_home()
        run = self.plan_run()
        self.assertEqual(
            [target.id for target in participant.session_step().targets(run)],
            [str(store / "claude-code.json")],
        )

    def test_the_records_of_both_roles_are_never_purge_targets(self):
        self.given_home()
        run = self.plan_run()
        records = {
            participant.record_path(self.given()).resolve(),
            (
                self.home / participant.INSTALLER_HOME / "installer" / "server.json"
            ).resolve(),
        }
        targets = {
            Path(target.id).resolve()
            for target in participant.session_step().targets(run)
        }
        self.assertEqual(targets & records, set())

    def test_the_server_data_of_the_repository_is_never_a_purge_target(self):
        self.given_home()
        run = self.plan_run()
        targets = {
            str(Path(target.id).resolve())
            for target in participant.session_step().targets(run)
        }
        for wanted in ("bridge/config.yaml", "bridge/state/broker.pid"):
            self.assertFalse(any(target.endswith(wanted) for target in targets))

    def test_the_kept_files_are_named_without_the_manifest_and_the_tokens(self):
        store = self.home / STORE
        store.mkdir(parents=True)
        (store / MANIFEST).write_text(json.dumps({"files": []}), encoding="utf-8")
        (store / "claude-code.json").write_text(json.dumps({"token": "t"}))
        (store / "readme.txt").write_text("привет", encoding="utf-8")
        self.assertEqual(
            [Path(path).name for path in participant.kept_files(store)],
            ["readme.txt"],
        )

    def test_the_manifest_is_left_out_of_discovery_by_its_name(self):
        store = self.home / STORE
        store.mkdir(parents=True)
        (store / MANIFEST).write_text(
            json.dumps({"files": [], "token": "даже если бы токен лежал здесь"}),
            encoding="utf-8",
        )
        self.assertEqual(participant.broker_tokens(store), [])

    def test_the_manifest_is_left_out_of_the_kept_list_by_its_name(self):
        store = self.home / STORE
        store.mkdir(parents=True)
        (store / MANIFEST).write_text(
            json.dumps({"files": [], "token": "даже если бы токен лежал здесь"}),
            encoding="utf-8",
        )
        self.assertEqual(participant.kept_files(store), [])


class BuiltInRolesTests(ParticipantCase):
    def test_the_parser_from_the_built_in_roles_takes_the_participant_options(self):
        plan = parse(
            ["--role", ROLE, "--broker-url", "http://127.0.0.1:9", "--claude"],
            self.given(),
            built_in_roles(),
        )
        self.assertEqual(plan.roles, (ROLE,))
        self.assertEqual(plan.answers[ROLE][participant.URL_DEST], "http://127.0.0.1:9")

    def test_the_built_in_roles_start_with_the_server(self):
        self.assertEqual([role.name for role in built_in_roles()], ["server", ROLE])

    def role_by_name(self, name: str):
        return next(role for role in built_in_roles() if role.name == name)

    def test_the_record_of_the_participant_lives_outside_the_client_store(self):
        record = self.role_by_name(ROLE).record_path(self.given())
        self.assertNotIn(STORE, record.parts)

    def test_the_default_broker_of_the_role_is_the_documented_one(self):
        plan = parse(["--role", ROLE], self.given(), built_in_roles())
        self.assertEqual(
            plan.answers[ROLE][participant.URL_DEST], participant.DEFAULT_BROKER
        )


class DshStepTests(ParticipantCase):
    def setUp(self):
        super().setUp()
        self.dsh_home = self.home / "dsh-home"
        self.profile_dir = self.dsh_home / "profiles" / "web"
        self.profile_dir.mkdir(parents=True)
        self.profile_dir.joinpath("package.json").write_text(
            json.dumps({"dependencies": {}, "dsh": {"profile": {"bundles": []}}}),
            encoding="utf-8",
        )
        self.profile_dir.joinpath("cordis.patch.yml").write_text(
            "[]\n", encoding="utf-8"
        )
        kit_dir = (
            self.repo
            / "bridge"
            / "sessionchat"
            / "kit"
            / "ru"
            / "dsh"
            / "skills"
            / "chatlogin"
        )
        kit_dir.mkdir(parents=True)
        kit_dir.joinpath("SKILL.md").write_text("skill content", encoding="utf-8")

    def dsh_flags(self, *extra: str):
        return ["--dsh", "--dsh-home", str(self.dsh_home), *extra]

    def test_the_dsh_step_is_skipped_without_the_flag(self):
        status, given = self.install("--claude")
        self.assertEqual(status, DONE)
        self.assertFalse((self.dsh_home / "skills" / "chatlogin").exists())

    def test_the_skill_is_installed_to_the_dsh_skills_root(self):
        status, given = self.install(*self.dsh_flags())
        self.assertEqual(status, DONE)
        target = self.dsh_home / "skills" / "chatlogin" / "SKILL.md"
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_text(encoding="utf-8"), "skill content")

    def test_the_plugin_is_added_with_the_dsh_cli_when_present(self):
        status, given = self.install(*self.dsh_flags())
        self.assertEqual(status, DONE)
        self.assertTrue(self.machine.dsh_plugin_added)
        self.assertFalse(self.machine.pnpm_added)

    def test_the_plugin_falls_back_to_pnpm_when_dsh_is_missing(self):
        self.machine.present["dsh"] = False
        status, given = self.install(*self.dsh_flags())
        self.assertEqual(status, DONE)
        self.assertTrue(self.machine.pnpm_added)
        self.assertEqual(self.machine.pnpm_cwd, self.profile_dir)

    def test_the_fallback_edits_the_profile_manifest(self):
        self.machine.present["dsh"] = False
        status, given = self.install(*self.dsh_flags())
        self.assertEqual(status, DONE)
        package = json.loads(
            self.profile_dir.joinpath("package.json").read_text(encoding="utf-8")
        )
        self.assertIn("dsh-agentschat", package["dependencies"])
        self.assertIn("dsh-agentschat", package["dsh"]["profile"]["bundles"])
        patch = self.profile_dir.joinpath("cordis.patch.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("agentschat", patch)
        self.assertIn("dsh-agentschat", patch)


if __name__ == "__main__":
    unittest.main()
