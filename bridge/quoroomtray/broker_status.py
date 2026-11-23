import json

from .observation import SessionLine


def is_session_entry(entry: object) -> bool:
    return isinstance(entry, dict) and all(
        isinstance(entry.get(field), str) for field in ("agent", "state", "line")
    )


def parse_sessions(body: bytes) -> tuple[SessionLine, ...] | None:
    try:
        document = json.loads(body)
    except ValueError:
        return None
    if not isinstance(document, dict) or not isinstance(document.get("sessions"), list):
        return None
    return tuple(
        SessionLine(entry["agent"], entry["state"], entry["line"])
        for entry in document["sessions"]
        if is_session_entry(entry)
    )
