from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import Enum
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable

CLIS = ("claude", "opencode")
CLI_NAMES = {"claude": "Claude Code", "opencode": "OpenCode"}
DEFAULT_ROOTS = {
    "claude": Path.home() / ".claude",
    "opencode": Path.home() / ".config" / "opencode",
}
KIT = files(__package__) / "kit"


class Action(Enum):
    INSTALL = "installed"
    UPDATE = "updated"
    OVERWRITE = "overwritten"
    UNCHANGED = "unchanged"
    CONFLICT = "conflict"
    REMOVE = "removed"
    KEEP = "kept"
    GONE = "gone"


WRITES = frozenset({Action.INSTALL, Action.UPDATE, Action.OVERWRITE})

COMMAND_INSTALL = "install"
COMMAND_UNINSTALL = "uninstall"
CODE_NONE = "none"
CODE_CONFLICT = "conflict"

DISPLAY_RU = {
    Action.INSTALL: "установлен",
    Action.UPDATE: "обновлён",
    Action.OVERWRITE: "перезаписан",
    Action.UNCHANGED: "без изменений",
    Action.CONFLICT: "занят чужим файлом",
    Action.REMOVE: "удалён",
    Action.KEEP: "оставлен (изменён вручную)",
    Action.GONE: "уже нет",
}


@dataclass(frozen=True)
class KitFile:
    cli: str
    relative: PurePosixPath
    content: bytes


@dataclass(frozen=True)
class Entry:
    cli: str
    sha256: str


@dataclass(frozen=True)
class Step:
    action: Action
    target: Path
    cli: str
    content: bytes = b""

    def line(self) -> str:
        return f"{DISPLAY_RU[self.action]}  {self.target}"


@dataclass(frozen=True)
class Report:
    command: str
    code: str
    steps: tuple[Step, ...] = ()

    @property
    def ok(self) -> bool:
        return self.code == CODE_NONE

    @property
    def wrote(self) -> bool:
        return any(step.action in WRITES for step in self.steps)

    @property
    def refused(self) -> tuple[Step, ...]:
        return tuple(conflicts(self.steps))

    def as_json(self) -> str:
        return json.dumps(
            {
                "command": self.command,
                "ok": self.ok,
                "code": self.code,
                "steps": [
                    {
                        "action": step.action.value,
                        "cli": step.cli,
                        "target": str(step.target),
                    }
                    for step in self.steps
                ],
            },
            ensure_ascii=True,
        )

    @classmethod
    def read(cls, raw: str, command: str) -> "Report | None":
        try:
            stored = json.loads(raw)
            steps = tuple(
                Step(Action(step["action"]), Path(step["target"]), str(step["cli"]))
                for step in stored["steps"]
            )
            code = str(stored["code"])
            if str(stored["command"]) != command:
                return None
            if stored["ok"] is not (code == CODE_NONE):
                return None
            if code != CODE_NONE and not steps:
                return None
        except (ValueError, KeyError, TypeError):
            return None
        return cls(command, code, steps)


def conflicts(steps: Iterable[Step]) -> list[Step]:
    return [step for step in steps if step.action is Action.CONFLICT]


class KitConflict(Exception):
    def __init__(self, steps: list[Step]):
        self.steps = steps
        listed = "\n".join(f"    {step.target}" for step in steps)
        super().__init__(
            "установка отменена, ничего не записано. Эти файлы уже существуют, "
            "отличаются от набора Quoroom и установлены не им:\n"
            f"{listed}\n"
            "Чтобы перезаписать их, повторите с --force: agentschat install --force"
        )

    @property
    def targets(self) -> list[Path]:
        return [step.target for step in self.steps]


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def chosen_clis(claude: bool, opencode: bool) -> tuple[str, ...]:
    picked = tuple(cli for cli, flag in zip(CLIS, (claude, opencode)) if flag)
    return picked or CLIS


def target_roots(
    clis: tuple[str, ...],
    claude_dir: str | None = None,
    opencode_dir: str | None = None,
) -> dict[str, Path]:
    given = {"claude": claude_dir, "opencode": opencode_dir}
    return {cli: Path(given[cli]) if given[cli] else DEFAULT_ROOTS[cli] for cli in clis}


def kit_files(cli: str, source: Traversable = KIT) -> list[KitFile]:
    return [
        KitFile(cli, relative, node.read_bytes())
        for relative, node in walk(source / cli, PurePosixPath())
    ]


def walk(
    node: Traversable, prefix: PurePosixPath
) -> Iterator[tuple[PurePosixPath, Traversable]]:
    for child in sorted(node.iterdir(), key=lambda item: item.name):
        relative = prefix / child.name
        if child.is_dir():
            yield from walk(child, relative)
        else:
            yield relative, child


def load_manifest(path: Path) -> dict[Path, Entry]:
    if not path.is_file():
        return {}
    stored = json.loads(path.read_text(encoding="utf-8"))
    return {
        Path(item["path"]): Entry(item["cli"], item["sha256"])
        for item in stored["files"]
    }


def save_manifest(path: Path, manifest: dict[Path, Entry]) -> None:
    if not manifest:
        path.unlink(missing_ok=True)
        return
    items = [
        {"path": str(target), "sha256": entry.sha256, "cli": entry.cli}
        for target, entry in sorted(manifest.items(), key=lambda item: str(item[0]))
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"files": items}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def install_action(content: bytes, target: Path, listed: bool, force: bool) -> Action:
    if not target.exists():
        return Action.INSTALL
    if target.read_bytes() == content:
        return Action.UNCHANGED
    if listed:
        return Action.UPDATE
    return Action.OVERWRITE if force else Action.CONFLICT


def plan_install(
    roots: dict[str, Path],
    manifest: dict[Path, Entry],
    force: bool = False,
    source: Traversable = KIT,
) -> list[Step]:
    steps = []
    for cli, root in roots.items():
        for item in kit_files(cli, source):
            target = root.resolve().joinpath(*item.relative.parts)
            action = install_action(item.content, target, target in manifest, force)
            steps.append(Step(action, target, cli, item.content))
    return steps


def apply_install(steps: list[Step], manifest: dict[Path, Entry]) -> dict[Path, Entry]:
    refused = conflicts(steps)
    if refused:
        raise KitConflict(refused)
    updated = dict(manifest)
    for step in steps:
        if step.action in WRITES:
            step.target.parent.mkdir(parents=True, exist_ok=True)
            step.target.write_bytes(step.content)
        updated[step.target] = Entry(step.cli, digest(step.content))
    return updated


def install(
    manifest_path: Path,
    roots: dict[str, Path],
    force: bool = False,
    source: Traversable = KIT,
) -> list[Step]:
    manifest = load_manifest(manifest_path)
    steps = plan_install(roots, manifest, force, source)
    save_manifest(manifest_path, apply_install(steps, manifest))
    return steps


def uninstall_action(target: Path, entry: Entry, force: bool) -> Action:
    if not target.exists():
        return Action.GONE
    if force or digest(target.read_bytes()) == entry.sha256:
        return Action.REMOVE
    return Action.KEEP


def plan_uninstall(
    manifest: dict[Path, Entry], clis: tuple[str, ...], force: bool = False
) -> list[Step]:
    return [
        Step(uninstall_action(target, entry, force), target, entry.cli)
        for target, entry in sorted(manifest.items(), key=lambda item: str(item[0]))
        if entry.cli in clis
    ]


def prune_empty_parents(directory: Path, root: Path) -> None:
    while root in directory.parents and not any(directory.iterdir()):
        directory.rmdir()
        directory = directory.parent


def apply_uninstall(
    steps: list[Step], manifest: dict[Path, Entry], roots: dict[str, Path]
) -> dict[Path, Entry]:
    updated = dict(manifest)
    for step in steps:
        if step.action is Action.KEEP:
            continue
        if step.action is Action.REMOVE:
            step.target.unlink()
            prune_empty_parents(step.target.parent, roots[step.cli].resolve())
        del updated[step.target]
    return updated


def uninstall(
    manifest_path: Path,
    roots: dict[str, Path],
    clis: tuple[str, ...] = CLIS,
    force: bool = False,
) -> list[Step]:
    manifest = load_manifest(manifest_path)
    steps = plan_uninstall(manifest, clis, force)
    save_manifest(manifest_path, apply_uninstall(steps, manifest, roots))
    return steps


def restart_hint(changed: list[Step]) -> str:
    touched = {step.cli for step in changed}
    names = " и ".join(CLI_NAMES[cli] for cli in CLIS if cli in touched)
    return f"Перезапустите открытые сессии {names}: запущенные изменений не увидят."


def install_summary(steps: list[Step]) -> str:
    changed = [step for step in steps if step.action in WRITES]
    if not changed:
        return "AGENTSCHAT: набор Quoroom уже на месте, менять нечего."
    return f"AGENTSCHAT: набор Quoroom установлен.\n{restart_hint(changed)}"


def uninstall_summary(steps: list[Step]) -> str:
    if not steps:
        return "AGENTSCHAT: установленного набора Quoroom нет, удалять нечего."
    lines = ["AGENTSCHAT: удаление набора Quoroom закончено."]
    removed = [step for step in steps if step.action is Action.REMOVE]
    if removed:
        lines.append(restart_hint(removed))
    if any(step.action is Action.KEEP for step in steps):
        lines.append(
            "Файлы, изменённые вручную, оставлены. Удалить и их: "
            "agentschat uninstall --force"
        )
    return "\n".join(lines)
