from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import secrets
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .boundaries import Boundaries, WINDOWS
from .roles import Role, RoleOptions
from .steps import NeedsHuman, Run, State

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
ACCOUNTS_FILE = "server-accounts.json"
CONFIG_NAME = "config.yaml"
CONFIG_EXAMPLE = "config.example.yaml"
ENV_FILE = ".env"
ENV_EXAMPLE = ".env.example"
TOML_NAME = "continuwuity.toml"
TOML_EXAMPLE = "continuwuity.toml.example"
CERT_NAME = "agentschat.local"
CERT_KEY = "agentschat.local-key"
ISSUED = re.compile(r"using the registration token ([A-Za-z0-9]+)")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
SEQUENCE = 0x30
CONTEXT_0 = 0xA0
UTC_TIME = 0x17
GENERALIZED_TIME = 0x18
TIMES = (UTC_TIME, GENERALIZED_TIME)
TOML_KEY = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
READY_TRIES = 30
READY_DELAY = 2.0
START_TRIES = 15
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
    def __init__(self, command: str, answer: dict) -> None:
        super().__init__(host_failure(command, answer))
        self.answer = answer


def host_call(run: Run, command: str, payload: dict) -> dict:
    done = run.boundaries.run(
        [str(venv_python(run)), str(host_script(run)), command],
        stdin=json.dumps(payload, ensure_ascii=True),
    )
    answer = _json(done.stdout)
    if done.returncode != 0 or answer.get("error"):
        raise HostRefused(command, answer)
    return answer


def _json(text: str | None) -> dict:
    try:
        answer = json.loads(text or "{}")
    except ValueError:
        return {}
    return answer if isinstance(answer, dict) else {}


def host_failure(command: str, answer: dict) -> str:
    parts = [f"bridge/.venv не справилась с {command}"]
    for key, label in (("errcode", "код"), ("status", "HTTP"), ("file", "файл")):
        if answer.get(key):
            parts.append(f"{label}={answer[key]}")
    if answer.get("line"):
        parts.append(f"строка={answer['line']}")
    return ": ".join(parts) + "."


def text_of(run: Run, argv: Sequence[str]) -> str:
    try:
        done = run.boundaries.run([str(part) for part in argv])
    except OSError:
        return ""
    return (done.stdout or "") if done.returncode == 0 else ""


def lines_of(run: Run, argv: Sequence[str]) -> list[str]:
    return [line for line in text_of(run, argv).splitlines() if line.strip()]


def ca_bundle(run: Run) -> str:
    root = text_of(run, ["mkcert", "-CAROOT"]).strip()
    bundle = Path(root) / "rootCA.pem" if root else Path("rootCA.pem")
    if not bundle.is_file():
        raise RuntimeError(
            f"нет корня mkcert: {bundle}. Он появляется при первом выпуске сертификата."
        )
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
    windows: str
    linux: str

    def check(self, run: Run) -> State:
        try:
            done = run.boundaries.run([*self.argv])
        except OSError:
            return State.TODO
        return State.DONE if done.returncode == 0 else State.TODO

    def apply(self, run: Run) -> None:
        raise NeedsHuman(
            self.windows if run.boundaries.platform == WINDOWS else self.linux
        )


@dataclass(frozen=True)
class ServerNameStep:
    name: str = "Проверить имя сервера"

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
    where = (
        r"C:\Windows\System32\drivers\etc\hosts (от имени администратора)"
        if run.boundaries.platform == WINDOWS
        else "/etc/hosts (от root)"
    )
    return (
        f"Добавьте строку «127.0.0.1 {SERVER_NAME}» в {where}: имя {SERVER_NAME} "
        "должно резолвиться в адрес петли, иначе стенд на хосте ответит вместо стека."
    )


@dataclass
class VenvStep:
    name: str = "Создать bridge/.venv"
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
            raise RuntimeError(venv_failure(created))
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
            raise RuntimeError(venv_failure(pip))
        host_call(run, "imports", {})


def venv_failure(result) -> str:
    tail = [
        line
        for line in (result.stderr or result.stdout or "").splitlines()
        if line.strip()
    ]
    return f"bridge/.venv не собралась: {tail[-1] if tail else 'без вывода'}"


@dataclass(frozen=True)
class CertificateStep:
    name: str = "Выпустить сертификат"

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
            raise RuntimeError(mkcert_failure(done))
        for path in (cert_path(run), cert_key_path(run)):
            run.record(ROLE, CERT_KIND, str(path))


def mkcert_failure(result) -> str:
    detail = (result.stderr or result.stdout or "").strip()
    return f"mkcert не выпустил сертификат: {detail}"


@dataclass(frozen=True)
class EnvFileStep:
    name: str = f"Создать docker/{ENV_FILE}"

    def check(self, run: Run) -> State:
        problem = env_problem(run)
        if problem:
            raise RuntimeError(problem)
        return State.DONE if env_path(run).is_file() else State.TODO

    def apply(self, run: Run) -> None:
        if env_path(run).is_file():
            raise RuntimeError(f"{env_path(run)} уже есть.")
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
                return (
                    f"{path}: строка {number} задаёт SERVER_NAME={given}, а стек "
                    f"настроен на {SERVER_NAME}. Правьте вручную: имя homeserver "
                    "зашито в Caddyfile и в конфиг Element."
                )
            return ""
    return f"{path}: нет строки SERVER_NAME, добавьте её вручную."


@dataclass(frozen=True)
class TomlFileStep:
    name: str = f"Создать docker/continuwuity/{TOML_NAME}"

    def check(self, run: Run) -> State:
        problem = toml_problem(run)
        if problem:
            raise RuntimeError(problem)
        return State.DONE if toml_path(run).is_file() else State.TODO

    def apply(self, run: Run) -> None:
        if toml_path(run).is_file():
            raise RuntimeError(f"{toml_path(run)} уже есть.")
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
            return f"{path}: нет строки {key}, добавьте её вручную."
        if not value:
            return f"{path}: строка {number} ({key}) пустая, заполните вручную."
    given, _ = toml_value(lines, "registration_token")
    sample, _ = toml_value(
        toml_example(run).read_text(encoding="utf-8").splitlines(), "registration_token"
    )
    if given == sample:
        return (
            f"{path}: registration_token всё ещё пример из {TOML_EXAMPLE}, "
            "замените его своим."
        )
    return ""


def served_status(status: int | None) -> bool:
    return status is not None and status not in GATEWAY_STATUSES


@dataclass
class InfrastructureStep:
    name: str = "Поднять инфраструктуру"
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
                raise RuntimeError(compose_failure("docker compose up -d", up))
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
            f"{SERVER_NAME} не ответил за {READY_TRIES * READY_DELAY:.0f}с: "
            f"{probe.error or probe.status}. Смотрите "
            f'docker compose -f "{compose_file(run)}" logs continuwuity.'
        )

    def project(self, run: Run) -> str:
        return str(
            _json(text_of(run, compose_argv(run, "config", "--format", "json"))).get(
                "name"
            )
            or ""
        )

    def volumes(self, run: Run) -> set[str]:
        argv = ["docker", "volume", "ls", "--format", "{{.Name}}"]
        if self.project(run):
            argv += [
                "--filter",
                f"label=com.docker.compose.project={self.project(run)}",
            ]
        return set(lines_of(run, argv))

    def record_new(self, run: Run, before: set[str]) -> None:
        declared = set(lines_of(run, compose_argv(run, "config", "--volumes")))
        for name in sorted(self.volumes(run) - before):
            if any(name.endswith(key) for key in declared):
                run.record(ROLE, VOLUME_KIND, name)


@dataclass(frozen=True)
class TrustStep:
    name: str = "Проверить доверие к сертификату"

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
        command = f'CAROOT="{caroot(run)}" mkcert -install (от root)'
    tail = f" Сервер ответил: {reason}." if reason else ""
    return (
        f"Браузер и брокер должны доверять сертификату {SERVER_NAME}. Выполните "
        f"от администратора: {command}.{tail} После этого повторите ту же команду."
    )


def caroot(run: Run) -> str:
    return text_of(run, ["mkcert", "-CAROOT"]).strip()


@dataclass(frozen=True)
class ConfigStep:
    name: str = f"Создать bridge/{CONFIG_NAME}"

    def check(self, run: Run) -> State:
        if not config_path(run).is_file():
            return State.TODO
        host_call(run, "read-yaml", {"path": str(config_path(run))})
        return State.DONE

    def apply(self, run: Run) -> None:
        if config_path(run).is_file():
            return
        config_path(run).write_text(
            config_example(run).read_text(encoding="utf-8"), encoding="utf-8"
        )
        run.record(ROLE, FILE_KIND, str(config_path(run)))


@dataclass
class HumanAccountStep:
    name: str = "Завести аккаунт человека"
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
            raise NeedsHuman(
                "Нужен локальный аккаунт человека: под ним он входит в Element, и "
                "первый аккаунт на сервере становится администратором. Повторите с "
                "--admin-user <имя>."
            )
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
    run.say("Имя локального аккаунта человека, под которым он войдёт в Element: ")
    return run.boundaries.stdin.readline().strip()


def admin_password(run: Run) -> str:
    from_env = run.boundaries.env.get(PASSWORD_VARIABLE, "")
    if from_env:
        return run.secrets.register(from_env)
    if not run.boundaries.stdin.isatty():
        raise NeedsHuman(
            f"Нужен пароль аккаунта человека. Задайте переменную "
            f"{PASSWORD_VARIABLE} или запустите установщик в терминале, где он "
            "спросит пароль без эха."
        )
    return run.secrets.register(run.boundaries.secret("Пароль аккаунта человека: "))


def manual_account(run: Run, username: str) -> str:
    return (
        f"Аккаунта {username} на сервере нет, а {TOML_NAME} создан не этим "
        "установщиком, поэтому регистрировать здесь установщик не будет. "
        f"Создайте его через {run.boundaries.repo / 'bridge' / 'register_account.py'} "
        "и повторите, либо отдайте установщику свой файл."
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
        return (
            "Сервер не принимает регистрации (HTTP 403): регистрация закрыта. "
            f"Поставьте allow_registration = true в {toml_path(run)} и выполните "
            f'docker compose -f "{compose_file(run)}" restart continuwuity.'
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
            "Сервер не напечатал свой токен регистрации. Возьмите его сами командой "
            f'docker compose -f "{compose_file(run)}" logs continuwuity и '
            "зарегистрируйте аккаунт через register_account.py."
        )
    return found[-1]


@dataclass
class BotAccountStep:
    name: str = "Завести аккаунты ботов"

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
                raise NeedsHuman(
                    f"Аккаунт бота {agent} на сервере уже есть, а пароль от него "
                    "установщику неизвестен: сбросьте его через Element или удалите "
                    "аккаунт, затем повторите."
                )
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
                    f"Сохранённый пароль для {agent} не подошёл к аккаунту на "
                    f"сервере: {refused}. Сбросьте пароль через Element или "
                    "удалите аккаунт, затем повторите."
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
    return (
        f"{TOML_NAME} создан не этим установщиком, поэтому заводить ботов здесь он "
        f"не будет. Впишите user_id, access_token и device_id каждого бота в "
        f"{config_path(run)} сами - значения показывает register_account.py."
    )


@dataclass(frozen=True)
class BrokerAddressStep:
    name: str = "Проверить адрес брокера"

    def check(self, run: Run) -> State:
        problem = broker_problem(run)
        if problem:
            raise RuntimeError(problem)
        return State.DONE

    def apply(self, run: Run) -> None:
        raise RuntimeError(broker_problem(run) or f"{config_path(run)} в порядке.")


def broker_problem(run: Run) -> str:
    stored = host_call(run, "read-yaml", {"path": str(config_path(run))})
    port = int(stored.get("sessionchat_port", BROKER_PORT))
    if port != BROKER_PORT:
        return (
            f"{config_path(run)} задаёт sessionchat_port={port}, а start.sh и "
            f"start.ps1 поднимают брокера на {BROKER_PORT}, и скрипты менять нельзя. "
            f"Поставьте в конфигурации sessionchat_port: {BROKER_PORT}."
        )
    url = str(stored.get("homeserver_url") or "")
    if url and SERVER_NAME not in url:
        return (
            f"{config_path(run)} задаёт homeserver_url={url}, а стек поднят на "
            f"{server_url()}. Поставьте homeserver_url: {server_url()}."
        )
    return ""


@dataclass
class CloseRegistrationStep:
    name: str = "Закрыть регистрацию"
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
    return (
        "Регистрация закрыта в файле, но сервер этого не подтвердил: пробная "
        "регистрация с заведомо неверным токеном не получила отказ 403. "
        "Проверьте, что контейнер перезапустился с новым файлом, командой "
        f'docker compose -f "{compose_file(run)}" restart continuwuity.'
    )


def manual_close(run: Run) -> str:
    closed = toml_value(toml_lines(run), "allow_registration")[0] == "false"
    head = (
        f"в {toml_path(run)} уже стоит allow_registration = false, но сервер "
        "регистрацию не закрывает"
        if closed
        else f"{TOML_NAME} создан не этим установщиком, поэтому закрывать "
        "регистрацию здесь он не будет"
    )
    todo = (
        f"перезапустите его командой docker compose -f "
        f'"{compose_file(run)}" restart continuwuity.'
        if closed
        else f"Поставьте allow_registration = false в {toml_path(run)} и выполните "
        f'docker compose -f "{compose_file(run)}" restart continuwuity.'
    )
    return f"{head}: {todo}"


@dataclass(frozen=True)
class RoomStep:
    name: str = "Записать комнату"

    def check(self, run: Run) -> State:
        asked = str(run.plan.answers.get(ROLE, {}).get(ROOM_DEST) or "")
        stored = room_id(run)
        if asked and stored and asked != stored and not room_problem(run, stored):
            run.warn_once(
                f"room:{stored}",
                f"В {CONFIG_NAME} уже стоит комната {stored}, а в этом запуске "
                f"передана {asked}. Оставлена первая: записанное значение "
                f"установщик сам не затирает. Поменяйте room_id в "
                f"{config_path(run)} и повторите.",
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
            f"{config_path(run)}: записать {', '.join(conflicts)} не вышло. Либо "
            "там уже другое значение, либо файл написан в форме, которую "
            "установщик не правит (строка в фигурных скобках, ключ в кавычках). "
            "Впишите значения сами и повторите."
        )


def room_id(run: Run) -> str:
    stored = host_call(run, "read-yaml", {"path": str(config_path(run))})
    return str(stored.get("room_id") or "")


def room_problem(run: Run, room: str) -> str:
    if not room:
        return "Не указан идентификатор комнаты."
    if not room.startswith(("!", "#")):
        return f"Идентификатор комнаты должен начинаться с ! или #, а не с {room!r}."
    if any(part.isspace() for part in room):
        return f"В идентификаторе комнаты не должно быть пробела: {room!r}."
    localpart, _, domain = room[1:].partition(":")
    if not localpart:
        return f"В идентификаторе комнаты {room!r} нет имени после ! или #."
    if room.startswith("#") and not domain:
        return (
            f"Псевдоним комнаты {room!r} должен называть сервер: "
            f"псевдоним всегда пишут как #имя:{SERVER_NAME}."
        )
    if domain and domain != SERVER_NAME:
        return (
            f"Идентификатор комнаты {room!r} указывает на сервер {domain!r}, "
            f"а стенд работает на {SERVER_NAME}."
        )
    if localpart == example_room(run):
        return f"Идентификатор комнаты всё ещё пример из {CONFIG_EXAMPLE}: {room!r}."
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
    return (
        "Создайте комнату в Element под своим аккаунтом и пригласите в неё "
        f"{who}. Приглашение брокер примет сам. Затем Room settings -> Advanced -> "
        "Internal room ID, и передайте значение установщику через --room-id как "
        "есть: оно начинается с !, а домен, если он есть, должен быть "
        f"{SERVER_NAME}."
    )


@dataclass
class StartStep:
    name: str = "Запустить стенд"
    sleep: Callable[[float], None] = time.sleep
    started: bool = False

    def check(self, run: Run) -> State:
        probe = run.boundaries.probe(f"{BROKER_URL}/status")
        if probe.status is None:
            return State.TODO
        if not self.started and BotAccountStep.name in run.completed:
            run.warn(
                "Брокер уже отвечает, а токены ботов записал этот запуск: "
                "перезапустите стенд вручную (stop и start), чтобы он взял новые."
            )
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
            f"Брокер не ответил на {BROKER_URL}/status за {START_TRIES}с. Смотрите "
            "bridge/broker.log и перезапустите стенд."
        )


def start_failure(run: Run, done) -> str:
    return (
        f"{compose_failure('стартовый скрипт', done)}. Полный вывод: {logs_path(run)}"
    )


def compose_failure(what: str, done) -> str:
    lines = [
        line.strip()
        for line in f"{done.stdout or ''}\n{done.stderr or ''}".splitlines()
        if line.strip()
    ]
    return f"{what} закончился с кодом {done.returncode}: {lines[-1] if lines else 'без вывода'}"


def server_role(
    python: str = sys.executable, sleep: Callable[[float], None] = time.sleep
) -> Role:
    people = HumanAccountStep()
    return Role(
        name=ROLE,
        record_path=record_path,
        install=steps(python, sleep, people),
        purge_consequence=(
            "тома compose с данными комнаты исчезнут: переписка будет удалена "
            "безвозвратно."
        ),
        report=lambda run: report(run, people),
        add_options=add_options,
    )


def steps(
    python: str,
    sleep: Callable[[float], None],
    people: HumanAccountStep | None = None,
) -> tuple:
    return (
        ToolStep(
            "Найти Docker",
            ("docker", "--version"),
            "Установите Docker Desktop: winget install Docker.DockerDesktop, "
            "запустите его и повторите.",
            "Установите Docker: apt install docker.io, запустите dockerd и повторите.",
        ),
        ToolStep(
            "Проверить Docker-демен",
            ("docker", "info"),
            "Запустите Docker Desktop и повторите.",
            "Запустите dockerd. Если вы не в группе docker, выполните "
            "usermod -aG docker $USER, перезайдите и повторите.",
        ),
        ToolStep(
            "Проверить Compose v2",
            ("docker", "compose", "version"),
            "Docker Desktop несёт compose v2; обновите Docker Desktop.",
            "Установите плагин: apt install docker-compose-v2.",
        ),
        ToolStep(
            "Найти mkcert",
            ("mkcert", "-version"),
            "Установите mkcert: winget install FiloSottile.mkcert.",
            "Установите mkcert: apt install mkcert libnss3-tools "
            "(проект: github.com/FiloSottile/mkcert).",
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
    options.add("--admin-user", help="локальный аккаунт человека в Element")
    options.add(
        "--room-id", help="идентификатор комнаты, например !AbCdEf:agentschat.local"
    )


def report(run: Run, people: HumanAccountStep) -> None:
    if run.plan.remove:
        raise RuntimeError(
            "Удаление роли сервера ещё не реализовано: оно описано в карточке "
            "local-installers-07 и появится отдельным изменением."
        )
    run.say(f"Брокер для участников: {BROKER_URL}")
    run.say(f"Сервер Matrix и Element Web: {server_url()}")
    if people.became_admin:
        run.say(
            "Первый аккаунт стал администратором сервера и получил приглашение "
            "в административную комнату."
        )
    run.say(certificate_note(run))
    run.say(
        "Дальше в каждой сессии CLI вызвать /chatlogin. Остановить всё: "
        + ("stop.ps1" if run.boundaries.platform == WINDOWS else "stop.sh")
    )


def certificate_note(run: Run) -> str:
    expires = not_after(cert_path(run))
    when = f"Сертификат истекает {expires}. " if expires else ""
    return (
        f"{when}Обновить его: mkcert -cert-file {cert_path(run)} -key-file "
        f"{cert_key_path(run)} {SERVER_NAME}, затем docker compose -f "
        f'"{compose_file(run)}" restart caddy.'
    )


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
