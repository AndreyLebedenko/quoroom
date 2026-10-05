from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

from .boundaries import Boundaries
from .confirmation import Confirmation
from .ownership import Ownership, PurgeTarget
from .secrets import Secrets

RESUME = "Повторите ту же команду: она продолжит с места, где остановилась."


class State(Enum):
    DONE = "сделано"
    TODO = "не сделано"


class Outcome(Enum):
    DONE = "выполнено"
    HUMAN = "нужен человек"
    FAILED = "сбой"
    CANCELLED = "отменено"


class Cancelled(Exception):
    pass


class NeedsHuman(Exception):
    pass


@dataclass(frozen=True)
class Plan:
    roles: tuple[str, ...]
    remove: bool
    purge: bool
    answers: dict[str, dict[str, object]] = field(default_factory=dict)


class Step(Protocol):
    name: str

    def check(self, run: "Run") -> State: ...

    def apply(self, run: "Run") -> None: ...


@runtime_checkable
class Destructive(Protocol):
    def targets(self, run: "Run") -> Sequence[PurgeTarget]: ...


def unlink(run: "Run", id: str) -> None:
    Path(id).unlink(missing_ok=True)


def approved(run: "Run", targets: Sequence[PurgeTarget]) -> list[PurgeTarget]:
    if not run.plan.purge:
        return list(targets)
    return [target for target in targets if target in run.confirmed]


def unapproved(run: "Run", targets: Sequence[PurgeTarget]) -> list[PurgeTarget]:
    if not run.plan.purge:
        return []
    return [target for target in targets if target not in run.confirmed]


@dataclass(frozen=True)
class OwnedStep:
    name: str
    role: str
    kind: str
    delete: Callable[["Run", str], None] = unlink

    def targets(self, run: "Run") -> list[PurgeTarget]:
        ownership = run.ownership_of(self.role)
        return [
            PurgeTarget(self.role, self.kind, id) for id in ownership.of_kind(self.kind)
        ]

    def check(self, run: "Run") -> State:
        targets = self.targets(run)
        report_kept(run, self.name, unapproved(run, targets))
        return State.TODO if approved(run, targets) else State.DONE

    def apply(self, run: "Run") -> None:
        for target in approved(run, self.targets(run)):
            self.delete(run, target.id)
            run.forget(self.role, self.kind, target.id)


@dataclass(frozen=True)
class FoundStep:
    name: str
    role: str
    kind: str
    found: Callable[["Run"], Sequence[str]]
    delete: Callable[["Run", str], None] = unlink

    def discovered(self, run: "Run") -> list[PurgeTarget]:
        return [PurgeTarget(self.role, self.kind, id) for id in self.found(run)]

    def is_record(self, run: "Run", target: PurgeTarget) -> bool:
        return Path(target.id).resolve() in run.records

    def targets(self, run: "Run") -> list[PurgeTarget]:
        return [
            target for target in self.discovered(run) if not self.is_record(run, target)
        ]

    def check(self, run: "Run") -> State:
        found = self.discovered(run)
        records = [target for target in found if self.is_record(run, target)]
        if records:
            run.warn_once(
                f"records:{self.name}",
                f"{self.name}: оставлено как запись установщика: "
                + ", ".join(target.id for target in records),
            )
        targets = self.targets(run)
        report_kept(run, self.name, unapproved(run, targets))
        return State.TODO if approved(run, targets) else State.DONE

    def apply(self, run: "Run") -> None:
        for target in approved(run, self.targets(run)):
            self.delete(run, target.id)


@dataclass(frozen=True)
class HumanStep:
    name: str
    instruction: str
    done: Callable[["Run"], bool]

    def check(self, run: "Run") -> State:
        return State.DONE if self.done(run) else State.TODO

    def apply(self, run: "Run") -> None:
        raise NeedsHuman(self.instruction)


@dataclass
class Run:
    boundaries: Boundaries
    plan: Plan
    secrets: Secrets
    confirm: Confirmation
    ownerships: Mapping[str, Ownership]
    completed: list[str] = field(default_factory=list)
    confirmed: set[PurgeTarget] = field(default_factory=set)
    records: frozenset[Path] = frozenset()
    warned: set[str] = field(default_factory=set)

    def ownership_of(self, role: str) -> Ownership:
        return self.ownerships[role]

    def record(self, role: str, kind: str, id: str) -> None:
        ownership = self.ownership_of(role)
        ownership.record(kind, id)
        ownership.save()

    def forget(self, role: str, kind: str, id: str) -> None:
        ownership = self.ownership_of(role)
        ownership.forget(kind, id)
        ownership.save()

    def say(self, text: str) -> None:
        self.boundaries.stdout.write(self.secrets.scrub(text) + "\n")

    def warn(self, text: str) -> None:
        self.boundaries.stderr.write(self.secrets.scrub(text) + "\n")

    def warn_once(self, key: str, text: str) -> None:
        if key in self.warned:
            return
        self.warned.add(key)
        self.warn(text)


@dataclass(frozen=True)
class Failure:
    step: str
    completed: tuple[str, ...]
    error: str = ""

    def render(self, secrets: Secrets) -> str:
        lines = [f"Сбой на шаге «{self.step}»."]
        if self.error:
            lines.append(f"Причина: {secrets.scrub(self.error)}")
        if self.completed:
            lines.append("Изменения этого запуска сохранены:")
            lines += [f"    {name}" for name in self.completed]
        lines.append(RESUME)
        return "\n".join(lines)


def report_kept(run: Run, name: str, targets: Sequence[PurgeTarget]) -> None:
    if targets:
        run.warn_once(
            f"kept:{name}",
            f"{name}: не подтверждено и оставлено: " + ", ".join(t.id for t in targets),
        )


def execute(steps: Sequence[Step], run: Run) -> Outcome:
    for step in steps:
        outcome = _one(step, run)
        if outcome is not Outcome.DONE:
            return outcome
    return Outcome.DONE


def _one(step: Step, run: Run) -> Outcome:
    try:
        if step.check(run) is State.DONE:
            run.say(f"{step.name}: уже сделано.")
            return Outcome.DONE
        step.apply(run)
        state = step.check(run)
    except NeedsHuman as need:
        run.say(str(need))
        run.warn(
            f"Остановлено на шаге «{step.name}»: это должен сделать человек. {RESUME}"
        )
        return Outcome.HUMAN
    except Cancelled:
        run.warn("Отменено человеком, ничего не изменено.")
        return Outcome.CANCELLED
    except Exception as error:
        return refuse(step, run, error)
    if state is State.TODO:
        return refuse(step, run, None)
    run.say(f"{step.name}: готово.")
    run.completed.append(step.name)
    return Outcome.DONE


def refuse(step: Step, run: Run, error: Exception | None) -> Outcome:
    failure = Failure(step.name, tuple(run.completed), str(error or ""))
    run.warn(failure.render(run.secrets))
    return Outcome.FAILED
