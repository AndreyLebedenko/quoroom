import hashlib
import json
import re
from dataclasses import asdict, dataclass


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", value):
        raise ValueError(
            "Invalid identifier: use 1-80 letters, digits, underscores or hyphens"
        )
    return value


def key(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:24]


@dataclass(frozen=True)
class Outcome:
    action: str
    summary: str
    details: str
    to: tuple[str, ...]

    def encode(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def parse_outcome(text: str, agents: set[str]) -> Outcome:
    data: object = json.loads(text)
    if not isinstance(data, dict) or set(data) != {
        "action",
        "summary",
        "details",
        "to",
    }:
        raise ValueError("Expected action, summary, details and to")
    action, summary, details, recipients = (
        data[k] for k in ("action", "summary", "details", "to")
    )
    if not isinstance(action, str) or action not in {
        "reply",
        "request",
        "revise",
        "escalate",
        "veto",
        "ready",
    }:
        raise ValueError("Unknown action")
    if not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 600:
        raise ValueError("Summary must contain 1-600 characters")
    if not isinstance(details, str) or not 1 <= len(details.strip()) <= 100000:
        raise ValueError("Details must contain 1-100000 characters")
    if not isinstance(recipients, list) or any(
        not isinstance(a, str) or a not in agents for a in recipients
    ):
        raise ValueError("Unknown recipient")
    if len(set(recipients)) != len(recipients):
        raise ValueError("Duplicate recipients")
    if bool(recipients) != (action in {"request", "revise"}):
        raise ValueError("Only request/revise must have recipients")
    return Outcome(action, summary.strip(), details.strip(), tuple(recipients))


@dataclass(frozen=True)
class Incoming:
    event_id: str
    room: str
    sender: str
    body: str
    thread: str = ""


@dataclass(frozen=True)
class Job:
    id: str
    topic: str
    agent: str
    prompt: str
    event_id: str
    round: int
    reply_agent: str = ""


@dataclass(frozen=True)
class RunResult:
    session: str
    text: str


@dataclass(frozen=True)
class Notice:
    id: str
    room: str
    agent: str
    body: str
    human: bool
    thread: str = ""
