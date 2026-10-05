import json

PREFIX = "AGENTSCHAT-RESULT"


def line(command: str, ok: bool, **fields: object) -> str:
    body = {"command": command, "ok": ok, **fields}
    return f"{PREFIX} {json.dumps(body, separators=(',', ':'))}"
