from __future__ import annotations

import sys
from argparse import ArgumentParser
from collections.abc import Sequence
from typing import IO

from .boundaries import Boundaries
from .errors import HelpRequested, UsageError
from .roles import Role, RoleOptions, order
from .steps import Plan

CORE_FLAGS = ("role", "remove", "purge")
BOTH = "both"
NO_ROLES = "в этой сборке нет ни одной роли: установщик без ролей делать нечего."


class Parser(ArgumentParser):
    def __init__(self, *args, stdout: IO[str], stderr: IO[str], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.stdout = stdout
        self.stderr = stderr

    def _print_message(self, message, file=None) -> None:
        if not message:
            return
        stream = self.stderr if file is sys.stderr else self.stdout
        stream.write(message)

    def error(self, message: str) -> None:
        raise UsageError(f"{message}\n{self.format_usage()}")

    def exit(self, status: int = 0, message: str | None = None) -> None:
        if status == 0:
            raise HelpRequested()
        raise UsageError(message or "")


def parser_for(
    roles: Sequence[Role], boundaries: Boundaries
) -> tuple[Parser, dict[str, list[str]]]:
    parser = Parser(
        prog="install",
        description="Установка и удаление Quoroom на одной машине",
        stdout=boundaries.stdout,
        stderr=boundaries.stderr,
    )
    parser.add_argument("--role", help="роль установки")
    parser.add_argument(
        "--remove", action="store_true", help="удалить вместо установки"
    )
    parser.add_argument("--purge", action="store_true", help="удалить и данные роли")
    grouped: dict[str, list[str]] = {}
    for role in roles:
        options = RoleOptions(parser, role.name)
        role.add_options(options)
        grouped[role.name] = options.dests
    return parser, grouped


def names_of(roles: Sequence[Role]) -> list[str]:
    return [role.name for role in roles]


def parse(argv: Sequence[str], boundaries: Boundaries, roles: Sequence[Role]) -> Plan:
    parser, grouped = parser_for(roles, boundaries)
    args = parser.parse_args(list(argv))
    if not roles:
        raise UsageError(NO_ROLES)
    if args.purge and not args.remove:
        raise UsageError("--purge имеет смысл только вместе с --remove")
    values = vars(args)
    answers = {
        name: {dest: values[dest] for dest in dests} for name, dests in grouped.items()
    }
    return Plan(
        order(_selected(args.role, boundaries, roles), args.remove),
        args.remove,
        args.purge,
        answers,
    )


def _selected(
    given: str | None, boundaries: Boundaries, roles: Sequence[Role]
) -> list[str]:
    if given == BOTH:
        return names_of(roles)
    if given:
        if given not in names_of(roles):
            raise UsageError(
                f"роль {given} неизвестна, доступны: {', '.join([BOTH, *names_of(roles)])}"
            )
        return [given]
    if boundaries.stdin.isatty():
        return _asked(boundaries, names_of(roles))
    raise UsageError(
        "не указан --role, а интерактивного ввода нет: передайте --role явно."
    )


def _asked(boundaries: Boundaries, names: Sequence[str]) -> list[str]:
    choices = [*names, BOTH] if len(names) > 1 else list(names)
    listing = "\n".join(
        f"    {index + 1}. {name}" for index, name in enumerate(choices)
    )
    boundaries.stdout.write(f"Что ставим или удаляем?\n{listing}\n")
    answer = boundaries.stdin.readline().strip()
    number = int(answer) if answer.isdigit() else 0
    picked = choices[number - 1] if 1 <= number <= len(choices) else answer
    if picked == BOTH:
        return list(names)
    if picked in names:
        return [picked]
    raise UsageError(f"не понял выбор: {answer!r}. Повторите запуск с --role.")
