from __future__ import annotations

from argparse import ArgumentParser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .boundaries import Boundaries
from .steps import Destructive, FoundStep, Plan, Run, Step

INSTALL_ORDER = ("server", "participant")
REMOVE_ORDER = ("participant", "server")
DEFAULT_CONSEQUENCE = "восстановить эти данные будет нечем."


class RoleOptions:
    def __init__(self, parser: ArgumentParser, role: str) -> None:
        self.parser = parser
        self.role = role
        self.dests: list[str] = []

    def add(self, flag: str, **kwargs) -> None:
        if "dest" in kwargs:
            raise TypeError(
                f"роль {self.role} не задаёт dest: имя ключа {flag} даёт его само"
            )
        dest = f"{self.role}_{flag.lstrip('-').replace('-', '_')}"
        self.parser.add_argument(flag, dest=dest, **kwargs)
        self.dests.append(dest)


def no_options(options: RoleOptions) -> None:
    return None


def no_report(run: Run) -> None:
    return None


@dataclass(frozen=True)
class Role:
    name: str
    record_path: Callable[[Boundaries], Path]
    install: tuple[Step, ...] = ()
    remove: tuple[Step, ...] = ()
    purge: tuple[Step, ...] = ()
    purge_consequence: str = ""
    report: Callable[[Run], None] = no_report
    add_options: Callable[[RoleOptions], None] = no_options

    def __post_init__(self) -> None:
        for step in self.purge:
            if not isinstance(step, Destructive):
                raise TypeError(
                    f"шаг очистки «{step.name}» роли {self.name} не объявляет, что удаляет"
                )
        for step in self.remove:
            if isinstance(step, FoundStep):
                raise TypeError(
                    f"шаг удаления «{step.name}» роли {self.name} ищет незаписанное:"
                    " такое удаляют только с вопросом, то есть в очистке"
                )

    def steps_for(self, plan: Plan) -> tuple[Step, ...]:
        if not plan.remove:
            return self.install
        if plan.purge:
            return self.remove + self.purge
        return self.remove

    def destructive(self, plan: Plan) -> tuple[Destructive, ...]:
        if not plan.remove:
            return ()
        steps = tuple(step for step in self.remove if isinstance(step, Destructive))
        if not plan.purge:
            return steps
        return steps + tuple(
            step for step in self.purge if isinstance(step, Destructive)
        )

    def consequence(self) -> str:
        return self.purge_consequence or DEFAULT_CONSEQUENCE


def built_in_roles() -> tuple[Role, ...]:
    return ()


def order(names: Sequence[str], remove: bool) -> tuple[str, ...]:
    wanted = list(names)
    sequence = REMOVE_ORDER if remove else INSTALL_ORDER
    ordered = [name for name in sequence if name in wanted]
    ordered += [name for name in wanted if name not in ordered]
    return tuple(ordered)


def consequence_of(roles: Sequence[Role]) -> str:
    said = [role.consequence() for role in roles if role.purge]
    return " ".join(dict.fromkeys(said)) or DEFAULT_CONSEQUENCE
