from __future__ import annotations

from collections.abc import Sequence

from .boundaries import Boundaries
from .confirmation import Confirmation
from .errors import HelpRequested, UsageError
from .options import parse
from .ownership import Ownership, PurgeTarget
from .roles import Role, consequence_of
from .secrets import Secrets
from .steps import Cancelled, Failure, Outcome, Plan, Run, execute

DONE = 0
FAILED = 1
USAGE = 2
HUMAN = 3
CANCELLED = 4
PREPARE = "подготовка запуска"
REPORT = "отчёт после установки"

CODES = {
    Outcome.DONE: DONE,
    Outcome.FAILED: FAILED,
    Outcome.HUMAN: HUMAN,
    Outcome.CANCELLED: CANCELLED,
}


def main(argv: Sequence[str], boundaries: Boundaries, roles: Sequence[Role]) -> int:
    try:
        plan = parse(argv, boundaries, roles)
    except HelpRequested:
        return DONE
    except UsageError as problem:
        boundaries.stderr.write(f"AGENTSCHAT: {problem}\n")
        return USAGE

    secrets = Secrets()
    by_name = {role.name: role for role in roles}
    selected = [by_name[name] for name in plan.roles]
    try:
        ownerships = {
            role.name: Ownership.load(role.record_path(boundaries)) for role in selected
        }
        run = Run(
            boundaries,
            plan,
            secrets,
            Confirmation(boundaries, secrets),
            ownerships,
            records=frozenset(role.record_path(boundaries).resolve() for role in roles),
        )
        targets = _targets(selected, plan, run)
        if plan.purge:
            _confirmed(run, targets, consequence_of(selected, targets))
    except Cancelled:
        boundaries.stderr.write("Отменено человеком, ничего не изменено.\n")
        return CANCELLED
    except Exception as error:
        return _failed(boundaries, secrets, PREPARE, error)

    for role in selected:
        outcome = execute(role.steps_for(plan), run)
        if outcome is not Outcome.DONE:
            return CODES[outcome]
    try:
        for role in selected:
            role.report(run)
    except Exception as error:
        return _failed(boundaries, secrets, REPORT, error, tuple(run.completed))
    return DONE


def _confirmed(run: Run, targets: tuple[PurgeTarget, ...], consequence: str) -> None:
    if not targets:
        return
    if not run.confirm.ask(consequence, targets):
        raise Cancelled
    run.confirmed.update(targets)


def _failed(
    boundaries: Boundaries,
    secrets: Secrets,
    step: str,
    error: Exception,
    completed: tuple[str, ...] = (),
) -> int:
    failure = Failure(step, completed, str(error))
    boundaries.stderr.write(failure.render(secrets) + "\n")
    return FAILED


def _targets(roles: Sequence[Role], plan: Plan, run: Run) -> tuple[PurgeTarget, ...]:
    return tuple(
        target
        for role in roles
        for step in role.destructive(plan)
        for target in step.targets(run)
    )
