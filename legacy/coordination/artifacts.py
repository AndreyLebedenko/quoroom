import os
from pathlib import Path

from .model import identifier


class Artifacts:
    def __init__(self, project: Path):
        self.project = project.resolve(strict=True)

    def directory(self, topic: str) -> Path:
        path = (
            self.project
            / ".agent-comms"
            / "active"
            / ("ac-" + identifier(topic))
            / "bridge"
        )
        if not path.resolve().is_relative_to(self.project):
            raise ValueError("Artifact path leaves the project")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def record(self, topic: str, record_id: str, text: str) -> Path:
        path = self.directory(topic) / (identifier(record_id) + ".md")
        return self.immutable(path, text)

    def open_topic(
        self, topic: str, coordinator: str, participants: list[str], event: str
    ) -> None:
        self.immutable(
            self.directory(topic).parent / "README.md",
            f"# {topic}\n\nCoordinator: {coordinator}\n\nParticipants: {', '.join(participants)}\n\n"
            f"Decision authority: human. Explicit delegation: none.\n\nOpening event: {event}\n\n"
            "Initial round: 1. Maximum rounds: 3.\n\n"
            "Reports, round numbers, human responses and task references are recorded in [bridge/](bridge/).\n"
            "Current execution status is maintained by AgentsChat; an open question blocks dependent work.\n",
        )

    @staticmethod
    def immutable(path: Path, text: str) -> Path:
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                raise ValueError(f"Published record differs: {path}")
            return path
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        return path

    def relative(self, path: Path) -> str:
        return path.relative_to(self.project).as_posix()
