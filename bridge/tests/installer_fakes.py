from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import CompletedProcess

from sessionchat.installer.boundaries import Boundaries, Probe, WINDOWS
from sessionchat.installer.confirmation import Confirmation
from sessionchat.installer.ownership import Ownership
from sessionchat.installer.ownership import PurgeTarget
from sessionchat.installer.roles import Role, unrestorable
from sessionchat.installer.secrets import Secrets
from sessionchat.installer.steps import (
    NeedsHuman,
    OwnedStep,
    Plan,
    Run,
    State,
    Step,
)

SH = shutil.which("sh")


def posix_path(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    text = str(path)
    if len(text) > 1 and text[1] == ":":
        return f"/{text[0].lower()}{text[2:]}".replace("\\", "/")
    return text.replace("\\", "/")


class Input(io.StringIO):
    def __init__(self, text: str = "", interactive: bool = False) -> None:
        super().__init__(text)
        self.interactive = interactive

    def isatty(self) -> bool:
        return self.interactive


def completed(stdout: str = "", stderr: str = "", code: int = 0) -> CompletedProcess:
    return CompletedProcess([], code, stdout, stderr)


def boundaries(
    home: Path,
    stdin: str = "",
    interactive: bool = False,
    repo: Path | None = None,
    env: dict[str, str] | None = None,
    run: Callable[..., CompletedProcess] | None = None,
    probe: Callable[[str], Probe] | None = None,
    platform: str = WINDOWS,
    resolve: Callable[[str], Sequence[str]] | None = None,
    secret: Callable[[str], str] | None = None,
) -> Boundaries:
    return Boundaries(
        repo=repo or home,
        home=home,
        env=env or {},
        stdin=Input(stdin, interactive),
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        run=run or (lambda argv, **kwargs: completed()),
        probe=probe or (lambda url: Probe(200, None)),
        platform=platform,
        resolve=resolve or (lambda name: ("127.0.0.1",)),
        secret=secret or (lambda prompt: ""),
    )


@dataclass
class Marker:
    name: str
    log: list[str]
    done: bool = False
    stays_todo: bool = False
    raises: Exception | None = None
    error_on_recheck: bool = False
    applied: bool = field(default=False, init=False)

    def check(self, run) -> State:
        self.log.append(f"check:{self.name}")
        if self.error_on_recheck and self.applied and self.raises is not None:
            raise self.raises
        if self.done or (self.applied and not self.stays_todo):
            return State.DONE
        return State.TODO

    def apply(self, run) -> None:
        self.log.append(f"apply:{self.name}")
        if self.raises is not None and not self.error_on_recheck:
            raise self.raises
        self.applied = True


@dataclass
class FileMarker:
    name: str
    path: Path
    log: list[str]
    raises_on_apply: Exception | None = None
    needs_human: str = ""

    def check(self, run) -> State:
        self.log.append(f"check:{self.name}")
        return State.DONE if self.path.exists() else State.TODO

    def apply(self, run) -> None:
        self.log.append(f"apply:{self.name}")
        if self.needs_human:
            raise NeedsHuman(self.needs_human)
        if self.raises_on_apply is not None:
            raise self.raises_on_apply
        self.path.write_text("сделано\n", encoding="utf-8")


def owned_remover(name: str, role: str, kind: str, log: list[str]) -> OwnedStep:
    def delete(run, id: str) -> None:
        log.append(f"delete:{id}")
        Path(id).unlink(missing_ok=True)

    return OwnedStep(name, role, kind, delete)


def role(
    name: str,
    install: Sequence[Step] = (),
    remove: Sequence[Step] = (),
    purge: Sequence[Step] = (),
    consequence: Callable[[Sequence[PurgeTarget]], str] | None = None,
    add_options: Callable | None = None,
    report: Callable | None = None,
    record: str | None = None,
) -> Role:
    def record_path(
        boundaries: Boundaries, filename: str = record or f"{name}.json"
    ) -> Path:
        return boundaries.home / "records" / filename

    return Role(
        name=name,
        record_path=record_path,
        install=tuple(install),
        remove=tuple(remove),
        purge=tuple(purge),
        purge_consequence=consequence or unrestorable,
        report=report or (lambda run: None),
        add_options=add_options or (lambda options: None),
    )


def option(flag: str, action: str | None = None, **kwargs) -> Callable:
    def add(options) -> None:
        given = {"action": action} if action else dict(kwargs)
        options.add(flag, **given)

    return add


def recorded(home: Path, filename: str, entries: Sequence[tuple[str, str]]) -> Path:
    path = home / filename
    items = [{"kind": kind, "id": id} for kind, id in entries]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"entries": items}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


class InstallerTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.log: list[str] = []

    def record(self, role: str) -> Path:
        return self.home / "records" / f"{role}.json"

    def boundaries(self, **values) -> Boundaries:
        return boundaries(self.home, **values)

    def run_for(
        self,
        given: Boundaries,
        ownerships: Mapping[str, Ownership] | None = None,
        remove: bool = False,
        purge: bool = False,
        answers: dict[str, dict[str, object]] | None = None,
    ) -> Run:
        return make_run(
            given, ownerships=ownerships, remove=remove, purge=purge, answers=answers
        )


def make_run(
    given: Boundaries,
    ownerships: Mapping[str, Ownership] | None = None,
    remove: bool = False,
    purge: bool = False,
    answers: dict[str, dict[str, object]] | None = None,
) -> Run:
    secrets = Secrets()
    plan = Plan(tuple(ownerships or ()), remove, purge, answers or {})
    return Run(given, plan, secrets, Confirmation(given, secrets), ownerships or {})


__all__ = [
    "SH",
    "FileMarker",
    "InstallerTestCase",
    "Marker",
    "State",
    "boundaries",
    "make_run",
    "option",
    "owned_remover",
    "posix_path",
    "recorded",
    "role",
]
