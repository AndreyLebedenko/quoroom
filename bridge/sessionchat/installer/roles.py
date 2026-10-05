from __future__ import annotations

from argparse import ArgumentParser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .boundaries import Boundaries
from .catalogue import DEFAULT_LANGUAGE, text
from .ownership import PurgeTarget
from .steps import Destructive, FoundStep, Plan, Run, Step

INSTALL_ORDER = ("server", "participant")
REMOVE_ORDER = ("participant", "server")


class RoleOptions:
    def __init__(self, parser: ArgumentParser, role: str, lang: str) -> None:
        self.parser = parser
        self.role = role
        self.lang = lang
        self.dests: list[str] = []

    def t(self, key: str, **params: object) -> str:
        return text(self.lang, key, **params)

    def add(self, flag: str, **kwargs) -> None:
        if "dest" in kwargs:
            raise TypeError(self.t("roles.dest_not_allowed", role=self.role, flag=flag))
        dest = f"{self.role}_{flag.lstrip('-').replace('-', '_')}"
        self.parser.add_argument(flag, dest=dest, **kwargs)
        self.dests.append(dest)


def no_options(options: RoleOptions) -> None:
    return None


def no_report(run: Run) -> None:
    return None


def unrestorable(targets: Sequence[PurgeTarget], lang: str) -> str:
    return text(lang, "roles.default_consequence")


@dataclass(frozen=True)
class Role:
    name: str
    record_path: Callable[[Boundaries], Path]
    install: tuple[Step, ...] = ()
    remove: tuple[Step, ...] = ()
    purge: tuple[Step, ...] = ()
    purge_consequence: Callable[[Sequence[PurgeTarget], str], str] = unrestorable
    report: Callable[[Run], None] = no_report
    add_options: Callable[[RoleOptions], None] = no_options

    def __post_init__(self) -> None:
        for step in self.purge:
            if not isinstance(step, Destructive):
                raise TypeError(
                    text(
                        DEFAULT_LANGUAGE,
                        "roles.purge_step_not_destructive",
                        step=step.name,
                        role=self.name,
                    )
                )
        for step in self.remove:
            if isinstance(step, FoundStep):
                raise TypeError(
                    text(
                        DEFAULT_LANGUAGE,
                        "roles.remove_step_finds_unrecorded",
                        step=step.name,
                        role=self.name,
                    )
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

    def consequence(self, targets: Sequence[PurgeTarget], lang: str) -> str:
        return self.purge_consequence(targets, lang) or unrestorable(targets, lang)


def built_in_roles() -> tuple[Role, ...]:
    from .participant import participant_role
    from .server import server_role

    return (server_role(), participant_role())


def order(names: Sequence[str], remove: bool) -> tuple[str, ...]:
    wanted = list(names)
    sequence = REMOVE_ORDER if remove else INSTALL_ORDER
    ordered = [name for name in sequence if name in wanted]
    ordered += [name for name in wanted if name not in ordered]
    return tuple(ordered)


def consequence_of(
    roles: Sequence[Role], targets: Sequence[PurgeTarget], lang: str
) -> str:
    owners = {target.role for target in targets}
    said = [
        role.consequence(targets, lang)
        for role in roles
        if role.purge and role.name in owners
    ]
    return " ".join(dict.fromkeys(said)) or unrestorable(targets, lang)
