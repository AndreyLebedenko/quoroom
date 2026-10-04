"""Карточка local-installers-06: роль сервера."""

import base64
import http.server
import io
import json
import os
import secrets as server_secrets
import re
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import installer_host
from tests.installer_fakes import (
    InstallerTestCase,
    boundaries,
    completed,
)
from sessionchat.installer.boundaries import Probe
from sessionchat.installer.main import DONE, FAILED, HUMAN, main
from sessionchat.installer.options import parse
from sessionchat.installer.ownership import Ownership
from sessionchat.installer.roles import built_in_roles
from sessionchat.installer.server import (
    BROKER_PORT,
    SERVER_NAME,
    not_after,
    server_role,
)

ROLE = "server"
ISSUED = "ISSUEDTOKEN01"
STALE = "STALETOKEN01"
CONFIG_TOKEN = "CONFIGTOKEN001"
ADMIN = "andrey"
ROOM = "!AbCdEf:agentschat.local"


class Machine:
    def __init__(self, home: Path, repo: Path, platform: str = "linux") -> None:
        self.home = home
        self.repo = repo
        self.platform = platform
        self.present = {"docker": True, "daemon": True, "compose": True, "mkcert": True}
        self.caroot = home / "mkcert"
        self.volumes: set[str] = set()
        self.accounts: dict[str, str] = {}
        self.passwords: dict[str, str] = {}
        self.server_up = False
        self.broker_up = False
        self.registration_open = True
        self.issued = ISSUED
        self.log_has_token = True
        self.issued_in_stderr = False
        self.issued_seen = False
        self.registered_tokens: list[str] = []
        self.registration_token = CONFIG_TOKEN
        self.log: list[str] = []
        self.stdout_log = ""
        self.start_code = 0
        self.only_issued = False
        self.start_argv: list[str] = []
        self.fail_pip = False
        self.fail_up = ""
        self.missing_import = 0
        self.missing_library = "aiohttp"
        self.probes = 0
        self.never_answers = False
        self.down_probes = 0
        self.colour_around_the_token = False
        self.closed_status = [403]

    def __call__(self, argv, stdin=None, output=None):
        argv = [str(part) for part in argv]
        self.log.append(" ".join(argv))
        name = Path(argv[0]).name
        if name == "docker":
            return self.docker(argv)
        if name == "mkcert":
            return self.mkcert(argv)
        if any(Path(part).name == "installer_host.py" for part in argv):
            return self.host(argv, stdin or "")
        if name in ("sh", "bash", "powershell.exe", "pwsh"):
            return self.start(argv, output)
        if name in ("python", "python.exe"):
            return self.python(argv)
        if name == "curl":
            return completed("")
        raise AssertionError(f"непредусмотренный вызов: {' '.join(argv)}")

    def docker(self, argv):
        if argv[1:] == ["--version"]:
            return (
                completed("Docker version 27.0.0")
                if self.present["docker"]
                else self._no("docker")
            )
        if argv[1] == "info":
            return (
                completed("Server: ok")
                if self.present["daemon"]
                else self._no("daemon")
            )
        if argv[1:] == ["compose", "version"]:
            return (
                completed("v2.29.0") if self.present["compose"] else self._no("compose")
            )
        if argv[1] == "volume":
            return completed("\n".join(sorted(self.volumes)))
        if argv[1] != "compose":
            return self._no("docker compose")
        assert argv[2] == "-f", argv
        assert "-p" not in argv, argv
        self.compose_file = Path(argv[3])
        rest = argv[4:]
        if rest[:1] == ["config"] and "--format" in rest:
            return completed(json.dumps({"name": "docker"}))
        if rest == ["config", "--volumes"]:
            return completed("continuwuity-data\ncaddy-data\ncaddy-config")
        if rest[:2] == ["up", "-d"]:
            if self.fail_up:
                return completed("", self.fail_up, 1)
            if self.never_answers:
                self.volumes |= {
                    "docker_continuwuity-data",
                    "docker_caddy-data",
                    "docker_caddy-config",
                }
                return completed("Container agentschat-caddy Started")
            self.volumes |= {
                "docker_continuwuity-data",
                "docker_caddy-data",
                "docker_caddy-config",
            }
            self.server_up = True
            return completed("Container agentschat-caddy Started")
        if rest == ["restart", "continuwuity"]:
            self.down_probes = 2
            return completed("Container agentschat-continuwuity Started")
        if rest[:1] == ["logs"]:
            return self.logs()
        return self._no(" ".join(rest))

    def logs(self):
        if self.colour_around_the_token:
            lines = [
                f"\x1b[1musing the registration token \x1b[33m{STALE}\x1b[0m . Pick your own",
                f"\x1b[1musing the registration token \x1b[33m{self.issued}\x1b[0m . Pick your own",
            ]
        elif self.log_has_token:
            lines = [
                f"using the registration token {STALE} . Pick your own",
                f"using the registration token {self.issued} . Pick your own",
            ]
        else:
            lines = ["continuwuity | the server is ready"]
        text = "\x1b[1m\x1b[32m" + "\n".join(lines) + "\x1b[0m"
        if self.issued_in_stderr:
            return completed("", text)
        return completed(text)

    def mkcert(self, argv):
        if argv[1] == "-version":
            return (
                completed("mkcert 1.4.3")
                if self.present["mkcert"]
                else self._no("mkcert")
            )
        if argv[1] == "-CAROOT":
            return completed(str(self.caroot))
        if "-cert-file" in argv:
            Path(argv[argv.index("-cert-file") + 1]).write_text(
                "cert", encoding="utf-8"
            )
            Path(argv[argv.index("-key-file") + 1]).write_text("key", encoding="utf-8")
            self.caroot.mkdir(parents=True, exist_ok=True)
            (self.caroot / "rootCA.pem").write_text("ca", encoding="utf-8")
            return completed("Created a new certificate")
        return self._no("mkcert")

    def python(self, argv):
        if argv[1:3] == ["-m", "venv"]:
            target = Path(argv[3])
            suffix = "Scripts" if self.platform == "windows" else "bin"
            name = "python.exe" if self.platform == "windows" else "python"
            (target / suffix).mkdir(parents=True, exist_ok=True)
            (target / suffix / name).write_text("python", encoding="utf-8")
            return completed("created")
        if "pip" in argv:
            if self.fail_pip:
                return completed("", "Could not find a version", 1)
            return completed("Successfully installed")
        return self._no(" ".join(argv[1:]))

    def start(self, argv, output):
        self.start_argv = [str(part) for part in argv]
        if self.start_code == 0:
            self.broker_up = True
        if output is not None:
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_text(self.stdout_log, encoding="utf-8")
            return subprocess.CompletedProcess(
                argv, self.start_code, self.stdout_log, ""
            )
        return completed(self.stdout_log, "", self.start_code)

    def host(self, argv, stdin):
        command = argv[[Path(p).name for p in argv].index("installer_host.py") + 1]
        payload = json.loads(stdin or "{}")
        try:
            answer = self.helper(command, payload)
        except installer_host.Failed as problem:
            return completed(json.dumps(problem.payload(), ensure_ascii=False), "", 1)
        return completed(
            json.dumps(answer, ensure_ascii=False), "", 1 if answer.get("error") else 0
        )

    def helper(self, command, payload):
        if command == "imports":
            if self.missing_import:
                self.missing_import -= 1
                raise installer_host.Failed("imports", errcode=self.missing_library)
            return {"ok": True}
        if command == "available":
            return {"available": payload["username"] not in self.accounts}
        if command == "whoami":
            return self.whoami(payload)
        if command == "read-yaml":
            return installer_host.read_yaml(payload["path"], installer_host.READABLE)
        if command == "write-yaml":
            return installer_host.write_yaml(
                payload["path"], payload["example"], payload["values"], payload["owned"]
            )
        if command == "register":
            return self.register(payload)
        if command == "login":
            return self.login(payload)
        if command == "probe-closed":
            status = (
                self.closed_status.pop(0)
                if len(self.closed_status) > 1
                else self.closed_status[0]
            )
            self.probes += 1
            return {
                "status": status,
                "errcode": "" if status == 403 else "M_FORBIDDEN",
            }
        raise AssertionError(f"непредусмотренная команда помощника: {command}")

    def whoami(self, payload):
        example = installer_host._load(payload["example"])
        statuses = {}
        for agent, entry in (
            installer_host._load(payload["config"]).get("agents") or {}
        ).items():
            token = str((entry or {}).get("access_token") or "")
            if not token:
                statuses[agent] = "absent"
            elif token == str(
                ((example.get("agents") or {}).get(agent) or {}).get("access_token")
                or ""
            ):
                statuses[agent] = "placeholder"
            elif self.accounts.get(agent) == token:
                statuses[agent] = "valid"
            else:
                statuses[agent] = "invalid"
        return statuses

    def toml_token(self) -> str:
        path = self.repo / "docker" / "continuwuity" / "continuwuity.toml"
        if not path.is_file():
            return ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("registration_token"):
                return line.split("=", 1)[1].strip().strip(chr(34))
        return ""

    def register(self, payload):
        username = payload["username"]
        if username in self.accounts:
            return {"error": "register", "errcode": "M_USER_IN_USE", "status": 400}
        if not self.registration_open:
            return {"error": "register", "errcode": "M_FORBIDDEN", "status": 403}
        accepted = {self.registration_token, self.issued, self.toml_token()}
        if self.only_issued:
            accepted = (
                {self.issued}
                if not self.accounts
                else {self.registration_token, self.toml_token()}
            )
        if payload["token"] not in accepted:
            return {"error": "register", "errcode": "M_FORBIDDEN", "status": 401}
        if payload["token"] == self.issued:
            self.issued_seen = True
        self.registered_tokens.append(payload["token"])
        self.accounts[username] = f"token-{username}"
        self.passwords[username] = payload["password"]
        return {
            "user_id": f"@{username}:{SERVER_NAME}",
            "access_token": f"token-{username}",
            "device_id": f"device-{username}",
        }

    def login(self, payload):
        username = payload["username"]
        if self.passwords.get(username) != payload["password"]:
            return {"error": "login", "errcode": "M_FORBIDDEN", "status": 403}
        return {
            "user_id": f"@{username}:{SERVER_NAME}",
            "access_token": f"token-{username}",
            "device_id": f"device-{username}",
        }

    def _no(self, what):
        if not self.present.get(what.split()[0], True):
            raise FileNotFoundError(what)
        return completed(f"{what}: command not found", "", 127)


class ServerCase(InstallerTestCase):
    def setUp(self):
        super().setUp()
        self.repo = self.home / "repo"
        self.machine = Machine(self.home, self.repo)
        self.ready()
        self.probe_status = 200
        self.probe_untrusted = False
        self.resolved = ("127.0.0.1",)
        self.env = {
            "PATH": "",
            "HOME": str(self.home),
            "QUOROOM_ADMIN_PASSWORD": "from-env",
        }
        self.slept: list[float] = []
        self.last_given = None

    def probe(self, url: str) -> Probe:
        if self.machine.down_probes and not url.endswith("/status"):
            self.machine.down_probes -= 1
            return Probe(None, "continuwuity перезапускается")
        alive = (
            self.machine.broker_up
            if url.endswith("/status")
            else self.machine.server_up
        )
        if self.probe_untrusted:
            return Probe(None, "сертификат не подтверждён: self signed", True)
        return (
            Probe(self.probe_status, None)
            if alive
            else Probe(None, "отказано в соединении")
        )

    def given(self, **values) -> boundaries:
        self.machine.platform = values.get("platform", self.machine.platform)
        probe = values.pop("probe", self.probe)
        return boundaries(
            self.home,
            repo=self.repo,
            env=values.pop("env", self.env),
            run=self.machine,
            probe=probe,
            platform=values.pop("platform", "linux"),
            resolve=values.pop("resolve", lambda name: self.resolved),
            secret=values.pop("secret", lambda prompt: "typed-password"),
            **values,
        )

    def roles(self):
        return (server_role(python=sys.executable, sleep=self.slept.append),)

    def full(self, *flags: str, **values):
        return self.install("--admin-user", ADMIN, "--room-id", ROOM, *flags, **values)

    def install(self, *flags: str, **values):
        given = self.given(**values)
        code = main(["--role", ROLE, *flags], given, self.roles())
        self.last_given = given
        return code, given

    def ready(self) -> None:
        self.repo.mkdir(parents=True, exist_ok=True)
        for name in (
            "bridge/requirements.txt",
            "bridge/register_account.py",
            "bridge/config.example.yaml",
            "docker/docker-compose.yml",
            "docker/.env.example",
            "docker/continuwuity/continuwuity.toml.example",
            "start.sh",
            "start.ps1",
            "stop.sh",
            "stop.ps1",
        ):
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.is_file():
                self.copy_example(name, path)
        self.machine.present["mkcert"] = True

    def copy_example(self, name: str, target: Path) -> None:
        source = Path(__file__).resolve().parents[2] / name
        if source.is_file():
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            return
        target.write_text(f"# {name}\n", encoding="utf-8")

    def path(self, relative: str) -> Path:
        return self.repo / relative

    def stdout(self, given) -> str:
        return given.stdout.getvalue()

    def stderr(self, given) -> str:
        return given.stderr.getvalue()

    def recorded(self) -> list[tuple[str, str]]:
        ownership = Ownership.load(self.record_file())
        return [(entry.kind, entry.id) for entry in ownership.entries]

    def record_file(self) -> Path:
        return self.home / ".quoroom" / "installer" / "server.json"

    def toml(self) -> Path:
        return self.path("docker/continuwuity/continuwuity.toml")

    def config(self) -> Path:
        return self.path("bridge/config.yaml")

    def accounts_file(self) -> Path:
        return self.path("bridge/state/server-accounts.json")

    def edit_config(self, values: dict, owned: bool = True) -> dict:
        return installer_host.write_yaml(
            str(self.config()),
            str(self.path("bridge/config.example.yaml")),
            values,
            owned,
        )

    def settled(self) -> None:
        self.machine.accounts[ADMIN] = "already"
        self.configure()

    def configure(self, room: str = ROOM) -> None:
        self.config().write_text(
            self.path("bridge/config.example.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        self.machine.accounts.setdefault("claude-code", "token-claude-code")
        self.machine.accounts.setdefault("opencode", "token-opencode")
        installer_host.write_yaml(
            str(self.config()),
            str(self.path("bridge/config.example.yaml")),
            {
                "room_id": room,
                "agents.claude-code.user_id": f"@claude-code:{SERVER_NAME}",
                "agents.claude-code.access_token": "token-claude-code",
                "agents.claude-code.device_id": "device-claude-code",
                "agents.opencode.user_id": f"@opencode:{SERVER_NAME}",
                "agents.opencode.access_token": "token-opencode",
                "agents.opencode.device_id": "device-opencode",
            },
            True,
        )


class PrerequisiteTests(ServerCase):
    def test_a_missing_docker_is_a_human_step_naming_the_windows_command(self):
        self.machine.present["docker"] = False
        code, given = self.install(platform="windows")
        self.assertEqual(code, HUMAN)
        self.assertIn("winget install Docker.DockerDesktop", self.stdout(given))
        self.assertEqual(self.recorded(), [])

    def test_a_missing_docker_on_linux_names_the_apt_command(self):
        self.machine.present["docker"] = False
        code, given = self.install()
        self.assertEqual(code, HUMAN)
        self.assertIn("apt install docker.io", self.stdout(given))

    def test_a_docker_that_does_not_answer_is_a_human_step(self):
        self.machine.present["daemon"] = False
        code, given = self.install()
        self.assertEqual(code, HUMAN)
        self.assertIn("Запустите dockerd", self.stdout(given))

    def test_the_daemon_human_step_names_docker_desktop_on_windows(self):
        self.machine.present["daemon"] = False
        code, given = self.install(platform="windows")
        self.assertEqual(code, HUMAN)
        self.assertIn("Запустите Docker Desktop", self.stdout(given))

    def test_a_docker_group_problem_is_named_on_linux(self):
        self.machine.present["daemon"] = False
        code, given = self.install()
        self.assertEqual(code, HUMAN)
        self.assertIn("usermod -aG docker", self.stdout(given))

    def test_a_missing_compose_is_a_human_step(self):
        self.machine.present["compose"] = False
        code, given = self.install()
        self.assertEqual(code, HUMAN)
        self.assertIn("docker-compose-v2", self.stdout(given))

    def test_a_missing_mkcert_is_a_human_step(self):
        self.machine.present["mkcert"] = False
        code, given = self.install()
        self.assertEqual(code, HUMAN)
        self.assertIn("FiloSottile/mkcert", self.stdout(given))

    def test_nothing_is_created_before_the_prerequisites_pass(self):
        self.machine.present["docker"] = False
        self.install()
        self.assertEqual(list(self.repo.rglob("bridge/.venv")), [])

    def test_a_whole_run_on_a_ready_machine_finishes(self):
        self.ready()
        code, given = self.install(
            "--admin-user", ADMIN, "--room-id", ROOM, secret=lambda prompt: "typed"
        )
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(
            f"Брокер для участников: http://127.0.0.1:{BROKER_PORT}", self.stdout(given)
        )


class ServerNameTests(ServerCase):
    def test_a_name_that_does_not_resolve_is_a_human_step(self):
        self.resolved = ()
        code, given = self.install()
        self.assertEqual(code, HUMAN)
        self.assertIn(f"127.0.0.1 {SERVER_NAME}", self.stdout(given))

    def test_the_human_step_names_the_windows_hosts_file(self):
        self.resolved = ()
        code, given = self.install(platform="windows")
        self.assertEqual(code, HUMAN)
        self.assertIn(r"drivers\etc\hosts", self.stdout(given))

    def test_the_human_step_names_the_linux_hosts_file(self):
        self.resolved = ()
        code, given = self.install()
        self.assertEqual(code, HUMAN)
        self.assertIn("/etc/hosts", self.stdout(given))

    def test_a_name_that_resolves_off_loopback_is_a_human_step(self):
        self.resolved = ("192.168.1.10",)
        code, given = self.install()
        self.assertEqual(code, HUMAN)
        self.assertIn("адрес петли", self.stdout(given))

    def test_ipv6_loopback_is_accepted(self):
        self.resolved = ("::1",)
        code, given = self.install(
            "--admin-user", ADMIN, "--room-id", ROOM, secret=lambda prompt: "typed"
        )
        self.assertEqual(code, DONE, self.stderr(given))

    def test_a_loopback_name_is_not_asked_about_again(self):
        self.ready()
        self.full()
        self.assertIn(
            "Проверить имя сервера: уже сделано.", self.stdout(self.last_given)
        )


class VenvTests(ServerCase):
    def installed_to_venv(self, *flags: str, **values):
        self.ready()
        return self.full(*flags, **values)

    def test_the_venv_is_created_and_recorded(self):
        code, _ = self.installed_to_venv()
        self.assertEqual(code, DONE, self.stderr(self.last_given))
        self.assertIn(("venv", str(self.path("bridge/.venv"))), self.recorded())

    def test_a_repeat_run_keeps_the_same_venv(self):
        self.installed_to_venv()
        self.machine.log.clear()
        self.install()
        self.assertFalse([line for line in self.machine.log if "-m venv" in line])

    def test_the_record_is_written_before_pip_so_a_failure_keeps_it(self):
        self.machine.fail_pip = True
        code, given = self.installed_to_venv()
        self.assertEqual(code, FAILED)
        self.assertIn("bridge/.venv не собралась", self.stderr(given))
        self.assertIn(("venv", str(self.path("bridge/.venv"))), self.recorded())

    def test_a_pip_failure_names_its_last_line(self):
        self.machine.fail_pip = True
        _, given = self.installed_to_venv()
        self.assertIn("Could not find a version", self.stderr(given))

    def test_a_venv_without_the_libraries_is_repaired(self):
        self.ready()
        self.install()
        self.machine.missing_import = 1
        self.machine.log.clear()
        code, _ = self.full()
        self.assertEqual(code, DONE, self.stderr(self.last_given))
        self.assertTrue([line for line in self.machine.log if "pip install" in line])

    def test_a_venv_that_existed_before_this_run_is_not_recorded_as_ours(self):
        venv = self.path("bridge/.venv/bin")
        venv.mkdir(parents=True, exist_ok=True)
        (venv / "python").write_text("python", encoding="utf-8")
        self.machine.missing_import = 1
        code, given = self.installed_to_venv()
        self.assertEqual(code, DONE, self.stderr(self.last_given))
        self.assertNotIn(("venv", str(self.path("bridge/.venv"))), self.recorded())

    def test_a_venv_whose_libraries_never_come_back_fails_with_the_name(self):
        self.ready()
        self.machine.missing_import = 99
        code, given = self.install("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, FAILED)
        self.assertIn("imports", self.stderr(given))
        self.assertIn("aiohttp", self.stderr(given))


class CertificateTests(ServerCase):
    def prepared(self):
        self.ready()
        return self.full(secret=lambda prompt: "typed")

    def test_the_certificate_is_issued_and_recorded(self):
        code, given = self.prepared()
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(
            ("cert", str(self.path("docker/caddy/certs/agentschat.local.pem"))),
            self.recorded(),
        )
        self.assertIn(
            ("cert", str(self.path("docker/caddy/certs/agentschat.local-key.pem"))),
            self.recorded(),
        )

    def test_certificates_that_existed_are_not_adopted(self):
        self.ready()
        self.path("docker/caddy/certs").mkdir(parents=True, exist_ok=True)
        (self.path("docker/caddy/certs/agentschat.local.pem")).write_text(
            "old", encoding="utf-8"
        )
        (self.path("docker/caddy/certs/agentschat.local-key.pem")).write_text(
            "old", encoding="utf-8"
        )
        self.install()
        self.assertEqual([kind for kind, _ in self.recorded() if kind == "cert"], [])

    def test_an_existing_certificate_is_not_issued_again(self):
        self.ready()
        self.path("docker/caddy/certs").mkdir(parents=True, exist_ok=True)
        (self.path("docker/caddy/certs/agentschat.local.pem")).write_text(
            "old", encoding="utf-8"
        )
        (self.path("docker/caddy/certs/agentschat.local-key.pem")).write_text(
            "old", encoding="utf-8"
        )
        self.machine.log.clear()
        self.install()
        self.assertFalse([line for line in self.machine.log if "-cert-file" in line])


class EnvFileTests(ServerCase):
    def prepared(self):
        self.ready()
        return self.full(secret=lambda prompt: "typed")

    def test_the_env_file_is_created_from_the_example_and_recorded(self):
        code, given = self.prepared()
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(("file", str(self.path("docker/.env"))), self.recorded())
        self.assertIn(
            f"SERVER_NAME={SERVER_NAME}",
            self.path("docker/.env").read_text(encoding="utf-8"),
        )

    def test_another_server_name_is_a_named_conflict(self):
        self.ready()
        (self.path("docker/.env")).write_text(
            "SERVER_NAME=other.local\n", encoding="utf-8"
        )
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn("SERVER_NAME=other.local", self.stderr(given))
        self.assertIn("строка 1", self.stderr(given))

    def test_a_file_without_the_server_name_is_a_named_conflict(self):
        self.ready()
        (self.path("docker/.env")).write_text("# пусто\n", encoding="utf-8")
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn("нет строки SERVER_NAME", self.stderr(given))

    def test_an_existing_env_file_is_not_adopted(self):
        self.ready()
        (self.path("docker/.env")).write_text(
            f"SERVER_NAME={SERVER_NAME}\n", encoding="utf-8"
        )
        self.install()
        self.assertNotIn(("file", str(self.path("docker/.env"))), self.recorded())


class TomlTests(ServerCase):
    def prepared(self):
        self.ready()
        return self.full(secret=lambda prompt: "typed")

    def test_the_toml_is_created_with_a_generated_token_and_recorded(self):
        opened: list[str] = []
        original = type(self.machine).register

        def watching(machine_self, payload):
            opened.append(self.toml().read_text(encoding="utf-8"))
            return original(machine_self, payload)

        type(self.machine).register = watching
        try:
            code, given = self.prepared()
        finally:
            type(self.machine).register = original
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(("file", str(self.toml())), self.recorded())
        self.assertTrue(opened)
        for text in opened:
            self.assertIn("allow_registration = true", text)
            self.assertNotIn("change-me-before-first-run", text)
        self.assertNotIn(
            "change-me-before-first-run", self.toml().read_text(encoding="utf-8")
        )

    def test_the_example_keeps_its_global_section(self):
        self.prepared()
        self.assertIn("[global]", self.toml().read_text(encoding="utf-8"))

    def test_a_toml_with_the_example_token_is_a_named_conflict(self):
        self.ready()
        self.copy_example("docker/continuwuity/continuwuity.toml.example", self.toml())
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn("всё ещё пример", self.stderr(given))

    def test_a_toml_without_a_registration_token_is_a_named_conflict(self):
        self.ready()
        self.toml().write_text(
            "[global]\nallow_registration = true\n", encoding="utf-8"
        )
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn("нет строки registration_token", self.stderr(given))

    def test_an_existing_valid_toml_is_not_adopted(self):
        self.ready()
        self.toml().write_text(
            '[global]\nallow_registration = true\nregistration_token = "mine-not-the-example"\n',
            encoding="utf-8",
        )
        self.install()
        self.assertNotIn(("file", str(self.toml())), self.recorded())

    def test_the_secret_token_never_reaches_the_output(self):
        code, given = self.prepared()
        token = re.search(
            r'registration_token = "([^"]+)"', self.toml().read_text(encoding="utf-8")
        ).group(1)
        self.assertEqual(code, DONE)
        self.assertNotIn(token, self.stdout(given) + self.stderr(given))


class InfrastructureTests(ServerCase):
    def prepared(self):
        self.ready()
        return self.full(secret=lambda prompt: "typed")

    def test_compose_is_called_with_the_file_and_without_a_project_name(self):
        self.prepared()
        calls = [line for line in self.machine.log if " compose " in line]
        self.assertTrue(calls)
        wanted = f"-f {self.path('docker/docker-compose.yml')}".replace("\\", "/")
        for call in calls:
            self.assertNotIn(" -p ", call)
            if call.startswith("docker compose -f"):
                self.assertIn(wanted, call.replace("\\", "/"))
        self.assertTrue([line for line in calls if wanted in line.replace("\\", "/")])

    def test_the_stack_is_brought_up(self):
        self.prepared()
        self.assertTrue([line for line in self.machine.log if line.endswith("up -d")])

    def test_the_new_volumes_are_recorded(self):
        self.prepared()
        kinds = [(kind, name) for kind, name in self.recorded() if kind == "volume"]
        self.assertEqual(
            sorted(name for _, name in kinds),
            ["docker_caddy-config", "docker_caddy-data", "docker_continuwuity-data"],
        )

    def test_volumes_that_existed_are_not_recorded(self):
        self.machine.volumes |= {"docker_continuwuity-data"}
        self.prepared()
        names = [name for kind, name in self.recorded() if kind == "volume"]
        self.assertNotIn("docker_continuwuity-data", names)

    def test_a_server_that_never_answers_fails_with_the_compose_hint(self):
        self.probe_status = None
        code, given = self.prepared()
        self.assertEqual(code, FAILED)
        self.assertIn("не ответил за", self.stderr(given))
        self.assertIn("logs continuwuity", self.stderr(given))

    def test_the_run_waits_before_giving_up(self):
        self.probe_status = None
        self.prepared()
        self.assertTrue(self.slept)

    def test_a_failed_up_is_named_with_composes_own_reason(self):
        self.machine.fail_up = "443/tcp: address already in use"
        code, given = self.prepared()
        self.assertEqual(code, FAILED)
        self.assertIn("443/tcp: address already in use", self.stderr(given))

    def test_volumes_are_recorded_even_when_the_server_never_answers(self):
        self.machine.never_answers = True
        code, given = self.prepared()
        self.assertEqual(code, FAILED)
        self.assertIn("не ответил за", self.stderr(given))
        self.assertEqual(
            sorted(name for kind, name in self.recorded() if kind == "volume"),
            ["docker_caddy-config", "docker_caddy-data", "docker_continuwuity-data"],
        )

    def test_volumes_are_counted_under_the_compose_project_of_the_repository(self):
        self.prepared()
        self.assertTrue(
            [
                line
                for line in self.machine.log
                if "label=com.docker.compose.project=" in line
            ]
        )

    def test_a_gateway_error_is_not_a_started_server(self):
        self.machine.server_up = True
        self.probe_status = 502
        code, given = self.prepared()
        self.assertEqual(code, FAILED)
        self.assertIn("не ответил за", self.stderr(given))
        self.assertTrue(self.slept)

    def test_an_untrusted_certificate_still_counts_as_started(self):
        self.probe_untrusted = True
        code, given = self.install()
        self.assertIn("Поднять инфраструктуру: уже сделано.", self.stdout(given))
        self.assertIn("mkcert -install", self.stdout(given))


class TrustTests(ServerCase):
    def prepared(self, **values):
        self.ready()
        return self.full(**values)

    def test_an_untrusted_certificate_is_a_human_step(self):
        self.probe_untrusted = True
        code, given = self.prepared()
        self.assertEqual(code, HUMAN)
        self.assertIn("mkcert -install", self.stdout(given))

    def test_the_linux_instruction_names_the_mkcert_root(self):
        self.probe_untrusted = True
        _, given = self.prepared()
        self.assertIn(f'CAROOT="{self.machine.caroot}"', self.stdout(given))

    def test_the_windows_instruction_has_no_caroot(self):
        self.probe_untrusted = True
        _, given = self.prepared(platform="windows")
        self.assertIn("mkcert -install", self.stdout(given))
        self.assertNotIn("CAROOT", self.stdout(given))

    def test_a_trusted_certificate_passes_without_a_word(self):
        code, given = self.prepared()
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(
            "Проверить доверие к сертификату: уже сделано.", self.stdout(given)
        )


class ConfigTests(ServerCase):
    def prepared(self):
        self.ready()
        return self.full(secret=lambda prompt: "typed")

    def test_the_config_is_created_from_the_example_and_recorded(self):
        code, given = self.prepared()
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(("file", str(self.config())), self.recorded())

    def test_a_config_with_placeholders_still_passes_this_step(self):
        code, given = self.prepared()
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn("PASTE_TOKEN_HERE", self.config().read_text(encoding="utf-8"))

    def test_a_broken_config_names_the_file_and_the_line(self):
        self.ready()
        self.config().write_text('homeserver_url: "x"\n\tbroken: [\n', encoding="utf-8")
        code, given = self.install()
        self.assertEqual(code, FAILED)
        self.assertIn(str(self.config()), self.stderr(given))
        self.assertIn("строка=", self.stderr(given))

    def test_an_existing_config_is_not_adopted(self):
        self.ready()
        self.config().write_text(
            f'homeserver_url: "{SERVER_NAME}"\nroom_id: "{ROOM}"\n', encoding="utf-8"
        )
        self.install()
        self.assertNotIn(("file", str(self.config())), self.recorded())


class HumanAccountTests(ServerCase):
    def prepared(self, *flags: str, **values):
        self.ready()
        return self.install(*flags, **values)

    def test_the_human_account_is_registered_with_the_configured_token(self):
        code, given = self.prepared(
            "--admin-user", ADMIN, "--room-id", ROOM, secret=lambda prompt: "typed"
        )
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(ADMIN, self.machine.accounts)
        self.assertFalse(self.machine.issued_seen)

    def test_the_password_comes_from_the_environment_when_it_is_set(self):
        self.env = {"PATH": "", "QUOROOM_ADMIN_PASSWORD": "from-env"}
        code, _ = self.prepared("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, DONE)
        self.assertIn(ADMIN, self.machine.accounts)

    def test_the_password_is_never_in_the_output(self):
        code, given = self.prepared(
            "--admin-user",
            ADMIN,
            "--room-id",
            ROOM,
            env={"PATH": "", "QUOROOM_ADMIN_PASSWORD": "from-env-secret"},
            secret=lambda prompt: "typed",
        )
        self.assertEqual(code, DONE)
        self.assertNotIn("from-env-secret", self.stdout(given) + self.stderr(given))

    def test_the_password_is_asked_without_echo_in_a_terminal(self):
        code, given = self.prepared(
            "--admin-user",
            ADMIN,
            "--room-id",
            ROOM,
            stdin="",
            interactive=True,
            secret=lambda prompt: "typed-here",
        )
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(ADMIN, self.machine.accounts)

    def test_no_password_anywhere_is_a_human_step(self):
        self.ready()
        code, given = self.install(
            "--admin-user",
            ADMIN,
            "--room-id",
            ROOM,
            env={"PATH": "", "HOME": str(self.home)},
        )
        self.assertEqual(code, HUMAN, self.stderr(given))
        self.assertIn("QUOROOM_ADMIN_PASSWORD", self.stdout(given))

    def test_a_missing_admin_user_is_a_human_step_naming_the_flag(self):
        code, given = self.prepared("--room-id", ROOM)
        self.assertEqual(code, HUMAN)
        self.assertIn("--admin-user", self.stdout(given))

    def test_an_interactive_run_asks_the_admin_user_and_registers_it(self):
        code, given = self.install(
            "--room-id",
            ROOM,
            stdin=f"{ADMIN}\n",
            interactive=True,
            secret=lambda prompt: "typed",
        )
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(ADMIN, self.machine.accounts)

    def test_the_interactive_question_appears_once_and_names_the_account(self):
        code, given = self.install(
            "--room-id",
            ROOM,
            stdin=f"{ADMIN}\n",
            interactive=True,
            secret=lambda prompt: "typed",
        )
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertEqual(self.stdout(given).count("Имя локального аккаунта"), 1)

    def test_an_interactive_repeat_of_an_installer_made_server_registers_nothing(self):
        self.prepared("--admin-user", ADMIN, "--room-id", ROOM)
        code, given = self.install(
            "--room-id",
            ROOM,
            stdin=f"{ADMIN}\n",
            interactive=True,
            secret=lambda prompt: "typed",
        )
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertNotIn("M_USER_IN_USE", self.stderr(given))

    def test_an_interactive_run_on_a_hand_built_server_accepts_the_existing_account(
        self,
    ):
        self.ready()
        self.machine.accounts[ADMIN] = "already"
        self.toml().parent.mkdir(parents=True, exist_ok=True)
        self.toml().write_text(
            '[global]\nallow_registration = true\nregistration_token = "mine"\n',
            encoding="utf-8",
        )
        code, given = self.install(
            "--room-id",
            ROOM,
            stdin=f"{ADMIN}\n",
            interactive=True,
            secret=lambda prompt: "typed",
        )
        self.assertIn("Завести аккаунт человека: готово", self.stdout(given))
        for claim in ("M_USER_IN_USE", "на сервере нет"):
            self.assertNotIn(claim, self.stdout(given) + self.stderr(given))

    def test_an_interactive_run_with_an_empty_answer_is_a_human_step(self):
        code, given = self.install(
            "--room-id",
            ROOM,
            stdin="\n",
            interactive=True,
            secret=lambda prompt: "typed",
        )
        self.assertEqual(code, HUMAN)
        self.assertIn("--admin-user", self.stdout(given))
        self.assertNotIn(ADMIN, self.machine.accounts)

    def test_an_existing_account_registers_nothing(self):
        self.machine.accounts[ADMIN] = "already"
        self.prepared("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(self.machine.accounts[ADMIN], "already")

    def test_an_unowned_toml_is_a_human_step(self):
        self.ready()
        self.toml().parent.mkdir(parents=True, exist_ok=True)
        self.toml().write_text(
            '[global]\nallow_registration = true\nregistration_token = "mine"\n',
            encoding="utf-8",
        )
        code, given = self.install("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, HUMAN)
        self.assertIn("создан не этим установщиком", self.stdout(given))
        self.assertNotIn(ADMIN, self.machine.accounts)

    def test_a_closed_server_is_a_human_step_and_never_reads_the_log(self):
        self.machine.registration_open = False
        code, given = self.prepared("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, HUMAN, self.stderr(given))
        self.assertIn("не принимает регистрации", self.stdout(given))
        self.assertFalse([line for line in self.machine.log if " logs " in line])
        self.assertNotIn(ADMIN, self.machine.accounts)

    def test_a_refused_configured_token_falls_back_to_the_issued_one(self):
        self.machine.only_issued = True
        code, given = self.prepared("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertTrue(self.machine.issued_seen)
        self.assertIn(ADMIN, self.machine.accounts)

    def test_the_issued_token_is_read_from_both_streams(self):
        self.machine.only_issued = True
        self.machine.issued_in_stderr = True
        code, _ = self.prepared("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, DONE)
        self.assertTrue(self.machine.issued_seen)

    def test_the_log_output_never_reaches_the_installer_output(self):
        self.machine.only_issued = True
        self.machine.issued_in_stderr = True
        code, given = self.prepared("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, DONE)
        for text in (self.stdout(given), self.stderr(given)):
            self.assertNotIn(ISSUED, text)
            self.assertNotIn("Pick your own", text)

    def test_no_issued_token_anywhere_is_a_human_step_naming_the_command(self):
        self.machine.only_issued = True
        self.machine.log_has_token = False
        code, given = self.prepared("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, HUMAN)
        self.assertIn("logs continuwuity", self.stdout(given))

    def test_a_banner_that_wraps_the_token_in_colour_is_still_read(self):
        self.machine.only_issued = True
        self.machine.colour_around_the_token = True
        code, given = self.prepared("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertTrue(self.machine.issued_seen)

    def test_the_newest_issued_token_is_the_one_that_is_used(self):
        self.machine.only_issued = True
        code, given = self.prepared("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(ISSUED, self.machine.registered_tokens)
        self.assertNotIn(STALE, self.machine.registered_tokens)

    def test_the_log_command_is_compose_with_the_file(self):
        self.machine.only_issued = True
        self.machine.log_has_token = False
        self.prepared("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertTrue(
            [
                line
                for line in self.machine.log
                if line.endswith("logs --no-log-prefix continuwuity")
            ]
        )


class BotAccountTests(ServerCase):
    def prepared(self, *flags: str, **values):
        self.ready()
        values.setdefault("secret", lambda prompt: "typed")
        return self.full(*flags, **values)

    def with_extra_agent(self, block: str) -> None:
        self.ready()
        self.config().write_text(
            self.path("bridge/config.example.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        self.edit_config(
            {
                "room_id": ROOM,
                "agents.claude-code.user_id": f"@claude-code:{SERVER_NAME}",
                "agents.claude-code.access_token": "token-claude-code",
                "agents.claude-code.device_id": "device-claude-code",
                "agents.opencode.user_id": f"@opencode:{SERVER_NAME}",
                "agents.opencode.access_token": "token-opencode",
                "agents.opencode.device_id": "device-opencode",
            },
            owned=False,
        )
        with self.config().open("a", encoding="utf-8") as sink:
            sink.write(block)
        self.machine.accounts.setdefault("claude-code", "token-claude-code")
        self.machine.accounts.setdefault("opencode", "token-opencode")

    def test_an_agent_the_human_added_gets_its_keys_inside_its_own_block(self):
        self.with_extra_agent('  terra:\n    display_name: "Terra"\n')
        code, given = self.install(
            "--admin-user", ADMIN, "--room-id", ROOM, secret=lambda prompt: "typed"
        )
        self.assertEqual(code, DONE, self.stderr(given))
        stored = installer_host._load(str(self.config()))
        self.assertEqual(
            stored["agents"]["terra"],
            {
                "display_name": "Terra",
                "user_id": f"@terra:{SERVER_NAME}",
                "access_token": "token-terra",
                "device_id": "device-terra",
            },
        )
        self.assertNotIn("terra", stored)

    def test_an_agent_copied_from_the_example_block_still_gets_its_tokens(self):
        self.with_extra_agent(
            "  terra:\n"
            '    user_id: "@terra:agentschat.local"\n'
            '    access_token: "PASTE_TOKEN_HERE"\n'
            '    device_id: "PASTE_DEVICE_ID_HERE"\n'
            '    display_name: "Terra"\n'
        )
        code, given = self.install(
            "--admin-user", ADMIN, "--room-id", ROOM, secret=lambda prompt: "typed"
        )
        self.assertEqual(code, DONE, self.stderr(given))
        stored = installer_host._load(str(self.config()))
        self.assertEqual(stored["agents"]["terra"]["access_token"], "token-terra")
        self.assertEqual(stored["agents"]["terra"]["device_id"], "device-terra")

    def test_a_repeat_run_adds_no_new_key_to_the_agents_block(self):
        self.with_extra_agent('  terra:\n    display_name: "Terra"\n')
        self.install(
            "--admin-user", ADMIN, "--room-id", ROOM, secret=lambda prompt: "typed"
        )
        before = self.config().read_text(encoding="utf-8")
        code, given = self.install(
            "--admin-user", ADMIN, "--room-id", ROOM, secret=lambda prompt: "typed"
        )
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertEqual(self.config().read_text(encoding="utf-8"), before)

    def test_a_free_bot_gets_a_password_registration_and_a_written_token(self):
        code, given = self.prepared()
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn("claude-code", self.machine.accounts)
        self.assertIn("opencode", self.machine.accounts)
        written = self.config().read_text(encoding="utf-8")
        self.assertIn('access_token: "token-claude-code"', written)
        self.assertIn('access_token: "token-opencode"', written)

    def test_the_passwords_are_saved_before_the_registration(self):
        seen: list[str] = []
        original = Machine.register

        def watching(machine_self, payload):
            if payload["username"] != ADMIN:
                stored = json.loads(self.accounts_file().read_text(encoding="utf-8"))
                seen.append(payload["username"])
                self.assertIn(payload["username"], stored)
            return original(machine_self, payload)

        Machine.register = watching
        try:
            code, _ = self.prepared()
        finally:
            Machine.register = original
        self.assertEqual(code, DONE)
        self.assertEqual(sorted(seen), ["claude-code", "opencode"])

    @unittest.skipIf(os.name == "nt", "права 0600 проверяются не на Windows")
    def test_the_passwords_file_is_readable_only_by_its_owner(self):
        self.prepared()
        mode = stat.S_IMODE(self.accounts_file().stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_the_passwords_file_is_recorded(self):
        self.prepared()
        self.assertIn(("passwords", str(self.accounts_file())), self.recorded())

    def test_no_account_is_recorded(self):
        self.prepared()
        self.assertEqual([kind for kind, _ in self.recorded() if kind == "account"], [])

    def test_a_taken_bot_without_a_password_is_a_human_step(self):
        self.machine.accounts["claude-code"] = "someone-elses"
        code, given = self.prepared()
        self.assertEqual(code, HUMAN)
        self.assertIn("уже есть", self.stdout(given))
        self.assertIn("сбросьте", self.stdout(given))

    def test_a_taken_bot_with_a_saved_password_is_entered_not_registered(self):
        self.machine.accounts["claude-code"] = "someone-elses"
        self.accounts_file().parent.mkdir(parents=True, exist_ok=True)
        self.accounts_file().write_text(
            json.dumps({"claude-code": {"password": "saved"}}), encoding="utf-8"
        )
        code, given = self.prepared()
        self.assertEqual(code, HUMAN)
        self.assertEqual(self.machine.accounts["claude-code"], "someone-elses")

    def test_a_valid_bot_token_is_left_alone(self):
        self.prepared()
        self.machine.log.clear()
        self.full()
        self.assertFalse([line for line in self.machine.log if "write-yaml" in line])

    def test_an_unowned_toml_is_a_human_step(self):
        self.ready()
        self.machine.accounts[ADMIN] = "already"
        self.toml().parent.mkdir(parents=True, exist_ok=True)
        self.toml().write_text(
            '[global]\nallow_registration = true\nregistration_token = "mine"\n',
            encoding="utf-8",
        )
        code, given = self.full()
        self.assertEqual(code, HUMAN)
        self.assertIn("access_token", self.stdout(given))

    def test_a_foreign_token_is_named_and_never_overwritten(self):
        self.ready()
        self.config().write_text(
            self.path("bridge/config.example.yaml")
            .read_text(encoding="utf-8")
            .replace(
                'access_token: "PASTE_TOKEN_HERE"',
                'access_token: "stale-token-of-another-server"',
                1,
            ),
            encoding="utf-8",
        )
        code, given = self.install("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, FAILED, self.stderr(given))
        self.assertIn("не вышло", self.stderr(given))
        self.assertIn("впишите значения сами", self.stderr(given).lower())
        self.assertIn(
            "stale-token-of-another-server", self.config().read_text(encoding="utf-8")
        )

    def test_bot_tokens_never_reach_the_output(self):
        code, given = self.prepared()
        self.assertEqual(code, DONE)
        self.assertNotIn("token-claude-code", self.stdout(given) + self.stderr(given))


class BrokerAddressTests(ServerCase):
    def prepared(self):
        self.ready()
        return self.full(secret=lambda prompt: "typed")

    def another_port(self) -> None:
        self.ready()
        self.settled()
        self.edit_config({"sessionchat_port": 9999})

    def test_a_config_without_a_port_is_accepted(self):
        code, given = self.prepared()
        self.assertEqual(code, DONE, self.stderr(given))

    def test_another_port_is_a_conflict_naming_both_sides(self):
        self.another_port()
        code, given = self.install("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, FAILED)
        self.assertIn("sessionchat_port=9999", self.stderr(given))
        self.assertIn(f"на {BROKER_PORT}", self.stderr(given))

    def test_another_homeserver_url_is_a_conflict(self):
        self.ready()
        self.settled()
        self.edit_config({"homeserver_url": "https://elsewhere.example"})
        code, given = self.install("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, FAILED)
        self.assertIn("homeserver_url", self.stderr(given))

    def test_the_start_scripts_are_never_edited(self):
        self.ready()
        self.settled()
        before = self.path("start.sh").read_text(encoding="utf-8")
        self.another_port()
        self.install("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(self.path("start.sh").read_text(encoding="utf-8"), before)


class CloseRegistrationTests(ServerCase):
    def prepared(self, *flags: str, **values):
        self.ready()
        values.setdefault("secret", lambda prompt: "typed")
        return self.full(*flags, **values)

    def test_registration_is_closed_after_the_accounts(self):
        code, given = self.prepared()
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(
            "allow_registration = false", self.toml().read_text(encoding="utf-8")
        )
        order = [line for line in self.machine.log]
        close = order.index(
            [line for line in order if "restart continuwuity" in line][0]
        )
        start = [index for index, line in enumerate(order) if line.endswith("start.sh")]
        if start:
            self.assertLess(close, start[0])

    def test_the_homeserver_is_restarted(self):
        self.prepared()
        self.assertTrue(
            [line for line in self.machine.log if line.endswith("restart continuwuity")]
        )

    def test_the_toml_is_written_in_place(self):
        self.prepared()
        inode = self.toml().stat().st_ino
        self.prepared()
        self.assertEqual(self.toml().stat().st_ino, inode)

    def test_a_confirmed_closure_is_not_warned_about(self):
        code, given = self.prepared()
        self.assertEqual(code, DONE)
        self.assertNotIn("не подтвердил", self.stderr(given))

    def test_an_unconfirmed_closure_is_a_failure(self):
        self.machine.closed_status = [401]
        code, given = self.prepared()
        self.assertEqual(code, FAILED)
        self.assertIn("не подтвердил", self.stderr(given))

    def test_a_file_closed_without_a_restart_is_repaired(self):
        self.prepared()
        self.machine.log.clear()
        self.machine.probes = 0
        self.machine.closed_status = [401, 403]
        code, given = self.install("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertTrue(
            [line for line in self.machine.log if "restart continuwuity" in line]
        )
        self.assertEqual(self.machine.probes, 3)

    def test_an_unowned_toml_is_a_human_step_with_the_exact_command(self):
        self.ready()
        self.settled()
        self.toml().parent.mkdir(parents=True, exist_ok=True)
        self.toml().write_text(
            '[global]\nallow_registration = true\nregistration_token = "mine"\n',
            encoding="utf-8",
        )
        code, given = self.install("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, HUMAN)
        self.assertIn("allow_registration = false", self.stdout(given))
        self.assertIn("restart continuwuity", self.stdout(given))

    def test_an_unowned_file_that_is_already_false_asks_only_for_the_restart(self):
        self.ready()
        self.settled()
        self.toml().parent.mkdir(parents=True, exist_ok=True)
        self.toml().write_text(
            '[global]\nallow_registration = false\nregistration_token = "mine"\n',
            encoding="utf-8",
        )
        self.machine.closed_status = [401]
        code, given = self.install("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, HUMAN)
        self.assertIn("уже стоит allow_registration = false", self.stdout(given))
        self.assertIn("restart continuwuity", self.stdout(given))
        self.assertNotIn("Поставьте allow_registration = false", self.stdout(given))

    def test_the_closure_step_waits_for_the_server_after_the_restart(self):
        code, given = self.prepared()
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertTrue(self.slept, "после рестарта никто не ждал homeserver")

    def test_a_closed_registration_is_not_closed_again(self):
        self.prepared()
        self.machine.log.clear()
        code, _ = self.install("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, DONE)
        self.assertFalse(
            [line for line in self.machine.log if "restart continuwuity" in line]
        )


class RoomTests(ServerCase):
    def prepared(self, *flags: str, **values):
        self.ready()
        values.setdefault("secret", lambda prompt: "typed")
        return self.full(*flags, **values)

    def test_the_room_from_the_option_is_written(self):
        code, given = self.prepared("--room-id", ROOM)
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(ROOM, self.config().read_text(encoding="utf-8"))

    def test_a_room_without_a_domain_is_accepted(self):
        code, given = self.prepared("--room-id", "!AbCdEf")
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn("!AbCdEf", self.config().read_text(encoding="utf-8"))

    def test_the_example_room_is_never_accepted(self):
        code, given = self.prepared("--room-id", f"!REPLACE_ME:{SERVER_NAME}")
        self.assertEqual(code, HUMAN)
        self.assertIn("всё ещё пример", self.stdout(given))

    def test_a_room_without_a_prefix_is_refused(self):
        code, given = self.prepared("--room-id", "agents")
        self.assertEqual(code, HUMAN)
        self.assertIn("должен начинаться с ! или #", self.stdout(given))

    def test_a_room_with_a_space_is_refused(self):
        code, given = self.prepared("--room-id", f"!ab cd:{SERVER_NAME}")
        self.assertEqual(code, HUMAN)
        self.assertIn("пробела", self.stdout(given))

    def test_a_room_of_another_server_is_refused(self):
        code, given = self.prepared("--room-id", "!AbCd:elsewhere.example")
        self.assertEqual(code, HUMAN)
        self.assertIn("elsewhere.example", self.stdout(given))

    def test_a_room_without_a_name_is_refused(self):
        code, given = self.prepared("--room-id", f"!:{SERVER_NAME}")
        self.assertEqual(code, HUMAN)
        self.assertIn("нет имени", self.stdout(given))

    def test_an_alias_is_accepted(self):
        code, given = self.prepared("--room-id", f"#alias:{SERVER_NAME}")
        self.assertEqual(code, DONE, self.stderr(given))

    def test_an_alias_without_a_domain_is_refused(self):
        code, given = self.prepared("--room-id", "#alias")
        self.assertEqual(code, HUMAN)
        self.assertIn("alias", self.stdout(given))

    def test_the_human_is_told_what_to_create_and_whom_to_invite(self):
        code, given = self.install(
            "--admin-user",
            ADMIN,
            stdin="",
            interactive=True,
            secret=lambda prompt: "typed",
        )
        self.assertEqual(code, HUMAN)
        self.assertIn(f"@claude-code:{SERVER_NAME}", self.stdout(given))
        self.assertIn("--room-id", self.stdout(given))

    def test_a_room_typed_in_a_terminal_is_written(self):
        self.ready()
        code, given = self.install(
            "--admin-user",
            ADMIN,
            stdin=f"{ROOM}\n",
            interactive=True,
            secret=lambda prompt: "typed",
        )
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn(ROOM, self.config().read_text(encoding="utf-8"))

    def test_an_explicit_room_does_not_replace_a_stored_one(self):
        self.prepared("--room-id", ROOM)
        code, given = self.prepared("--room-id", "!AnotherRoom")
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertNotIn("!AnotherRoom", self.config().read_text(encoding="utf-8"))
        self.assertIn("уже стоит комната", self.stderr(given))

    def test_a_config_without_the_room_key_is_never_given_one_behind_our_back(self):
        self.ready()
        self.config().write_text(
            'homeserver_url: "https://agentschat.local"\n', encoding="utf-8"
        )
        code, given = self.install("--admin-user", ADMIN, "--room-id", ROOM)
        self.assertEqual(code, FAILED)
        self.assertIn("не вышло", self.stderr(given))
        self.assertIn("впишите значения сами", self.stderr(given).lower())
        self.assertNotIn(ROOM, self.config().read_text(encoding="utf-8"))

    def test_a_valid_room_is_not_asked_again(self):
        self.prepared("--room-id", ROOM)
        self.full()
        self.assertIn("Записать комнату: уже сделано.", self.stdout(self.last_given))


class StartTests(ServerCase):
    def prepared(self, *flags: str, **values):
        self.ready()
        values.setdefault("secret", lambda prompt: "typed")
        return self.full(*flags, **values)

    def test_the_posix_start_script_is_run_without_logs(self):
        self.prepared()
        self.assertEqual(Path(self.machine.start_argv[0]).name, "sh")
        self.assertTrue(self.machine.start_argv[-1].endswith("start.sh"))
        self.assertNotIn("-Logs", self.machine.start_argv)

    def test_the_windows_start_script_is_run_with_powershell(self):
        self.prepared(platform="windows")
        self.assertTrue(
            [part for part in self.machine.start_argv if part.endswith("start.ps1")]
        )
        self.assertIn("-NoProfile", self.machine.start_argv)

    def test_a_start_failure_that_echoes_a_bot_token_does_not_print_it(self):
        self.machine.start_code = 1
        self.machine.stdout_log = "ОШИБКА: вход не удался, токен token-claude-code"
        code, given = self.prepared()
        self.assertEqual(code, FAILED)
        self.assertIn("вход не удался", self.stderr(given))
        self.assertNotIn("token-claude-code", self.stderr(given))

    def test_a_start_failure_that_echoes_every_secret_does_not_print_any(self):
        self.ready()
        self.machine.only_issued = True
        self.machine.start_code = 1
        self.machine.stdout_log = (
            "ОШИБКА: пароль parol-cheloveka, "
            "пароль бота parol-bota-izvestnaya, "
            "токен бота token-claude-code, "
            "токен регистрации tologin-token-registracii, "
            f"выданный сервером {ISSUED}"
        )
        issued = iter(["tologin-token-registracii"] + ["parol-bota-izvestnaya"] * 4)
        with patch.object(
            server_secrets, "token_urlsafe", side_effect=lambda size: next(issued)
        ):
            code, given = self.install(
                "--admin-user",
                ADMIN,
                "--room-id",
                ROOM,
                env={"PATH": "", "QUOROOM_ADMIN_PASSWORD": "parol-cheloveka"},
            )
        self.assertEqual(code, FAILED)
        self.assertIn("ОШИБКА: пароль", self.stderr(given))
        for secret in (
            "parol-cheloveka",
            "parol-bota-izvestnaya",
            "token-claude-code",
            "tologin-token-registracii",
            ISSUED,
        ):
            self.assertNotIn(secret, self.stderr(given))

    def test_a_start_failure_that_echoes_a_typed_password_does_not_print_it(self):
        self.ready()
        self.machine.start_code = 1
        self.machine.stdout_log = "ОШИБКА: вход не удался, пароль parol-s-ekrana"
        code, given = self.install(
            "--admin-user",
            ADMIN,
            "--room-id",
            ROOM,
            env={"PATH": ""},
            stdin="\n",
            interactive=True,
            secret=lambda prompt: "parol-s-ekrana",
        )
        self.assertEqual(code, FAILED)
        self.assertIn("вход не удался", self.stderr(given))
        self.assertNotIn("parol-s-ekrana", self.stderr(given))

    def test_the_start_script_output_goes_to_a_file(self):
        self.machine.stdout_log = "==> Поднимаю Docker-стек\n"
        self.prepared()
        self.assertIn(
            "==> Поднимаю Docker-стек",
            (self.path("bridge/logs/start.log")).read_text(encoding="utf-8"),
        )

    def test_a_failing_start_script_names_the_log(self):
        self.machine.start_code = 1
        self.machine.stdout_log = "ОШИБКА: нет docker/.env\n"
        code, given = self.prepared()
        self.assertEqual(code, FAILED)
        self.assertIn("нет docker/.env", self.stderr(given))
        self.assertIn("start.log", self.stderr(given))

    def test_a_broker_that_stays_silent_fails_with_the_broker_log(self):
        def silent(url: str) -> Probe:
            return (
                Probe(None, "отказано") if url.endswith("/status") else Probe(200, None)
            )

        code, given = self.full(probe=silent)
        self.assertEqual(code, FAILED)
        self.assertIn("bridge/broker.log", self.stderr(given))

    def test_a_broker_started_by_this_run_asks_for_no_restart(self):
        code, given = self.prepared()
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertNotIn("перезапустите стенд вручную", self.stderr(given))

    def test_a_running_broker_with_new_bot_tokens_is_told_to_restart(self):
        self.machine.broker_up = True
        self.machine.missing_import = 0
        self.machine.accounts.pop("claude-code", None)
        self.path("bridge/config.yaml").parent.mkdir(parents=True, exist_ok=True)
        self.path("bridge/config.yaml").write_text(
            self.path("bridge/config.example.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        self.edit_config({"room_id": ROOM}, owned=False)
        code, given = self.install(
            "--admin-user", ADMIN, "--room-id", ROOM, secret=lambda prompt: "typed"
        )
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertIn("перезапустите стенд вручную", self.stderr(given))


class RepeatTests(ServerCase):
    def installed(self):
        self.ready()
        code, given = self.install(
            "--admin-user", ADMIN, "--room-id", ROOM, secret=lambda prompt: "typed"
        )
        self.assertEqual(code, DONE, self.stderr(given))
        return given

    def test_a_repeat_run_registers_nothing_twice(self):
        self.installed()
        self.machine.log.clear()
        code, given = self.install(
            "--admin-user", ADMIN, "--room-id", ROOM, secret=lambda prompt: "typed"
        )
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertFalse(
            [line for line in self.machine.log if "installer_host.py register" in line]
        )
        self.assertFalse(
            [line for line in self.machine.log if "installer_host.py login" in line]
        )

    def test_a_repeat_run_keeps_the_existing_files(self):
        self.installed()
        before = self.toml().read_text(encoding="utf-8")
        self.full()
        self.assertEqual(self.toml().read_text(encoding="utf-8"), before)

    def test_a_repeat_run_keeps_the_record(self):
        self.installed()
        recorded = self.recorded()
        self.full()
        self.assertEqual(self.recorded(), recorded)

    def test_a_repeat_run_creates_no_certificate_again(self):
        self.installed()
        self.machine.log.clear()
        self.full()
        self.assertFalse([line for line in self.machine.log if "-cert-file" in line])


class ReportTests(ServerCase):
    def installed(self, *flags: str, **values):
        self.ready()
        values.setdefault("secret", lambda prompt: "typed")
        return self.full(*flags, **values)

    def test_the_report_names_the_broker_address(self):
        code, given = self.installed()
        self.assertEqual(code, DONE)
        self.assertIn(f"http://127.0.0.1:{BROKER_PORT}", self.stdout(given))

    def test_the_report_says_the_first_account_became_an_admin(self):
        self.machine.only_issued = True
        _, given = self.installed()
        self.assertIn("стал администратором сервера", self.stdout(given))

    def test_the_report_stays_quiet_when_the_configured_token_did_the_job(self):
        _, given = self.installed()
        self.assertNotIn("стал администратором сервера", self.stdout(given))

    def test_the_report_stays_quiet_when_the_account_was_not_created_here(self):
        self.machine.only_issued = True
        self.installed()
        _, given = self.install(
            "--admin-user", ADMIN, "--room-id", ROOM, secret=lambda prompt: "typed"
        )
        self.assertNotIn("стал администратором сервера", self.stdout(given))

    def test_the_report_names_the_renewal_command(self):
        _, given = self.installed()
        self.assertIn("mkcert -cert-file", self.stdout(given))
        self.assertIn("restart caddy", self.stdout(given))

    def test_the_report_has_no_token_and_no_password(self):
        _, given = self.installed(
            env={"PATH": "", "QUOROOM_ADMIN_PASSWORD": "top-secret-pw"}
        )
        for text in (self.stdout(given), self.stderr(given)):
            self.assertNotIn("top-secret-pw", text)
            self.assertNotIn("token-claude-code", text)

    def test_the_windows_stop_command_is_named(self):
        _, given = self.installed(platform="windows")
        self.assertIn("stop.ps1", self.stdout(given))

    def test_the_posix_stop_command_is_named(self):
        _, given = self.installed()
        self.assertIn("stop.sh", self.stdout(given))

    def test_a_renewal_command_names_the_compose_file_it_uses(self):
        _, given = self.installed()
        self.assertIn(
            str(self.path("docker/docker-compose.yml")).replace("\\", "/"),
            self.stdout(given).replace("\\", "/"),
        )

    def test_a_removal_run_fails_and_says_it_is_not_implemented_yet(self):
        self.ready()
        code, given = self.install("--remove")
        self.assertEqual(code, FAILED)
        self.assertIn("local-installers-07", self.stderr(given))


class RegistryTests(ServerCase):
    def test_the_registry_holds_the_server_first(self):
        self.assertEqual(
            [role.name for role in built_in_roles()], ["server", "participant"]
        )

    def test_the_parser_takes_the_server_options(self):
        plan = parse(
            ["--role", ROLE, "--admin-user", ADMIN, "--room-id", ROOM],
            self.given(),
            built_in_roles(),
        )
        answers = plan.answers[ROLE]
        self.assertEqual(answers["server_admin_user"], ADMIN)
        self.assertEqual(answers["server_room_id"], ROOM)

    def test_the_record_of_the_server_lives_outside_the_repository(self):
        record = built_in_roles()[0].record_path(self.given())
        self.assertEqual(record.name, "server.json")
        self.assertIn(".quoroom", str(record))
        self.assertNotIn(str(self.repo), str(record))

    def test_the_certificate_expiry_is_the_end_of_validity_not_a_later_stamp(self):
        path = self.pem_with(
            validity=der(0x30, utc("260204120000Z") + utc("290215304500Z")),
            after_validity=der(0x30, utc("310101000000Z")),
        )
        self.assertEqual(not_after(path), "15.02.2029")

    def test_a_certificate_older_than_fifty_years_keeps_its_four_digit_year(self):
        path = self.pem_with(
            validity=der(0x30, utc("260204120000Z") + der(0x18, b"20610212000000Z")),
        )
        self.assertEqual(not_after(path), "12.02.2061")

    def test_a_pem_that_is_not_a_certificate_reads_as_no_expiry(self):
        path = self.path("docker/caddy/certs/agentschat.local.pem")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("-----BEGIN CERTIFICATE-----\nZm9vYmFy\n", encoding="utf-8")
        self.assertEqual(not_after(path), "")

    def pem_with(self, validity: bytes, after_validity: bytes = b"") -> Path:
        tbs = der(
            0x30,
            b"".join(
                [
                    der(0xA0, der(0x02, b"\x01")),
                    der(0x02, b"\x02\x2a"),
                    der(0x30, b""),
                    der(0x30, b""),
                    validity,
                    der(0x30, b""),
                    after_validity,
                ]
            ),
        )
        pem = (
            "-----BEGIN CERTIFICATE-----\n"
            + base64.encodebytes(
                der(0x30, tbs + der(0x30, b"") + der(0x03, b"\x00"))
            ).decode()
            + "-----END CERTIFICATE-----\n"
        )
        path = self.path("docker/caddy/certs/agentschat.local.pem")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(pem, encoding="utf-8")
        return path


def der(tag: int, body: bytes) -> bytes:
    return bytes([tag, len(body)]) + body


def utc(stamp: str) -> bytes:
    return der(0x17, stamp.encode("ascii"))


class HelperTests(InstallerTestCase):
    def yaml_file(self, text: str, name: str = "config.yaml") -> Path:
        path = self.home / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_the_layout_finds_nested_keys(self):
        lines = installer_host.layout(
            'agents:\n  claude-code:\n    access_token: "x"\nroom_id: "!a"\n'
        )
        self.assertIn(
            ("agents.claude-code.access_token", '"x"'), [(f, v) for _, f, v in lines]
        )

    def test_comment_lines_are_not_keys(self):
        lines = installer_host.layout('# access_token: "PASTE"\nroom_id: "!a"\n')
        self.assertEqual([found for _, found, _ in lines], ["room_id"])

    def test_a_placeholder_value_is_replaced(self):
        target = self.yaml_file(
            'room_id: "!REPLACE_ME:x"\nagents:\n  claude-code:\n    access_token: "PASTE"\n'
        )
        example = self.yaml_file(
            'room_id: "!REPLACE_ME:x"\nagents:\n  claude-code:\n    access_token: "PASTE"\n',
            "config.example.yaml",
        )
        answer = installer_host.write_yaml(
            str(target),
            str(example),
            {"room_id": "!real:x", "agents.claude-code.access_token": "t"},
            True,
        )
        self.assertEqual(
            answer["written"], ["room_id", "agents.claude-code.access_token"]
        )
        self.assertNotIn("PASTE", target.read_text(encoding="utf-8"))

    def test_a_real_value_is_a_conflict_and_is_not_written(self):
        target = self.yaml_file('room_id: "!mine:x"\n')
        example = self.yaml_file('room_id: "!REPLACE_ME:x"\n', "example-a.yaml")
        answer = installer_host.write_yaml(
            str(target), str(example), {"room_id": "!other:x"}, True
        )
        self.assertEqual(answer["conflicts"], ["room_id"])
        self.assertIn("!mine:x", target.read_text(encoding="utf-8"))

    def test_an_agent_that_is_not_in_the_example_gets_its_keys_inside_its_block(self):
        target = self.yaml_file(
            'agents:\n  terra:\n    display_name: "Terra"\n', "with-terra.yaml"
        )
        example = self.yaml_file(
            'agents:\n  claude-code:\n    access_token: "PASTE"\n',
            "config.example.yaml",
        )
        answer = installer_host.write_yaml(
            str(target),
            str(example),
            {
                "agents.terra.user_id": "@terra:x",
                "agents.terra.access_token": "t",
                "agents.terra.device_id": "d",
            },
            True,
        )
        self.assertEqual(answer["conflicts"], [])
        self.assertEqual(
            sorted(answer["written"]),
            [
                "agents.terra.access_token",
                "agents.terra.device_id",
                "agents.terra.user_id",
            ],
        )
        stored = installer_host._load(str(target))
        self.assertEqual(
            stored["agents"]["terra"],
            {
                "display_name": "Terra",
                "user_id": "@terra:x",
                "access_token": "t",
                "device_id": "d",
            },
        )
        self.assertNotIn(
            "access_token:", target.read_text(encoding="utf-8").split("agents:")[0]
        )

    def test_the_copied_example_block_of_a_new_agent_is_a_placeholder(self):
        target = self.yaml_file(
            'agents:\n  terra:\n    user_id: "@terra:x"\n'
            '    access_token: "PASTE_TOKEN_HERE"\n'
            '    device_id: "PASTE_DEVICE_ID_HERE"\n',
            "with-terra.yaml",
        )
        example = self.yaml_file(
            'agents:\n  terra:\n    access_token: "PASTE_TOKEN_HERE"\n',
            "config.example.yaml",
        )
        answer = installer_host.write_yaml(
            str(target),
            str(example),
            {
                "agents.terra.access_token": "real-token",
                "agents.terra.device_id": "real-device",
            },
            True,
        )
        self.assertEqual(
            answer["written"], ["agents.terra.access_token", "agents.terra.device_id"]
        )
        stored = installer_host._load(str(target))
        self.assertEqual(stored["agents"]["terra"]["access_token"], "real-token")
        self.assertEqual(stored["agents"]["terra"]["device_id"], "real-device")

    def test_a_value_that_is_not_a_placeholder_is_still_a_conflict(self):
        target = self.yaml_file(
            'agents:\n  terra:\n    access_token: "someone-elses-token"\n',
            "with-terra.yaml",
        )
        answer = installer_host.write_yaml(
            str(target), "", {"agents.terra.access_token": "mine"}, True
        )
        self.assertEqual(answer["conflicts"], ["agents.terra.access_token"])
        self.assertEqual(
            installer_host._load(str(target))["agents"]["terra"]["access_token"],
            "someone-elses-token",
        )

    def test_a_broken_result_is_never_written_to_the_file(self):
        target = self.yaml_file(
            'agents:\n  terra:\n    access_token: "PASTE_TOKEN_HERE"\n',
            "config.yaml",
        )
        before = target.read_text(encoding="utf-8")
        answer = installer_host.write_yaml(
            str(target), "", {"agents.terra.access_token": 'unclosed " quote'}, True
        )
        self.assertEqual(answer["written"], [])
        self.assertEqual(answer["conflicts"], ["agents.terra.access_token"])
        self.assertEqual(target.read_text(encoding="utf-8"), before)

    def test_a_four_space_block_gets_its_keys_at_its_own_indent(self):
        target = self.yaml_file(
            'agents:\n    terra:\n        display_name: "Terra"\n',
            "with-terra.yaml",
        )
        answer = installer_host.write_yaml(
            str(target),
            "",
            {"agents.terra.user_id": "@terra:x", "agents.terra.access_token": "t"},
            True,
        )
        self.assertEqual(answer["conflicts"], [])
        stored = installer_host._load(str(target))
        self.assertEqual(stored["agents"]["terra"]["access_token"], "t")
        self.assertEqual(
            '        user_id: "@terra:x"\n' in target.read_text(encoding="utf-8"),
            True,
        )

    def test_a_flow_style_block_is_refused_and_the_message_says_why(self):
        target = self.yaml_file(
            'agents:\n  terra: {display_name: "Terra"}\n', "with-terra.yaml"
        )
        answer = installer_host.write_yaml(
            str(target),
            "",
            {"agents.terra.access_token": "t"},
            True,
        )
        self.assertEqual(answer["conflicts"], ["agents.terra.access_token"])
        self.assertNotIn("access_token", target.read_text(encoding="utf-8"))

    def test_a_quoted_key_is_refused_and_the_message_says_why(self):
        target = self.yaml_file(
            'agents:\n  "terra":\n    display_name: "Terra"\n', "with-terra.yaml"
        )
        answer = installer_host.write_yaml(
            str(target),
            "",
            {"agents.terra.access_token": "t"},
            True,
        )
        self.assertEqual(answer["conflicts"], ["agents.terra.access_token"])

    def test_a_missing_key_is_not_added_to_a_file_we_do_not_own(self):
        target = self.yaml_file('homeserver_url: "https://x"\n')
        example = self.yaml_file(
            'homeserver_url: "https://x"\nroom_id: "!REPLACE_ME:x"\n', "example-b.yaml"
        )
        answer = installer_host.write_yaml(
            str(target), str(example), {"room_id": "!a:x"}, False
        )
        self.assertEqual(answer["conflicts"], ["room_id"])
        self.assertNotIn("room_id", target.read_text(encoding="utf-8"))

    def test_comments_survive_a_write(self):
        target = self.yaml_file('#Access_token stays\nroom_id: "!REPLACE_ME:x"\n')
        example = self.yaml_file('room_id: "!REPLACE_ME:x"\n', "example-a.yaml")
        installer_host.write_yaml(str(target), str(example), {"room_id": "!a:x"}, True)
        self.assertIn("#Access_token stays", target.read_text(encoding="utf-8"))

    def test_the_readable_keys_never_include_a_token(self):
        path = self.yaml_file(
            'room_id: "!a:x"\naccess_token: "top"\nagents:\n  b:\n    access_token: "top"\n'
        )
        answer = installer_host.read_yaml(str(path), installer_host.READABLE)
        self.assertEqual(sorted(answer), ["agents", "room_id"])
        self.assertNotIn("top", json.dumps(answer))

    def test_a_broken_yaml_reports_the_line_without_the_text(self):
        path = self.yaml_file('access_token: "syt_secret"\nrooms: [\n')
        with self.assertRaises(installer_host.Failed) as problem:
            installer_host.read_yaml(str(path), installer_host.READABLE)
        self.assertEqual(problem.exception.file, str(path))
        self.assertNotIn("syt_secret", str(problem.exception))

    def test_a_yaml_error_names_the_line_where_the_secret_stands(self):
        path = self.yaml_file('a: 1\n  access_token: "syt_secret"\n')
        with self.assertRaises(installer_host.Failed) as problem:
            installer_host.read_yaml(str(path), installer_host.READABLE)
        self.assertEqual(problem.exception.line, 2)
        self.assertNotIn("syt_secret", str(problem.exception))
        self.assertNotIn(
            "syt_secret", json.dumps(problem.exception.payload(), default=str)
        )


class HomeserverStub(http.server.BaseHTTPRequestHandler):
    accounts: dict[str, dict] = {}
    calls: list[tuple[str, dict]] = []
    refuse_registration = False
    availability_status = 200
    first_status = 0

    def answer(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path.endswith("/register/available"):
            name = self.path.split("username=")[-1]
            if self.availability_status != 200:
                self.answer(self.availability_status, {"errcode": "M_UNKNOWN"})
                return
            if name in self.accounts:
                self.answer(400, {"errcode": "M_USER_IN_USE"})
                return
            self.answer(200, {"available": True})
            return
        if path.endswith("/account/whoami"):
            token = self.headers.get("Authorization", "").removeprefix("Bearer ")
            owner = next(
                (
                    name
                    for name, entry in self.accounts.items()
                    if entry["token"] == token
                ),
                None,
            )
            self.answer(
                200 if owner else 401,
                {"user_id": f"@{owner}:x"} if owner else {},
            )
            return
        self.answer(404, {})

    def do_POST(self) -> None:
        body = self.read_body()
        type(self).calls.append((self.path.split("?")[0], body))
        if self.path.split("?")[0].endswith("/login"):
            entry = self.accounts.get(body.get("identifier", {}).get("user", ""))
            if entry and entry["password"] == body.get("password"):
                self.answer(200, entry["answer"])
                return
            self.answer(403, {"errcode": "M_FORBIDDEN"})
            return
        if self.refuse_registration:
            self.answer(
                403, {"errcode": "M_FORBIDDEN", "error": "not accepting registrations"}
            )
            return
        if type(self).first_status and not body.get("auth"):
            self.answer(type(self).first_status, {"errcode": "M_UNKNOWN"})
            return
        token = body.get("auth", {}).get("token")
        if not body.get("auth"):
            self.answer(401, {"errcode": "M_UNAUTHORIZED", "session": "session-1"})
            return
        if token != "good-token":
            self.answer(
                401, {"errcode": "M_FORBIDDEN", "error": "Invalid registration token"}
            )
            return
        name = body["username"]
        answer = {
            "user_id": f"@{name}:x",
            "access_token": f"token-{name}",
            "device_id": f"device-{name}",
        }
        type(self).accounts[name] = {
            "token": answer["access_token"],
            "password": body["password"],
            "answer": answer,
        }
        self.answer(200, answer)

    def log_message(self, format: str, *args) -> None:
        return None


class HelperHttpTests(unittest.TestCase):
    def setUp(self):
        HomeserverStub.accounts = {}
        HomeserverStub.calls = []
        HomeserverStub.refuse_registration = False
        HomeserverStub.availability_status = 200
        HomeserverStub.first_status = 0
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), HomeserverStub)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def test_a_four_hundred_with_another_reason_is_not_a_taken_name(self):
        HomeserverStub.availability_status = 400
        with self.assertRaises(installer_host.Failed) as problem:
            installer_host.available(self.url, "terra", "")
        self.assertEqual(problem.exception.errcode, "M_UNKNOWN")

    def test_a_free_name_is_available(self):
        self.assertEqual(
            installer_host.available(self.url, "terra", ""), {"available": True}
        )

    def test_a_taken_name_is_not_available(self):
        self.assertEqual(
            installer_host.register(self.url, "terra", "пароль", "good-token", "")[
                "user_id"
            ],
            "@terra:x",
        )
        self.assertEqual(
            installer_host.available(self.url, "terra", ""), {"available": False}
        )

    def test_an_unexpected_availability_answer_is_named(self):
        HomeserverStub.availability_status = 500
        with self.assertRaises(installer_host.Failed) as problem:
            installer_host.available(self.url, "terra", "")
        self.assertEqual(problem.exception.error, "available")
        self.assertEqual(problem.exception.status, 500)

    def test_registration_asks_twice_and_returns_the_credentials(self):
        answer = installer_host.register(self.url, "terra", "пароль", "good-token", "")
        self.assertEqual(
            answer,
            {
                "user_id": "@terra:x",
                "access_token": "token-terra",
                "device_id": "device-terra",
            },
        )
        paths = [path for path, _ in HomeserverStub.calls]
        self.assertEqual(paths[-2:], ["/_matrix/client/v3/register"] * 2)

    def test_the_wrong_registration_token_is_refused_by_the_server(self):
        with self.assertRaises(installer_host.Failed) as problem:
            installer_host.register(self.url, "terra", "пароль", "bad-token", "")
        self.assertEqual(problem.exception.status, 401)
        self.assertEqual(problem.exception.errcode, "M_FORBIDDEN")

    def test_a_closed_server_answers_four_hundred_and_three(self):
        HomeserverStub.refuse_registration = True
        with self.assertRaises(installer_host.Failed) as problem:
            installer_host.register(self.url, "terra", "пароль", "good-token", "")
        self.assertEqual(problem.exception.status, 403)

    def test_login_returns_the_credentials_of_the_right_password(self):
        installer_host.register(self.url, "terra", "пароль", "good-token", "")
        answer = installer_host.login(self.url, "terra", "пароль", "")
        self.assertEqual(answer["access_token"], "token-terra")

    def test_login_with_a_wrong_password_is_refused(self):
        installer_host.register(self.url, "terra", "пароль", "good-token", "")
        with self.assertRaises(installer_host.Failed) as problem:
            installer_host.login(self.url, "terra", "не тот", "")
        self.assertEqual(problem.exception.errcode, "M_FORBIDDEN")

    def test_login_with_an_unknown_name_is_refused(self):
        with self.assertRaises(installer_host.Failed) as problem:
            installer_host.login(self.url, "nobody", "пароль", "")
        self.assertEqual(problem.exception.error, "login")

    def test_whoami_calls_a_valid_token_valid(self):
        with tempfile.TemporaryDirectory() as home:
            config = Path(home) / "config.yaml"
            example = Path(home) / "config.example.yaml"
            config.write_text(
                'agents:\n  terra:\n    user_id: "@terra:x"\n    access_token: "token-terra"\n',
                encoding="utf-8",
            )
            example.write_text(
                'agents:\n  terra:\n    access_token: "PASTE_TOKEN_HERE"\n',
                encoding="utf-8",
            )
            installer_host.register(self.url, "terra", "пароль", "good-token", "")
            self.assertEqual(
                installer_host.whoami(self.url, str(config), str(example), ""),
                {"terra": "valid"},
            )

    def test_whoami_calls_a_token_of_another_account_invalid(self):
        with tempfile.TemporaryDirectory() as home:
            config = Path(home) / "config.yaml"
            config.write_text(
                'agents:\n  terra:\n    user_id: "@terr:x"\n    access_token: "token-terra"\n',
                encoding="utf-8",
            )
            installer_host.register(self.url, "terra", "пароль", "good-token", "")
            self.assertEqual(
                installer_host.whoami(self.url, str(config), "", ""),
                {"terra": "invalid"},
            )

    def test_whoami_calls_the_examples_placeholder_a_placeholder(self):
        with tempfile.TemporaryDirectory() as home:
            config = Path(home) / "config.yaml"
            example = Path(home) / "config.example.yaml"
            config.write_text(
                'agents:\n  terra:\n    user_id: "@terra:x"\n    access_token: "PASTE_TOKEN_HERE"\n',
                encoding="utf-8",
            )
            example.write_text(
                'agents:\n  terra:\n    access_token: "PASTE_TOKEN_HERE"\n',
                encoding="utf-8",
            )
            self.assertEqual(
                installer_host.whoami(self.url, str(config), str(example), ""),
                {"terra": "placeholder"},
            )

    def test_the_closure_probe_sees_four_hundred_and_three(self):
        HomeserverStub.refuse_registration = True
        self.assertEqual(
            installer_host.probe_closed(self.url, ""),
            {"status": 403, "errcode": "M_FORBIDDEN"},
        )

    def test_the_closure_probe_sees_a_wrong_token_as_four_hundred_and_one(self):
        self.assertEqual(
            installer_host.probe_closed(self.url, ""),
            {"status": 401, "errcode": "M_FORBIDDEN"},
        )

    def test_the_closure_probe_passes_an_unexpected_first_answer_through(self):
        HomeserverStub.first_status = 429
        self.assertEqual(
            installer_host.probe_closed(self.url, ""),
            {"status": 429, "errcode": "M_UNKNOWN"},
        )

    def test_the_helper_asks_the_environment_for_nothing(self):
        self.assertFalse(installer_host.session().trust_env)

    def test_every_call_goes_through_the_helper_session_and_closes_it(self):
        asked: list[str] = []
        closed: list[bool] = []

        class Recording:
            def __enter__(self):
                return self

            def __exit__(self, *problem):
                closed.append(True)
                return False

            def get(self, url, **keywords):
                asked.append(url)

                class Stub:
                    status_code = 404

                    def json(self):
                        return {"errcode": "M_NOT_FOUND"}

                return Stub()

        with patch.object(installer_host, "session", return_value=Recording()):
            answer = installer_host.send("get", "https://agentschat.local/status")
        self.assertEqual(asked, ["https://agentschat.local/status"])
        self.assertEqual(closed, [True], "сессия осталась открытой")
        self.assertEqual(answer.status_code, 404)

    def test_a_configured_proxy_does_not_slow_the_helper_down(self):
        started = time.monotonic()
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://203.0.113.1:9",
                "HTTPS_PROXY": "http://203.0.113.1:9",
            },
        ):
            self.assertEqual(
                installer_host.available(self.url, "terra", ""), {"available": True}
            )
        self.assertLess(time.monotonic() - started, 5)

    def test_the_helper_leaves_the_proxy_environment_of_its_caller_alone(self):
        with patch.dict(os.environ, {"NO_PROXY": "was-here"}, clear=False):
            installer_host.available(self.url, "terra", "")
            self.assertEqual(os.environ["NO_PROXY"], "was-here")

    def test_a_dead_homeserver_is_named_as_such(self):
        closed = http.server.ThreadingHTTPServer(("127.0.0.1", 0), HomeserverStub)
        port = closed.server_address[1]
        closed.server_close()
        with self.assertRaises(installer_host.Failed) as problem:
            installer_host.available(f"http://127.0.0.1:{port}", "terra", "")
        self.assertEqual(problem.exception.error, "get")
        self.assertEqual(problem.exception.errcode, "ConnectionError")

    def test_the_closure_probe_never_registers_an_account(self):
        HomeserverStub.refuse_registration = False
        installer_host.probe_closed(self.url, "")
        self.assertEqual(HomeserverStub.accounts, {})


class HelperBoundaryTests(unittest.TestCase):
    def test_the_installer_core_imports_no_third_party_library(self):
        done = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.path.insert(0, '.');"
                "import sessionchat.installer.server;"
                "print([name for name in ('yaml', 'requests') if name in sys.modules])",
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "[]")

    def test_the_helper_prints_nothing_to_stderr_even_when_it_fails(self):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / "config.yaml"
            path.write_text('a: 1\n  access_token: "syt_secret"\n', encoding="utf-8")
            answer = io.StringIO()
            errors = io.StringIO()
            with (
                patch("sys.stdin", io.StringIO(json.dumps({"path": str(path)}))),
                patch("sys.stdout", answer),
                patch("sys.stderr", errors),
            ):
                code = installer_host.main(["read-yaml"])
        self.assertEqual(code, 1)
        self.assertEqual(errors.getvalue(), "")

    def test_the_answer_of_a_failure_carries_only_the_allowed_fields(self):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / "config.yaml"
            path.write_text('a: 1\n  access_token: "syt_secret"\n', encoding="utf-8")
            with self.assertRaises(installer_host.Failed) as problem:
                installer_host.read_yaml(str(path), installer_host.READABLE)
        self.assertEqual(
            sorted(problem.exception.payload()),
            ["errcode", "error", "file", "line", "status"],
        )


class HelperMainTests(unittest.TestCase):
    def call(self, command: str, payload: dict) -> tuple[int, dict]:
        answer = io.StringIO()
        errors = io.StringIO()
        with (
            patch("sys.stdin", io.StringIO(json.dumps(payload))),
            patch("sys.stdout", answer),
            patch("sys.stderr", errors),
        ):
            code = installer_host.main([command])
        return code, json.loads(answer.getvalue())

    def test_a_known_command_answers_zero_and_json(self):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / "config.yaml"
            path.write_text('room_id: "!a:x"\n', encoding="utf-8")
            code, answer = self.call("read-yaml", {"path": str(path)})
        self.assertEqual(code, 0)
        self.assertEqual(answer, {"room_id": "!a:x"})

    def test_an_unknown_command_answers_two_and_names_itself(self):
        code, answer = self.call("выдумка", {})
        self.assertEqual(code, 2)
        self.assertEqual(answer, {"error": "unknown", "errcode": "выдумка"})

    def test_a_broken_payload_answers_one_with_the_key_that_is_missing(self):
        code, answer = self.call("read-yaml", {})
        self.assertEqual(code, 1)
        self.assertEqual(answer["error"], "read-yaml")
        self.assertEqual(answer["errcode"], "KeyError")

    def test_a_missing_library_answers_one_with_the_library_name(self):
        with patch.object(installer_host, "LIBRARIES", ("нет_такой",)):
            code, answer = self.call("imports", {})
        self.assertEqual(code, 1)
        self.assertEqual(
            answer,
            {
                "error": "imports",
                "errcode": "нет_такой",
                "status": 0,
                "file": "",
                "line": 0,
            },
        )

    def test_the_answers_carry_no_ansi_and_no_source_text(self):
        with tempfile.TemporaryDirectory() as home:
            path = Path(home) / "config.yaml"
            path.write_text('a: 1\n  access_token: "syt_secret"\n', encoding="utf-8")
            code, answer = self.call("read-yaml", {"path": str(path)})
        self.assertEqual(code, 1)
        self.assertEqual(answer["line"], 2)
        self.assertNotIn("syt_secret", json.dumps(answer))


if __name__ == "__main__":
    unittest.main()
