import sys
from pathlib import Path

from coordination.cli import AgentCLI
from coordination.settings import Account, Settings


def settings(root: Path) -> Settings:
    return Settings(
        root,
        root / "state.sqlite",
        "https://matrix.invalid",
        False,
        "!general",
        "!escalations",
        {"@human:local"},
        {"codex": Account("@codex:local", "test-device", "test-token")},
        {"codex": AgentCLI("codex", sys.executable)},
        18766,
    )
