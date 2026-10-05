from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import secrets
import shlex
import shutil
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .boundaries import Boundaries, WINDOWS
from .catalogue import text
from .ownership import PurgeTarget, prune_record_home
from .report import Left, left_lines
from .roles import Role, RoleOptions
from .steps import (
    FoundStep,
    NeedsHuman,
    OwnedStep,
    Run,
    State,
    approved,
    report_kept,
    unapproved,
    unlink,
)

ROLE = "server"
INSTALLER_HOME = ".quoroom"
STATE_DIR = "state"
LOGS_DIR = "logs"
DOCKER_DIR = "docker"
COMPOSE_FILE = "docker-compose.yml"
SERVER_NAME = "agentschat.local"
BROKER_PORT = 8770
BROKER_URL = f"http://127.0.0.1:{BROKER_PORT}"
ADMIN_DEST = "server_admin_user"
ROOM_DEST = "server_room_id"
PASSWORD_VARIABLE = "QUOROOM_ADMIN_PASSWORD"
VENV_KIND = "venv"
CERT_KIND = "cert"
FILE_KIND = "file"
VOLUME_KIND = "volume"
PASSWORDS_KIND = "passwords"
STATE_KIND = "state"
BROKER_DB = "agentschat.db"
BROKER_PID = "broker.pid"
BROKER_STATE_FILES = (
    BROKER_DB,
    f"{BROKER_DB}-wal",
    f"{BROKER_DB}-shm",
    f"{BROKER_DB}-journal",
    BROKER_PID,
)
ACCOUNTS_FILE = "server-accounts.json"
CONFIG_NAME = "config.yaml"
CONFIG_EXAMPLE = "config.example.yaml"
ENV_FILE = ".env"
ENV_EXAMPLE = ".env.example"
TOML_NAME = "continuwuity.toml"
TOML_EXAMPLE = "continuwuity.toml.example"
CERT_NAME = "agentschat.local"
CERT_KEY = "agentschat.local-key"
BROKER_LOG = "broker.log"
KIND_WORDS = {
    FILE_KIND: "server.kind_files",
    CERT_KIND: "server.kind_certs",
    PASSWORDS_KIND: "server.kind_passwords",
    STATE_KIND: "server.kind_state",
    VENV_KIND: "server.kind_venv",
}
INSTALL_ENTRY = {"windows": "install.ps1", "linux": "install.sh"}
ISSUED = re.compile(r"using the registration token ([A-Za-z0-9]+)")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
LANGUAGE_LINE = re.compile(r"^language:.*$", re.M)
IMAGE = re.compile(r"^\s*image:\s*(\S+)", re.M)
SEQUENCE = 0x30
CONTEXT_0 = 0xA0
UTC_TIME = 0x17
GENERALIZED_TIME = 0x18
TIMES = (UTC_TIME, GENERALIZED_TIME)
TOML_KEY = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
READY_TRIES = 30
READY_DELAY = 2.0
START_TRIES = 15
SILENCE_TRIES = 15
GATEWAY_STATUSES = (502, 503, 504)


def docker_dir(run: Run) -> Path:
    return run.boundaries.repo / DOCKER_DIR


def compose_file(run: Run) -> Path:
    return docker_dir(run) / COMPOSE_FILE


def toml_path(run: Run) -> Path:
    return docker_dir(run) / "continuwuity" / TOML_NAME


def toml_example(run: Run) -> Path:
    return toml_path(run).with_name(TOML_EXAMPLE)


def env_path(run: Run) -> Path:
    return docker_dir(run) / ENV_FILE


def config_path(run: Run) -> Path:
    return run.boundaries.repo / "bridge" / CONFIG_NAME


def config_example(run: Run) -> Path:
    return config_path(run).with_name(CONFIG_EXAMPLE)


def certs_dir(run: Run) -> Path:
    return docker_dir(run) / "caddy" / "certs"


def cert_path(run: Run) -> Path:
    return certs_dir(run) / f"{CERT_NAME}.pem"


def cert_key_path(run: Run) -> Path:
    return certs_dir(run) / f"{CERT_KEY}.pem"


def venv_dir(run: Run) -> Path:
    return run.boundaries.repo / "bridge" / ".venv"


def venv_python(run: Run) -> Path:
    windows = run.boundaries.platform == WINDOWS
    return (
        venv_dir(run)
        / ("Scripts" if windows else "bin")
        / ("python.exe" if windows else "python")
    )


def host_script(run: Run) -> Path:
    return run.boundaries.repo / "bridge" / "installer_host.py"


def accounts_path(run: Run) -> Path:
    return run.boundaries.repo / "bridge" / STATE_DIR / ACCOUNTS_FILE


def state_dir(run: Run) -> Path:
    return run.boundaries.repo / "bridge" / STATE_DIR


def broker_log(run: Run) -> Path:
    return run.boundaries.repo / "bridge" / BROKER_LOG


def stop_log_path(run: Run) -> Path:
    return run.boundaries.repo / "bridge" / LOGS_DIR / "stop.log"


def broker_state(run: Run) -> list[str]:
    directory = state_dir(run)
    passwords = set(run.ownership_of(ROLE).of_kind(PASSWORDS_KIND))
    return [
        str(directory / name)
        for name in BROKER_STATE_FILES
        if (directory / name).is_file() and str(directory / name) not in passwords
    ]


def kept_while_up(run: Run) -> tuple[Path, ...]:
    return (
        toml_path(run),
        cert_path(run),
        cert_key_path(run),
        env_path(run),
        docker_dir(run) / "element" / "config.json",
        docker_dir(run) / "caddy" / "Caddyfile",
    )


def owned_toml(run: Run) -> bool:
    return ours(run, FILE_KIND, toml_path(run))


def foreign_files(run: Run) -> tuple[str, ...]:
    wanted = (
        env_path(run),
        toml_path(run),
        config_path(run),
        cert_path(run),
        cert_key_path(run),
        accounts_path(run),
    )
    ownership = run.ownership_of(ROLE)
    return tuple(
        str(path)
        for path in wanted
        if path.is_file()
        and not any(
            ownership.owns(kind, str(path))
            for kind in (FILE_KIND, CERT_KIND, PASSWORDS_KIND)
        )
    )


def install_logs(run: Run) -> list[Left]:
    files = tuple(
        str(path)
        for path in (logs_path(run), broker_log(run), stop_log_path(run))
        if path.is_file()
    )
    if not files:
        return []
    return [
        Left(run.t("server.logs_kept"), files),
        Left(run.t("server.logs_remove", command=removal_command(run, files))),
    ]


def removal_command(run: Run, files: Sequence[str]) -> str:
    if run.boundaries.platform == WINDOWS:
        quoted = ", ".join("'" + name.replace("'", "''") + "'" for name in files)
        return f"Remove-Item -Force -LiteralPath {quoted}"
    return "rm -f " + " ".join(shlex.quote(name) for name in files)


def compose_images(run: Run) -> list[str]:
    try:
        text = compose_file(run).read_text(encoding="utf-8")
    except OSError:
        return []
    return list(dict.fromkeys(IMAGE.findall(text)))


def logs_path(run: Run) -> Path:
    return run.boundaries.repo / "bridge" / LOGS_DIR / "start.log"


def record_path(boundaries: Boundaries) -> Path:
    return boundaries.home / INSTALLER_HOME / "installer" / f"{ROLE}.json"


def server_url() -> str:
    return f"https://{SERVER_NAME}"


def compose_argv(run: Run, *args: str) -> list[str]:
    return ["docker", "compose", "-f", str(compose_file(run)), *args]


def ours(run: Run, kind: str, path: Path) -> bool:
    return run.ownership_of(ROLE).owns(kind, str(path))


class HostRefused(RuntimeError):
    def __init__(self, message: str, answer: dict) -> None:
        super().__init__(message)
        self.answer = answer


def host_call(run: Run, command: str, payload: dict) -> dict:
    done = run.boundaries.run(
        [str(venv_python(run)), str(host_script(run)), command],
        stdin=json.dumps(payload, ensure_ascii=True),
    )
    answer = _json(done.stdout)
    if done.returncode != 0 or answer.get("error"):
        raise HostRefused(host_failure(run, command, answer), answer)
    return answer


def _json(text: str | None) -> dict:
    try:
        answer = json.loads(text or "{}")
    except ValueError:
        return {}
    return answer if isinstance(answer, dict) else {}


def host_failure(run: Run, command: str, answer: dict) -> str:
    parts = [run.t("server.host_failed", command=command)]
    for key, message in (
        ("errcode", "server.host_code"),
        ("status", "server.host_http"),
        ("file", "server.host_file"),
        ("line", "server.host_line"),
    ):
        if answer.get(key):
            parts.append(run.t(message, value=answer[key]))
    return ": ".join(parts) + "."


def text_of(run: Run, argv: Sequence[str]) -> str:
    try:
        done = run.boundaries.run([str(part) for part in argv])
    except OSError:
        return ""
    return (done.stdout or "") if done.returncode == 0 else ""


def lines_of(run: Run, argv: Sequence[str]) -> list[str]:
    return [line for line in text_of(run, argv).splitlines() if line.strip()]


def broker_answers(run: Run) -> bool:
    return run.boundaries.probe(f"{BROKER_URL}/status").status is not None


def docker_answers(run: Run) -> bool:
    try:
        return run.boundaries.run(["docker", "info"]).returncode == 0
    except OSError:
        return False


def containers(run: Run) -> list[str]:
    return lines_of(run, compose_argv(run, "ps", "-a", "-q"))


def volume_exists(run: Run, name: str) -> bool:
    try:
        return run.boundaries.run(["docker", "volume", "inspect", name]).returncode == 0
    except OSError:
        return False


def project_name(run: Run) -> str:
    return str(
        _json(text_of(run, compose_argv(run, "config", "--format", "json"))).get("name")
        or ""
    )


def project_volumes(run: Run) -> list[str]:
    argv = ["docker", "volume", "ls", "--format", "{{.Name}}"]
    name = project_name(run)
    if name:
        argv += ["--filter", f"label=com.docker.compose.project={name}"]
    return lines_of(run, argv)


def ca_bundle(run: Run) -> str:
    root = text_of(run, ["mkcert", "-CAROOT"]).strip()
    bundle = Path(root) / "rootCA.pem" if root else Path("rootCA.pem")
    if not bundle.is_file():
        raise RuntimeError(run.t("server.ca_root_missing", bundle=bundle))
    return str(bundle)


def toml_lines(run: Run) -> list[str]:
    path = toml_path(run)
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def toml_value(lines: Sequence[str], key: str) -> tuple[str, int]:
    for number, line in enumerate(lines, start=1):
        match = TOML_KEY.match(line)
        if match and match.group(1) == key:
            return match.group(2).strip().strip('"'), number
    return "", 0


def toml_place(lines: Sequence[str], key: str, value: str) -> list[str]:
    placed = []
    for line in lines:
        match = TOML_KEY.match(line)
        if match and match.group(1) == key:
            placed.append(f"{match.group(1)} = {value}")
        else:
            placed.append(line)
    return placed


def write_toml(run: Run, lines: Sequence[str]) -> None:
    with toml_path(run).open("w", encoding="utf-8") as sink:
        sink.write("\n".join(lines) + "\n")


@dataclass(frozen=True)
class ToolStep:
    name: str
    argv: tuple[str, ...]
    windows_instruction: str
    linux_instruction: str

    def check(self, run: Run) -> State:
        try:
            done = run.boundaries.run([*self.argv])
        except OSError:
            return State.TODO
        return State.DONE if done.returncode == 0 else State.TODO

    def apply(self, run: Run) -> None:
        key = (
            self.windows_instruction
            if run.boundaries.platform == WINDOWS
            else self.linux_instruction
        )
        raise NeedsHuman(run.t(key))


@dataclass(frozen=True)
class ServerNameStep:
    name: str = "check_server_name"

    def check(self, run: Run) -> State:
        found = run.boundaries.resolve(SERVER_NAME)
        return State.DONE if found and all(loopback(a) for a in found) else State.TODO

    def apply(self, run: Run) -> None:
        raise NeedsHuman(hosts_instruction(run))


def loopback(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def hosts_instruction(run: Run) -> str:
    key = (
        "server.hosts_instruction_windows"
        if run.boundaries.platform == WINDOWS
        else "server.hosts_instruction_linux"
    )
    return run.t(key, server=SERVER_NAME)


@dataclass
class VenvStep:
    name: str = "create_venv"
    python: str = sys.executable

    def check(self, run: Run) -> State:
        if not venv_python(run).is_file():
            return State.TODO
        try:
            host_call(run, "imports", {})
        except HostRefused:
            return State.TODO
        return State.DONE

    def apply(self, run: Run) -> None:
        fresh = not venv_python(run).is_file()
        created = run.boundaries.run([self.python, "-m", "venv", str(venv_dir(run))])
        if created.returncode != 0:
            raise RuntimeError(venv_failure(run, created))
        if fresh:
            run.record(ROLE, VENV_KIND, str(venv_dir(run)))
        pip = run.boundaries.run(
            [
                str(venv_python(run)),
                "-m",
                "pip",
                "install",
                "-r",
                str(run.boundaries.repo / "bridge" / "requirements.txt"),
            ]
        )
        if pip.returncode != 0:
            raise RuntimeError(venv_failure(run, pip))
        host_call(run, "imports", {})


def venv_failure(run: Run, result) -> str:
    tail = [
        line
        for line in (result.stderr or result.stdout or "").splitlines()
        if line.strip()
    ]
    return run.t(
        "server.venv_failed", detail=tail[-1] if tail else run.t("server.no_output")
    )


@dataclass(frozen=True)
class CertificateStep:
    name: str = "issue_certificate"

    def check(self, run: Run) -> State:
        return (
            State.DONE
            if cert_path(run).is_file() and cert_key_path(run).is_file()
            else State.TODO
        )

    def apply(self, run: Run) -> None:
        certs_dir(run).mkdir(parents=True, exist_ok=True)
        done = run.boundaries.run(
            [
                "mkcert",
                "-cert-file",
                str(cert_path(run)),
                "-key-file",
                str(cert_key_path(run)),
                SERVER_NAME,
            ]
        )
        if done.returncode != 0 or not cert_path(run).is_file():
            raise RuntimeError(mkcert_failure(run, done))
        for path in (cert_path(run), cert_key_path(run)):
            run.record(ROLE, CERT_KIND, str(path))


def mkcert_failure(run: Run, result) -> str:
    detail = (result.stderr or result.stdout or "").strip()
    return run.t("server.mkcert_failed", detail=detail)


@dataclass(frozen=True)
class EnvFileStep:
    name: str = "create_env_file"

    def check(self, run: Run) -> State:
        problem = env_problem(run)
        if problem:
            raise RuntimeError(problem)
        return State.DONE if env_path(run).is_file() else State.TODO

    def apply(self, run: Run) -> None:
        if env_path(run).is_file():
            raise RuntimeError(run.t("server.file_exists", path=env_path(run)))
        env_path(run).write_text(
            env_path(run).with_name(ENV_EXAMPLE).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        run.record(ROLE, FILE_KIND, str(env_path(run)))


def env_problem(run: Run) -> str:
    path = env_path(run)
    if not path.is_file():
        return ""
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip().startswith("SERVER_NAME="):
            given = line.split("=", 1)[1].strip()
            if given != SERVER_NAME:
                return run.t(
                    "server.env_server_name_differs",
                    path=path,
                    number=number,
                    given=given,
                    server=SERVER_NAME,
                )
            return ""
    return run.t("server.env_server_name_missing", path=path)


@dataclass(frozen=True)
class TomlFileStep:
    name: str = "create_toml_file"

    def check(self, run: Run) -> State:
        problem = toml_problem(run)
        if problem:
            raise RuntimeError(problem)
        return State.DONE if toml_path(run).is_file() else State.TODO

    def apply(self, run: Run) -> None:
        if toml_path(run).is_file():
            raise RuntimeError(run.t("server.file_exists", path=toml_path(run)))
        token = run.secrets.register(secrets.token_urlsafe(32))
        rendered = toml_place(
            toml_example(run).read_text(encoding="utf-8").splitlines(),
            "registration_token",
            f'"{token}"',
        )
        write_toml(run, rendered)
        run.record(ROLE, FILE_KIND, str(toml_path(run)))


def toml_problem(run: Run) -> str:
    path = toml_path(run)
    if not path.is_file():
        return ""
    lines = toml_lines(run)
    for key in ("allow_registration", "registration_token"):
        value, number = toml_value(lines, key)
        if not number:
            return run.t("server.toml_line_missing", path=path, setting=key)
        if not value:
            return run.t(
                "server.toml_line_empty", path=path, number=number, setting=key
            )
    given, _ = toml_value(lines, "registration_token")
    sample, _ = toml_value(
        toml_example(run).read_text(encoding="utf-8").splitlines(), "registration_token"
    )
    if given == sample:
        return run.t("server.toml_token_is_example", path=path, example=TOML_EXAMPLE)
    return ""


def served_status(status: int | None) -> bool:
    return status is not None and status not in GATEWAY_STATUSES


@dataclass
class InfrastructureStep:
    name: str = "start_infrastructure"
    sleep: Callable[[float], None] = time.sleep

    def check(self, run: Run) -> State:
        probe = run.boundaries.probe(f"{server_url()}/_matrix/client/versions")
        if probe.untrusted:
            return State.DONE
        return State.DONE if served_status(probe.status) else State.TODO

    def apply(self, run: Run) -> None:
        before = self.volumes(run)
        up = run.boundaries.run(compose_argv(run, "up", "-d"))
        try:
            if up.returncode != 0:
                raise RuntimeError(compose_failure(run, "docker compose up -d", up))
            self.wait_for_server(run)
        finally:
            self.record_new(run, before)

    def wait_for_server(self, run: Run) -> None:
        for _ in range(READY_TRIES):
            if self.check(run) is State.DONE:
                return
            self.sleep(READY_DELAY)
        probe = run.boundaries.probe(f"{server_url()}/_matrix/client/versions")
        raise RuntimeError(
            run.t(
                "server.server_silent",
                server=SERVER_NAME,
                seconds=f"{READY_TRIES * READY_DELAY:.0f}",
                reason=probe.error or probe.status,
                compose=compose_file(run),
            )
        )

    def project(self, run: Run) -> str:
        return project_name(run)

    def volumes(self, run: Run) -> set[str]:
        return set(project_volumes(run))

    def record_new(self, run: Run, before: set[str]) -> None:
        declared = set(lines_of(run, compose_argv(run, "config", "--volumes")))
        for name in sorted(self.volumes(run) - before):
            if any(name.endswith(key) for key in declared):
                run.record(ROLE, VOLUME_KIND, name)


@dataclass(frozen=True)
class TrustStep:
    name: str = "check_certificate_trust"

    def check(self, run: Run) -> State:
        probe = run.boundaries.probe(f"{server_url()}/_matrix/client/versions")
        return State.DONE if probe.status is not None else State.TODO

    def apply(self, run: Run) -> None:
        probe = run.boundaries.probe(f"{server_url()}/_matrix/client/versions")
        raise NeedsHuman(trust_instruction(run, probe.error or ""))


def trust_instruction(run: Run, reason: str) -> str:
    if run.boundaries.platform == WINDOWS:
        command = "mkcert -install"
    else:
        command = run.t("server.trust_command_linux", caroot=caroot(run))
    sentences = [run.t("server.trust_instruction", server=SERVER_NAME, command=command)]
    if reason:
        sentences.append(run.t("server.trust_server_said", reason=reason))
    sentences.append(run.t("server.trust_retry"))
    return " ".join(sentences)


def caroot(run: Run) -> str:
    return text_of(run, ["mkcert", "-CAROOT"]).strip()


@dataclass(frozen=True)
class ConfigStep:
    name: str = "create_config"

    def check(self, run: Run) -> State:
        if not config_path(run).is_file():
            return State.TODO
        host_call(run, "read-yaml", {"path": str(config_path(run))})
        return State.DONE

    def apply(self, run: Run) -> None:
        if config_path(run).is_file():
            return
        config_path(run).write_text(new_config(run), encoding="utf-8")
        run.record(ROLE, FILE_KIND, str(config_path(run)))


def new_config(run: Run) -> str:
    return LANGUAGE_LINE.sub(
        f"language: {run.boundaries.lang}",
        config_example(run).read_text(encoding="utf-8"),
        count=1,
    )


@dataclass
class HumanAccountStep:
    name: str = "create_human_account"
    username: str = ""
    became_admin: bool = False

    def check(self, run: Run) -> State:
        given = self.username or str(
            run.plan.answers.get(ROLE, {}).get(ADMIN_DEST) or ""
        )
        if not given:
            return State.TODO
        return State.DONE if not available(run, given) else State.TODO

    def apply(self, run: Run) -> None:
        username = self.asked(run)
        if not username:
            raise NeedsHuman(run.t("server.admin_user_needed"))
        if not available(run, username):
            return
        if not ours(run, FILE_KIND, toml_path(run)):
            raise NeedsHuman(manual_account(run, username))
        password = admin_password(run)
        try:
            register(run, username, password, self.token(run))
        except RegistrationRefused as refused:
            if (refused.status, refused.errcode) != (401, "M_FORBIDDEN"):
                raise NeedsHuman(refused.reason) from None
        else:
            return
        register(run, username, password, run.secrets.register(issued_token(run)))
        self.became_admin = True

    def token(self, run: Run) -> str:
        value, _ = toml_value(toml_lines(run), "registration_token")
        return run.secrets.register(value)

    def asked(self, run: Run) -> str:
        if not self.username:
            self.username = asked_admin_user(run)
        return self.username


class RegistrationRefused(Exception):
    def __init__(self, reason: str, errcode: str, status: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.errcode = errcode
        self.status = status


def asked_admin_user(run: Run) -> str:
    given = str(run.plan.answers.get(ROLE, {}).get(ADMIN_DEST) or "")
    if given:
        return given
    if not run.boundaries.stdin.isatty():
        return ""
    run.say(run.t("server.ask_admin_user"))
    return run.boundaries.stdin.readline().strip()


def admin_password(run: Run) -> str:
    from_env = run.boundaries.env.get(PASSWORD_VARIABLE, "")
    if from_env:
        return run.secrets.register(from_env)
    if not run.boundaries.stdin.isatty():
        raise NeedsHuman(
            run.t("server.admin_password_needed", variable=PASSWORD_VARIABLE)
        )
    return run.secrets.register(
        run.boundaries.secret(run.t("server.ask_admin_password"))
    )


def manual_account(run: Run, username: str) -> str:
    return run.t(
        "server.account_manual",
        username=username,
        toml=TOML_NAME,
        script=run.boundaries.repo / "bridge" / "register_account.py",
    )


def available(run: Run, username: str) -> bool:
    answer = host_call(
        run,
        "available",
        {"url": server_url(), "username": username, "ca_file": ca_bundle(run)},
    )
    return bool(answer.get("available"))


def register(run: Run, username: str, password: str, token: str) -> None:
    try:
        host_call(
            run,
            "register",
            {
                "url": server_url(),
                "username": username,
                "password": password,
                "token": token,
                "ca_file": ca_bundle(run),
            },
        )
    except HostRefused as refused:
        raise RegistrationRefused(
            registration_reason(run, refused),
            str(refused.answer.get("errcode") or ""),
            int(refused.answer.get("status") or 0),
        ) from None


def registration_reason(run: Run, refused: HostRefused) -> str:
    if int(refused.answer.get("status") or 0) == 403:
        return run.t(
            "server.registration_closed",
            toml=toml_path(run),
            compose=compose_file(run),
        )
    return str(refused)


def issued_token(run: Run) -> str:
    done = run.boundaries.run(
        compose_argv(run, "logs", "--no-log-prefix", "continuwuity")
    )
    text = ANSI.sub("", f"{done.stdout or ''}\n{done.stderr or ''}")
    found = ISSUED.findall(text)
    if not found:
        raise NeedsHuman(
            run.t("server.issued_token_missing", compose=compose_file(run))
        )
    return found[-1]


@dataclass
class BotAccountStep:
    name: str = "create_bot_accounts"

    def check(self, run: Run) -> State:
        return State.DONE if not self.pending(run) else State.TODO

    def statuses(self, run: Run) -> dict[str, str]:
        return host_call(
            run,
            "whoami",
            {
                "url": server_url(),
                "config": str(config_path(run)),
                "example": str(config_example(run)),
                "ca_file": ca_bundle(run),
            },
        )

    def pending(self, run: Run) -> list[str]:
        return [
            agent for agent, state in self.statuses(run).items() if state != "valid"
        ]

    def apply(self, run: Run) -> None:
        if not ours(run, FILE_KIND, toml_path(run)):
            raise NeedsHuman(manual_bots(run))
        for agent in self.pending(run):
            self.one(run, agent)

    def one(self, run: Run, agent: str) -> None:
        password = self.saved(run).get(agent, {}).get("password")
        if not password:
            if available(run, agent):
                password = self.remember(run, agent)
            else:
                raise NeedsHuman(run.t("server.bot_password_unknown", agent=agent))
        self.write(run, agent, self.enter(run, agent, password))

    def enter(self, run: Run, agent: str, password: str) -> dict:
        base = {
            "url": server_url(),
            "username": agent,
            "password": password,
            "ca_file": ca_bundle(run),
        }
        if available(run, agent):
            token, _ = toml_value(toml_lines(run), "registration_token")
            answer = host_call(
                run, "register", {**base, "token": run.secrets.register(token)}
            )
        else:
            try:
                answer = host_call(run, "login", base)
            except HostRefused as refused:
                raise NeedsHuman(
                    run.t("server.bot_password_refused", agent=agent, refused=refused)
                ) from None
        return {
            key: run.secrets.register(str(answer.get(key) or ""))
            if key == "access_token"
            else str(answer.get(key) or "")
            for key in ("user_id", "access_token", "device_id")
        }

    def saved(self, run: Run) -> dict:
        path = accounts_path(run)
        if not path.is_file():
            return {}
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return {}
        return stored if isinstance(stored, dict) else {}

    def remember(self, run: Run, agent: str) -> str:
        path = accounts_path(run)
        stored = self.saved(run)
        password = run.secrets.register(secrets.token_urlsafe(24))
        stored[agent] = {"password": password}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(stored, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if os.name != "nt":
            path.chmod(0o600)
        run.record(ROLE, PASSWORDS_KIND, str(path))
        return password

    def write(self, run: Run, agent: str, answer: dict) -> None:
        write_config(
            run,
            {
                f"agents.{agent}.user_id": answer["user_id"],
                f"agents.{agent}.access_token": answer["access_token"],
                f"agents.{agent}.device_id": answer["device_id"],
            },
        )


def manual_bots(run: Run) -> str:
    return run.t("server.bots_manual", toml=TOML_NAME, config=config_path(run))


@dataclass(frozen=True)
class BrokerAddressStep:
    name: str = "check_broker_address"

    def check(self, run: Run) -> State:
        problem = broker_problem(run)
        if problem:
            raise RuntimeError(problem)
        return State.DONE

    def apply(self, run: Run) -> None:
        raise RuntimeError(
            broker_problem(run) or run.t("server.config_fine", path=config_path(run))
        )


def broker_problem(run: Run) -> str:
    stored = host_call(run, "read-yaml", {"path": str(config_path(run))})
    port = int(stored.get("sessionchat_port", BROKER_PORT))
    if port != BROKER_PORT:
        return run.t(
            "server.broker_port_wrong",
            path=config_path(run),
            port=port,
            expected=BROKER_PORT,
        )
    url = str(stored.get("homeserver_url") or "")
    if url and SERVER_NAME not in url:
        return run.t(
            "server.homeserver_url_wrong",
            path=config_path(run),
            url=url,
            address=server_url(),
        )
    return ""


@dataclass
class CloseRegistrationStep:
    name: str = "close_registration"
    sleep: Callable[[float], None] = time.sleep

    def check(self, run: Run) -> State:
        value, _ = toml_value(toml_lines(run), "allow_registration")
        if value != "false":
            return State.TODO
        return State.DONE if self.confirmed(run) else State.TODO

    def apply(self, run: Run) -> None:
        if not ours(run, FILE_KIND, toml_path(run)):
            raise NeedsHuman(manual_close(run))
        write_toml(run, toml_place(toml_lines(run), "allow_registration", "false"))
        run.boundaries.run(compose_argv(run, "restart", "continuwuity"))
        InfrastructureStep(sleep=self.sleep).wait_for_server(run)
        if not self.confirmed(run):
            raise RuntimeError(closure_unconfirmed(run))

    def confirmed(self, run: Run) -> bool:
        answer = host_call(
            run, "probe-closed", {"url": server_url(), "ca_file": ca_bundle(run)}
        )
        return int(answer.get("status") or 0) == 403


def closure_unconfirmed(run: Run) -> str:
    return run.t("server.closure_unconfirmed", compose=compose_file(run))


def manual_close(run: Run) -> str:
    if toml_value(toml_lines(run), "allow_registration")[0] == "false":
        return run.t(
            "server.close_manual_restart",
            toml=toml_path(run),
            compose=compose_file(run),
        )
    return run.t(
        "server.close_manual_edit",
        name=TOML_NAME,
        toml=toml_path(run),
        compose=compose_file(run),
    )


@dataclass(frozen=True)
class RoomStep:
    name: str = "write_room"

    def check(self, run: Run) -> State:
        asked = str(run.plan.answers.get(ROLE, {}).get(ROOM_DEST) or "")
        stored = room_id(run)
        if asked and stored and asked != stored and not room_problem(run, stored):
            run.warn_once(
                f"room:{stored}",
                run.t(
                    "server.room_differs",
                    config=CONFIG_NAME,
                    stored=stored,
                    asked=asked,
                    path=config_path(run),
                ),
            )
        return State.DONE if stored and not room_problem(run, stored) else State.TODO

    def apply(self, run: Run) -> None:
        interactive = run.boundaries.stdin.isatty()
        given = str(run.plan.answers.get(ROLE, {}).get(ROOM_DEST) or "")
        if not given and interactive:
            run.say(room_instruction(run))
            given = run.boundaries.stdin.readline().strip()
        problem = room_problem(run, given)
        if problem:
            raise NeedsHuman(
                problem if interactive else f"{problem}\n{room_instruction(run)}"
            )
        write_config(run, {"room_id": given})


def write_config(run: Run, values: dict) -> None:
    answer = host_call(
        run,
        "write-yaml",
        {
            "path": str(config_path(run)),
            "example": str(config_example(run)),
            "owned": ours(run, FILE_KIND, config_path(run)),
            "values": values,
        },
    )
    conflicts = [str(name) for name in answer.get("conflicts", [])]
    if conflicts:
        raise RuntimeError(
            run.t(
                "server.config_conflicts",
                path=config_path(run),
                names=", ".join(conflicts),
            )
        )


def room_id(run: Run) -> str:
    stored = host_call(run, "read-yaml", {"path": str(config_path(run))})
    return str(stored.get("room_id") or "")


def room_problem(run: Run, room: str) -> str:
    if not room:
        return run.t("server.room_missing")
    if not room.startswith(("!", "#")):
        return run.t("server.room_bad_start", room=room)
    if any(part.isspace() for part in room):
        return run.t("server.room_has_space", room=room)
    localpart, _, domain = room[1:].partition(":")
    if not localpart:
        return run.t("server.room_no_name", room=room)
    if room.startswith("#") and not domain:
        return run.t("server.room_alias_without_server", room=room, server=SERVER_NAME)
    if domain and domain != SERVER_NAME:
        return run.t(
            "server.room_other_server", room=room, domain=domain, server=SERVER_NAME
        )
    if localpart == example_room(run):
        return run.t("server.room_is_example", room=room, example=CONFIG_EXAMPLE)
    return ""


def example_room(run: Run) -> str:
    for line in config_example(run).read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("room_id:"):
            value = line.split(":", 1)[1].strip().strip('"')
            return value.lstrip("!#").partition(":")[0]
    return ""


def room_instruction(run: Run) -> str:
    stored = host_call(run, "read-yaml", {"path": str(config_path(run))})
    who = ", ".join(f"@{agent}:{SERVER_NAME}" for agent in stored.get("agents", []))
    return run.t("server.room_instruction", who=who, server=SERVER_NAME)


@dataclass
class StartStep:
    name: str = "start_stand"
    sleep: Callable[[float], None] = time.sleep
    started: bool = False

    def check(self, run: Run) -> State:
        probe = run.boundaries.probe(f"{BROKER_URL}/status")
        if probe.status is None:
            return State.TODO
        if not self.started and BotAccountStep.name in run.completed:
            run.warn(run.t("server.broker_restart"))
        return State.DONE

    def apply(self, run: Run) -> None:
        self.started = True
        done = run.boundaries.run(self.argv(run), output=logs_path(run))
        if done.returncode != 0:
            raise RuntimeError(start_failure(run, done))
        self.wait_for_broker(run)

    def argv(self, run: Run) -> list[str]:
        if run.boundaries.platform == WINDOWS:
            return [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(run.boundaries.repo / "start.ps1"),
            ]
        return ["sh", str(run.boundaries.repo / "start.sh")]

    def wait_for_broker(self, run: Run) -> None:
        for _ in range(START_TRIES):
            if self.check(run) is State.DONE:
                return
            self.sleep(1)
        raise RuntimeError(
            run.t("server.broker_not_started", url=BROKER_URL, tries=START_TRIES)
        )


def start_failure(run: Run, done) -> str:
    return run.t(
        "server.failure_with_log",
        failure=compose_failure(run, run.t("server.what_start_script"), done),
        log=logs_path(run),
    )


def compose_failure(run: Run, what: str, done) -> str:
    lines = [
        line.strip()
        for line in f"{done.stdout or ''}\n{done.stderr or ''}".splitlines()
        if line.strip()
    ]
    return run.t(
        "server.command_failed",
        what=what,
        code=done.returncode,
        detail=lines[-1] if lines else run.t("server.no_output"),
    )


@dataclass
class Stand:
    containers_gone: bool = False


@dataclass
class StopStandStep:
    name: str = "stop_stand"
    sleep: Callable[[float], None] = time.sleep
    stand: Stand = field(default_factory=Stand)
    tried: bool = False

    def check(self, run: Run) -> State:
        if broker_answers(run):
            return State.TODO
        if not docker_answers(run):
            if self.tried:
                return State.DONE
            run.warn_once("stand-unseen", run.t("server.stand_unseen"))
            return State.TODO
        if containers(run):
            return State.TODO
        self.stand.containers_gone = True
        return State.DONE

    def apply(self, run: Run) -> None:
        self.stop_broker(run)
        self.wait_for_silence(run)
        self.down(run)
        self.tried = True

    def argv(self, run: Run) -> list[str]:
        if run.boundaries.platform == WINDOWS:
            return [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(run.boundaries.repo / "stop.ps1"),
                "-KeepDocker",
            ]
        return ["sh", str(run.boundaries.repo / "stop.sh"), "--keep-docker"]

    def stop_broker(self, run: Run) -> None:
        done = run.boundaries.run(self.argv(run), output=stop_log_path(run))
        if done.returncode != 0:
            raise RuntimeError(
                run.t(
                    "server.failure_with_log",
                    failure=compose_failure(
                        run, run.t("server.what_stop_script"), done
                    ),
                    log=stop_log_path(run),
                )
            )

    def wait_for_silence(self, run: Run) -> None:
        for _ in range(SILENCE_TRIES):
            if not broker_answers(run):
                return
            self.sleep(1)
        script = "stop.ps1" if run.boundaries.platform == WINDOWS else "stop.sh"
        raise RuntimeError(
            run.t(
                "server.broker_not_stopped",
                url=BROKER_URL,
                tries=SILENCE_TRIES,
                script=script,
            )
        )

    def down(self, run: Run) -> None:
        try:
            done = run.boundaries.run(compose_argv(run, "down"))
        except OSError as error:
            run.warn_once("stack-down", run.t("server.docker_unavailable", error=error))
            return
        if done.returncode == 0:
            self.stand.containers_gone = True
            return
        if not docker_answers(run):
            run.warn_once("stand-left-up", run.t("server.stand_left_up"))
            return
        raise RuntimeError(compose_failure(run, "docker compose down", done))


@dataclass(frozen=True)
class VenvRemoveStep:
    name: str = "remove_venv"
    python: str = sys.executable

    def targets(self, run: Run) -> list[PurgeTarget]:
        return [
            PurgeTarget(ROLE, VENV_KIND, id)
            for id in run.ownership_of(ROLE).of_kind(VENV_KIND)
        ]

    def check(self, run: Run) -> State:
        targets = self.targets(run)
        report_kept(run, self.name, unapproved(run, targets))
        return State.TODO if approved(run, targets) else State.DONE

    def apply(self, run: Run) -> None:
        for target in approved(run, self.targets(run)):
            self.drop(run, target.id)
            run.forget(ROLE, VENV_KIND, target.id)
            prune_record_home(run.ownership_of(ROLE).path)

    def drop(self, run: Run, id: str) -> None:
        path = Path(id)
        if not path.exists():
            return
        if self.holding(venv_dir(run)):
            raise NeedsHuman(run.t("server.venv_in_use", python=self.python))
        shutil.rmtree(path)

    def holding(self, directory: Path) -> bool:
        try:
            return Path(self.python).resolve().is_relative_to(directory.resolve())
        except OSError:
            return False


@dataclass(frozen=True)
class MountedStep:
    name: str
    kind: str
    stand: Stand
    delete: Callable[["Run", str], None] = unlink

    def targets(self, run: Run) -> list[PurgeTarget]:
        return [
            PurgeTarget(ROLE, self.kind, id)
            for id in run.ownership_of(ROLE).of_kind(self.kind)
        ]

    def still_mounted(self, run: Run, target: PurgeTarget) -> bool:
        if self.stand.containers_gone:
            return False
        kept = {path.resolve() for path in kept_while_up(run)}
        return Path(target.id).resolve() in kept

    def deletable(self, run: Run) -> list[PurgeTarget]:
        return [
            target
            for target in self.targets(run)
            if not self.still_mounted(run, target)
        ]

    def check(self, run: Run) -> State:
        targets = self.deletable(run)
        for target in self.targets(run):
            if self.still_mounted(run, target):
                run.warn_once(
                    f"mounted:{self.name}:{target.id}",
                    run.t(
                        "server.mounted_kept",
                        step=run.label(self.name),
                        target=target.id,
                    ),
                )
        report_kept(run, self.name, unapproved(run, targets))
        return State.TODO if approved(run, targets) else State.DONE

    def apply(self, run: Run) -> None:
        for target in approved(run, self.deletable(run)):
            self.delete(run, target.id)
            run.forget(ROLE, self.kind, target.id)


@dataclass(frozen=True)
class VolumeRemoveStep:
    name: str = "remove_stand_volumes"

    def targets(self, run: Run) -> list[PurgeTarget]:
        return [
            PurgeTarget(ROLE, VOLUME_KIND, id)
            for id in run.ownership_of(ROLE).of_kind(VOLUME_KIND)
        ]

    def check(self, run: Run) -> State:
        targets = self.targets(run)
        report_kept(run, self.name, unapproved(run, targets))
        return State.TODO if approved(run, targets) else State.DONE

    def apply(self, run: Run) -> None:
        targets = approved(run, self.targets(run))
        if targets and not docker_answers(run):
            raise RuntimeError(kept_volumes(run, targets))
        for target in targets:
            if not volume_exists(run, target.id):
                run.forget(ROLE, VOLUME_KIND, target.id)
                continue
            done = run.boundaries.run(["docker", "volume", "rm", target.id])
            if done.returncode != 0:
                raise RuntimeError(volume_failure(run, target.id, done))
            run.forget(ROLE, VOLUME_KIND, target.id)
            prune_record_home(run.ownership_of(ROLE).path)


def volume_failure(run: Run, name: str, done) -> str:
    return run.t(
        "server.volume_left",
        failure=compose_failure(run, "docker volume rm " + name, done),
    )


def kept_volumes(run: Run, targets: Sequence[PurgeTarget]) -> str:
    return run.t("server.volumes_kept", ids=", ".join(target.id for target in targets))


def found_broker_state(run: Run) -> list[str]:
    return broker_state(run) if owned_toml(run) else []


def broker_state_step() -> FoundStep:
    return FoundStep("remove_broker_state", ROLE, STATE_KIND, found_broker_state)


def remove_steps(
    stand: Stand, sleep: Callable[[float], None], python: str = sys.executable
) -> tuple:
    return (
        StopStandStep(sleep=sleep, stand=stand),
        VenvRemoveStep(python=python),
    )


def purge_steps(stand: Stand) -> tuple:
    return (
        broker_state_step(),
        MountedStep("remove_stand_config", FILE_KIND, stand),
        MountedStep("remove_certificates", CERT_KIND, stand),
        OwnedStep("remove_saved_passwords", ROLE, PASSWORDS_KIND),
        VolumeRemoveStep(),
    )


def server_role(
    python: str = sys.executable, sleep: Callable[[float], None] = time.sleep
) -> Role:
    people = HumanAccountStep()
    stand = Stand()
    return Role(
        name=ROLE,
        record_path=record_path,
        install=steps(python, sleep, people),
        remove=remove_steps(stand, sleep, python),
        purge=purge_steps(stand),
        purge_consequence=server_consequence,
        report=lambda run: report(run, people, stand),
        add_options=add_options,
    )


def server_consequence(targets: Sequence[PurgeTarget], lang: str) -> str:
    kinds = {target.kind for target in targets if target.role == ROLE}
    named = [text(lang, key) for kind, key in KIND_WORDS.items() if kind in kinds]
    parts = (
        [text(lang, "server.consequence_vanish", things=", ".join(named))]
        if named
        else []
    )
    if VOLUME_KIND in kinds:
        parts.append(text(lang, "server.consequence_volumes"))
    else:
        parts.append(text(lang, "server.consequence_room_stays"))
    return "; ".join(parts) + "."


def steps(
    python: str,
    sleep: Callable[[float], None],
    people: HumanAccountStep | None = None,
) -> tuple:
    return (
        ToolStep(
            "find_docker",
            ("docker", "--version"),
            "server.docker_missing_windows",
            "server.docker_missing_linux",
        ),
        ToolStep(
            "check_docker_daemon",
            ("docker", "info"),
            "server.daemon_stopped_windows",
            "server.daemon_stopped_linux",
        ),
        ToolStep(
            "check_compose",
            ("docker", "compose", "version"),
            "server.compose_missing_windows",
            "server.compose_missing_linux",
        ),
        ToolStep(
            "find_mkcert",
            ("mkcert", "-version"),
            "server.mkcert_missing_windows",
            "server.mkcert_missing_linux",
        ),
        ServerNameStep(),
        VenvStep(python=python),
        CertificateStep(),
        EnvFileStep(),
        TomlFileStep(),
        InfrastructureStep(sleep=sleep),
        TrustStep(),
        ConfigStep(),
        people or HumanAccountStep(),
        BotAccountStep(),
        BrokerAddressStep(),
        CloseRegistrationStep(sleep=sleep),
        RoomStep(),
        StartStep(sleep=sleep),
    )


def add_options(options: RoleOptions) -> None:
    options.add("--admin-user", help=options.t("server.help_admin_user"))
    options.add("--room-id", help=options.t("server.help_room_id", server=SERVER_NAME))


def report(run: Run, people: HumanAccountStep, stand: Stand) -> None:
    if run.plan.remove:
        prune_record_home(record_path(run.boundaries))
        for line in removal_lines(run, stand):
            run.say(line)
        return
    run.say(run.t("server.report_broker", url=BROKER_URL))
    run.say(run.t("server.report_matrix", url=server_url()))
    if people.became_admin:
        run.say(run.t("server.report_became_admin"))
    run.say(certificate_note(run))
    run.say(
        run.t(
            "server.report_next",
            script="stop.ps1" if run.boundaries.platform == WINDOWS else "stop.sh",
        )
    )


def removal_lines(run: Run, stand: Stand) -> list[str]:
    kept = kept_items(run)
    return [
        *(
            [run.t("server.left_heading"), *left_lines(kept)]
            if kept
            else [run.t("server.removed")]
        ),
        *stand_lines(run, stand),
        *trust_lines(run),
        hosts_line(run),
        *image_lines(run),
        run.t(
            "server.reinstall_hint",
            entry=INSTALL_ENTRY.get(run.boundaries.platform, "install.sh"),
        ),
    ]


def hosts_line(run: Run) -> str:
    where = (
        r"C:\Windows\System32\drivers\etc\hosts"
        if run.boundaries.platform == WINDOWS
        else "/etc/hosts"
    )
    return run.t("server.hosts_line_kept", server=SERVER_NAME, where=where)


def kept_items(run: Run) -> list[Left]:
    items = [
        *_volumes_left(run),
        *[_recorded_left(run)],
        *[_foreign_left(run)],
        *[_state_left(run)],
        *install_logs(run),
    ]
    return [item for item in items if item is not None]


def _recorded_left(run: Run) -> Left | None:
    ownership = run.ownership_of(ROLE)
    files = tuple(
        id
        for kind in (FILE_KIND, CERT_KIND, PASSWORDS_KIND, VENV_KIND)
        for id in ownership.of_kind(kind)
    )
    if not files:
        return None
    return Left(run.t("server.left_records"), files)


def _volumes_left(run: Run) -> list[Left]:
    if not docker_answers(run):
        return [Left(run.t("server.left_volumes_unreadable"))]
    names = project_volumes(run)
    if not names:
        return []
    ownership = run.ownership_of(ROLE)
    mine = tuple(name for name in names if ownership.owns(VOLUME_KIND, name))
    theirs = tuple(name for name in names if name not in mine)
    return [
        item
        for item in (
            Left(run.t("server.left_volumes_mine"), mine),
            Left(run.t("server.left_volumes_theirs"), theirs),
        )
        if item.files
    ]


def _foreign_left(run: Run) -> Left | None:
    files = foreign_files(run)
    if not files:
        return None
    return Left(run.t("server.left_foreign"), files)


def _state_left(run: Run) -> Left | None:
    files = tuple(broker_state(run))
    if not files:
        return None
    return Left(run.t("server.left_state"), files)


def stand_lines(run: Run, stand: Stand) -> list[str]:
    if stand.containers_gone:
        return [run.t("server.stand_removed")]
    return [run.t("server.stand_remains")]


def trust_lines(run: Run) -> list[str]:
    root = caroot(run)
    if not root:
        return []
    command = (
        "mkcert -uninstall"
        if run.boundaries.platform == WINDOWS
        else run.t("server.untrust_command_linux", caroot=root)
    )
    return [
        run.t("server.mkcert_root_kept", root=root),
        run.t("server.mkcert_root_manual", command=command, root=root),
    ]


def image_lines(run: Run) -> list[str]:
    images = tuple(compose_images(run))
    if not images:
        return []
    return [
        run.t("server.images_kept", images=", ".join(images)),
        run.t(
            "server.images_remove",
            commands=", ".join(f"docker image rm {image}" for image in images),
        ),
    ]


def certificate_note(run: Run) -> str:
    expires = not_after(cert_path(run))
    sentences = (
        [run.t("server.certificate_expires", expires=expires)] if expires else []
    )
    sentences.append(
        run.t(
            "server.certificate_renew",
            cert_file=cert_path(run),
            key_file=cert_key_path(run),
            server=SERVER_NAME,
            compose=compose_file(run),
        )
    )
    return " ".join(sentences)


def not_after(path: Path) -> str:
    try:
        der = base64.b64decode(_pem_body(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return ""
    certificate = _der_take(der)
    if certificate is None:
        return ""
    tbs = next((body for tag, body in _der_walk(certificate) if tag == SEQUENCE), None)
    if tbs is None:
        return ""
    fields = _der_walk(tbs)
    if fields and fields[0][0] == CONTEXT_0:
        fields = fields[1:]
    validity = fields[3][1] if len(fields) > 3 else b""
    times = [
        (body.decode("ascii"), tag) for tag, body in _der_walk(validity) if tag in TIMES
    ]
    return _readable(*times[1]) if len(times) == 2 else ""


def _der_take(der: bytes) -> bytes | None:
    parts = _der_walk(der)
    return parts[0][1] if len(parts) == 1 and parts[0][0] == SEQUENCE else None


def _der_walk(der: bytes) -> list[tuple[int, bytes]]:
    fields: list[tuple[int, bytes]] = []
    number = 0
    while number < len(der):
        tag = der[number]
        sized = _der_size(der, number + 1)
        if sized is None:
            return fields
        size, used = sized
        start = number + used + 1
        fields.append((tag, der[start : start + size]))
        number = start + size
    return fields


def _der_size(der: bytes, number: int) -> tuple[int, int] | None:
    if number >= len(der):
        return None
    first = der[number]
    if first < 0x80:
        return first, 1
    count = first & 0x7F
    raw = der[number + 1 : number + 1 + count]
    if len(raw) != count:
        return None
    return int.from_bytes(raw, "big"), 1 + count


def _pem_body(text: str) -> str:
    return "".join(
        line for line in text.splitlines() if line and not line.startswith("-----")
    )


def _readable(stamp: str, tag: int) -> str:
    digits = stamp.rstrip("Z")
    if tag == UTC_TIME and len(digits) == 12:
        year, month, day = f"20{digits[0:2]}", digits[2:4], digits[4:6]
    elif tag == GENERALIZED_TIME and len(digits) == 14:
        year, month, day = digits[0:4], digits[4:6], digits[6:8]
    else:
        return ""
    if not (month.isdigit() and day.isdigit()):
        return ""
    if not ("01" <= month <= "12" and "01" <= day <= "31"):
        return ""
    return f"{day}.{month}.{year}"
