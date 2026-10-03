import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Entry:
    kind: str
    id: str


@dataclass(frozen=True)
class PurgeTarget:
    role: str
    kind: str
    id: str


@dataclass
class Ownership:
    path: Path
    entries: list[Entry] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Ownership":
        if not path.is_file():
            return cls(path)
        stored = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            path,
            [Entry(str(item["kind"]), str(item["id"])) for item in stored["entries"]],
        )

    def record(self, kind: str, id: str) -> None:
        if not self.owns(kind, id):
            self.entries.append(Entry(kind, id))

    def forget(self, kind: str, id: str) -> None:
        self.entries = [
            entry for entry in self.entries if entry.id != id or entry.kind != kind
        ]

    def of_kind(self, kind: str) -> list[str]:
        return [entry.id for entry in self.entries if entry.kind == kind]

    def owns(self, kind: str, id: str) -> bool:
        return any(entry.id == id and entry.kind == kind for entry in self.entries)

    def save(self) -> None:
        if not self.entries:
            self.path.unlink(missing_ok=True)
            return
        items = [{"kind": entry.kind, "id": entry.id} for entry in self.entries]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"entries": items}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
