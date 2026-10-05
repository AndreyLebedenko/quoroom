from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

from .boundaries import Boundaries
from .catalogue import step_label, text
from .confirmation import Confirmation
from .ownership import Ownership, PurgeTarget
from .secrets import Secrets


class State(Enum):
    DONE = "done"
    TODO = "todo"


class Outcome(Enum):
    DONE = "done"
    HUMAN = "human"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
                run.t(
                    "steps.kept_as_record",
                    step=run.label(self.name),
                    ids=", ".join(target.id for target in records),
                ),
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

    def t(self, key: str, **params: object) -> str:
        return text(self.boundaries.lang, key, **params)

    def label(self, name: str) -> str:
        return step_label(self.boundaries.lang, name)

    def say(self, line: str) -> None:
        self.boundaries.stdout.write(self.secrets.scrub(line) + "\n")

    def warn(self, line: str) -> None:
        self.boundaries.stderr.write(self.secrets.scrub(line) + "\n")

    def warn_once(self, key: str, line: str) -> None:
        if key in self.warned:
            return
        self.warned.add(key)
        self.warn(line)


@dataclass(frozen=True)
class Failure:
    step: str
    completed: tuple[str, ...]
    error: str = ""

    def render(self, secrets: Secrets, lang: str) -> str:
        lines = [text(lang, "steps.failure_step", step=step_label(lang, self.step))]
        if self.error:
            lines.append(text(lang, "steps.failure_reason", error=self.error))
        if self.completed:
            lines.append(text(lang, "steps.failure_saved"))
            lines += [f"    {step_label(lang, name)}" for name in self.completed]
        lines.append(text(lang, "steps.resume"))
        return secrets.scrub("\n".join(lines))


def report_kept(run: Run, name: str, targets: Sequence[PurgeTarget]) -> None:
    if targets:
        run.warn_once(
            f"kept:{name}",
            run.t(
                "steps.kept_unconfirmed",
                step=run.label(name),
                ids=", ".join(t.id for t in targets),
            ),
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
            run.say(run.t("steps.already_done", step=run.label(step.name)))
            return Outcome.DONE
        step.apply(run)
        state = step.check(run)
    except NeedsHuman as need:
        run.say(str(need))
        run.warn(
            run.t(
                "steps.stopped_for_human",
                step=run.label(step.name),
                resume=run.t("steps.resume"),
            )
        )
        return Outcome.HUMAN
    except Cancelled:
        run.warn(run.t("steps.cancelled"))
        return Outcome.CANCELLED
    except Exception as error:
        return refuse(step, run, error)
    if state is State.TODO:
        return refuse(step, run, None)
    run.say(run.t("steps.done", step=run.label(step.name)))
    run.completed.append(step.name)
    return Outcome.DONE


def refuse(step: Step, run: Run, error: Exception | None) -> Outcome:
    failure = Failure(step.name, tuple(run.completed), str(error or ""))
    run.warn(failure.render(run.secrets, run.boundaries.lang))
    return Outcome.FAILED
