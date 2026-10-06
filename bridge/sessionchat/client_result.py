import json

PREFIX = "AGENTSCHAT-RESULT"
MARK = f"{PREFIX} "


def line(command: str, ok: bool, **fields: object) -> str:
    body = {"command": command, "ok": ok, **fields}
    return f"{PREFIX} {json.dumps(body, separators=(',', ':'))}"


def read(output: str) -> dict | None:
    for text in reversed(output.splitlines()):
        if not text.startswith(MARK):
            continue
        try:
            body = json.loads(text[len(MARK) :])
        except ValueError:
            return None
        return body if isinstance(body, dict) else None
    return None
