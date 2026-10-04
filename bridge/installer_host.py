from __future__ import annotations

import importlib.util
import json
import os
import re
import secrets
import sys
from pathlib import Path

LINE = re.compile(r"^(\s*)([A-Za-z0-9_.-]+):\s*(.*)$")
PLACEHOLDER = "PASTE_"
READABLE = (
    "homeserver_url",
    "verify_ssl",
    "room_id",
    "sessionchat_port",
    "max_depth",
)
LIBRARIES = ("yaml", "aiohttp", "nio", "requests")
DEVICE = "agentschat-installer"


class Failed(Exception):
    def __init__(
        self,
        error: str,
        errcode: str = "",
        status: int = 0,
        file: str = "",
        line: int = 0,
    ):
        super().__init__(error)
        self.error = error
        self.errcode = errcode
        self.status = status
        self.file = file
        self.line = line

    def payload(self) -> dict:
        return {
            "error": self.error,
            "errcode": self.errcode,
            "status": self.status,
            "file": self.file,
            "line": self.line,
        }


def yaml():
    try:
        import yaml as module
    except ImportError:
        raise Failed("imports", errcode="yaml") from None
    return module


def requests():
    try:
        import requests as module
    except ImportError:
        raise Failed("imports", errcode="requests") from None
    return module


def send(method: str, url: str, **keywords):
    try:
        with session() as http:
            return getattr(http, method)(url, **keywords)
    except (requests().RequestException, OSError) as problem:
        raise Failed(method, errcode=type(problem).__name__) from None


def session():
    http = requests().Session()
    http.trust_env = False
    return http


def scalar(text: str) -> str:
    return text.strip().strip('"').strip("'")


def layout(text: str) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    stack: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines()):
        match = (
            LINE.match(line)
            if line.strip() and not line.lstrip().startswith("#")
            else None
        )
        if not match:
            continue
        indent = len(match.group(1).replace("\t", "    "))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, match.group(2)))
        found.append((number, ".".join(part for _, part in stack), match.group(3)))
    return found


def read_yaml(path: str, keys: tuple[str, ...]) -> dict:
    stored = _load(path)
    answer = {key: stored[key] for key in keys if key in stored}
    if isinstance(stored.get("agents"), dict):
        answer["agents"] = sorted(stored["agents"])
    return answer


def _load(path: str) -> dict:
    module = yaml()
    try:
        return module.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except module.YAMLError as problem:
        raise Failed("yaml", file=path, line=problem.problem_mark.line + 1) from None
    except OSError as problem:
        raise Failed("yaml", file=path, errcode=type(problem).__name__) from None


def _value_at(lines: list[str], path: str) -> str | None:
    for _, found, value in layout("\n".join(lines)):
        if found == path:
            return scalar(value)
    return None


def write_yaml(path: str, example: str, values: dict, owned: bool) -> dict:
    target = Path(path)
    if not target.is_file():
        return {"written": [], "conflicts": sorted(values)}
    text = target.read_text(encoding="utf-8")
    sample = Path(example).read_text(encoding="utf-8").splitlines() if example else []
    lines = text.splitlines()
    written: list[str] = []
    conflicts: list[str] = []
    for key, wanted in values.items():
        place = [
            (number, value) for number, found, value in layout(text) if found == key
        ]
        if not place:
            at = _insert_point(lines, key, owned)
            if at is None:
                conflicts.append(key)
                continue
            name = key.rsplit(".", 1)[-1]
            lines.insert(at, f'{_indent(lines, key)}{name}: "{wanted}"')
            written.append(key)
            continue
        number, value = place[0]
        here, model = scalar(value), _value_at(sample, key)
        if here == wanted:
            continue
        if _placeholder(here, model):
            lines[number] = re.sub(
                r"(\s*:[ \t]*).*$",
                lambda found: f'{found.group(1)}"{wanted}"',
                lines[number],
            )
            written.append(key)
        else:
            conflicts.append(key)
    if not written:
        return {"written": [], "conflicts": conflicts}
    body = "\n".join(lines) + "\n"
    if not _readable_yaml(body):
        return {"written": [], "conflicts": sorted(values)}
    target.write_text(body, encoding="utf-8")
    return {"written": written, "conflicts": conflicts}


def _placeholder(here: str, model: str | None) -> bool:
    return (model is not None and here == model) or here.startswith(PLACEHOLDER)


def _insert_point(lines: list[str], key: str, owned: bool) -> int | None:
    parent = key.rsplit(".", 1)[0] if "." in key else ""
    if parent:
        return _block_end(lines, parent)
    return len(lines) if owned else None


def _block_end(lines: list[str], parent: str) -> int | None:
    fields = layout("\n".join(lines))
    for index, (number, found, _) in enumerate(fields):
        if found != parent:
            continue
        last = number
        for later, path, _ in fields[index + 1 :]:
            if later != last + 1 or not path.startswith(f"{parent}."):
                break
            last = later
        return last + 1
    return None


def _indent(lines: list[str], key: str) -> str:
    parent = key.rsplit(".", 1)[0] if "." in key else ""
    fields = layout("\n".join(lines))
    for index, (number, found, _) in enumerate(fields):
        if found != parent:
            continue
        for later, path, _ in fields[index + 1 :]:
            if not path.startswith(f"{parent}."):
                break
            return lines[later][: len(lines[later]) - len(lines[later].lstrip())]
        return " " * (len(lines[number]) - len(lines[number].lstrip()) + 2)
    return ""


def _readable_yaml(text: str) -> bool:
    module = yaml()
    try:
        module.safe_load(text)
    except module.YAMLError:
        return False
    return True


def whoami(url: str, config: str, example: str, ca_file: str) -> dict:
    stored = _load(config)
    sample = _load(example) if example else {}
    status: dict[str, str] = {}
    for agent, entry in sorted((stored.get("agents") or {}).items()):
        entry = entry or {}
        token = str(entry.get("access_token") or "")
        if not token:
            status[agent] = "absent"
            continue
        if token == str(
            ((sample.get("agents") or {}).get(agent) or {}).get("access_token") or ""
        ):
            status[agent] = "placeholder"
            continue
        answer = send(
            "get",
            f"{_base(url)}/_matrix/client/v3/account/whoami",
            headers={"authorization": f"Bearer {token}"},
            verify=_verify(ca_file),
            timeout=30,
        )
        status[agent] = (
            "valid"
            if answer.status_code == 200
            and _body(answer).get("user_id") == entry.get("user_id")
            else "invalid"
        )
    return status


def available(url: str, username: str, ca_file: str) -> dict:
    answer = send(
        "get",
        f"{_base(url)}/_matrix/client/v3/register/available",
        params={"username": username},
        verify=_verify(ca_file),
        timeout=30,
    )
    body = _body(answer)
    if answer.status_code == 200 and body.get("available") is True:
        return {"available": True}
    if answer.status_code == 400 and body.get("errcode") == "M_USER_IN_USE":
        return {"available": False}
    raise Failed(
        "available", errcode=str(body.get("errcode") or ""), status=answer.status_code
    )


def login(url: str, username: str, password: str, ca_file: str) -> dict:
    answer = send(
        "post",
        f"{_base(url)}/_matrix/client/v3/login",
        json={
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": username},
            "password": password,
            "initial_device_display_name": DEVICE,
        },
        verify=_verify(ca_file),
        timeout=30,
    )
    return _credentials(answer, "login")


def register(url: str, username: str, password: str, token: str, ca_file: str) -> dict:
    endpoint = f"{_base(url)}/_matrix/client/v3/register"
    body = {
        "username": username,
        "password": password,
        "initial_device_display_name": DEVICE,
    }
    first = send("post", endpoint, json=body, verify=_verify(ca_file), timeout=30)
    if first.status_code == 200:
        return _credentials(first, "register")
    session = _body(first).get("session")
    if first.status_code != 401 or not session:
        raise _refusal(first, "register")
    second = send(
        "post",
        endpoint,
        json={
            **body,
            "auth": {
                "type": "m.login.registration_token",
                "token": token,
                "session": session,
            },
        },
        verify=_verify(ca_file),
        timeout=30,
    )
    if second.status_code != 200:
        raise _refusal(second, "register")
    return _credentials(second, "register")


def probe_closed(url: str, ca_file: str) -> dict:
    endpoint = f"{_base(url)}/_matrix/client/v3/register"
    body = {
        "username": f"quoroom-probe-{os.getpid()}",
        "password": secrets.token_urlsafe(16),
        "initial_device_display_name": "quoroom-probe",
    }
    first = send("post", endpoint, json=body, verify=_verify(ca_file), timeout=30)
    if first.status_code != 401 or not _body(first).get("session"):
        return {
            "status": first.status_code,
            "errcode": str(_body(first).get("errcode") or ""),
        }
    second = send(
        "post",
        endpoint,
        json={
            **body,
            "auth": {
                "type": "m.login.registration_token",
                "token": "quoroom-probe-not-a-token",
                "session": _body(first)["session"],
            },
        },
        verify=_verify(ca_file),
        timeout=30,
    )
    return {
        "status": second.status_code,
        "errcode": str(_body(second).get("errcode") or ""),
    }


def libraries() -> dict:
    missing = [name for name in LIBRARIES if importlib.util.find_spec(name) is None]
    if missing:
        raise Failed("imports", errcode=missing[0])
    return {"ok": True}


def _credentials(answer, command: str) -> dict:
    body = _body(answer)
    if answer.status_code != 200 or not body.get("access_token"):
        raise _refusal(answer, command)
    return {
        "user_id": str(body.get("user_id") or ""),
        "access_token": str(body["access_token"]),
        "device_id": str(body.get("device_id") or ""),
    }


def _refusal(answer, command: str) -> Failed:
    return Failed(
        command,
        errcode=str(_body(answer).get("errcode") or ""),
        status=answer.status_code,
    )


def _body(answer) -> dict:
    try:
        return answer.json()
    except ValueError:
        return {}


def _base(url: str) -> str:
    return url.rstrip("/")


def _verify(ca_file: str):
    return ca_file or True


COMMANDS = {
    "imports": lambda payload: libraries(),
    "read-yaml": lambda payload: read_yaml(
        payload["path"], tuple(payload.get("keys", READABLE))
    ),
    "write-yaml": lambda payload: write_yaml(
        payload["path"],
        payload.get("example", ""),
        payload.get("values", {}),
        bool(payload.get("owned")),
    ),
    "available": lambda payload: available(
        payload["url"], payload["username"], payload.get("ca_file", "")
    ),
    "probe-closed": lambda payload: probe_closed(
        payload["url"], payload.get("ca_file", "")
    ),
    "whoami": lambda payload: whoami(
        payload["url"],
        payload["config"],
        payload.get("example", ""),
        payload.get("ca_file", ""),
    ),
    "login": lambda payload: login(
        payload["url"],
        payload["username"],
        payload["password"],
        payload.get("ca_file", ""),
    ),
    "register": lambda payload: register(
        payload["url"],
        payload["username"],
        payload["password"],
        payload["token"],
        payload.get("ca_file", ""),
    ),
}


def main(argv: list[str]) -> int:
    command = argv[0] if argv else ""
    handler = COMMANDS.get(command)
    if handler is None:
        print(json.dumps({"error": "unknown", "errcode": command}, ensure_ascii=True))
        return 2
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        answer = handler(payload)
    except Failed as failure:
        print(json.dumps(failure.payload(), ensure_ascii=True))
        return 1
    except (KeyError, ValueError, TypeError) as broken:
        print(
            json.dumps(
                {"error": command, "errcode": type(broken).__name__, "status": 0},
                ensure_ascii=True,
            )
        )
        return 1
    print(json.dumps(answer, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
