from __future__ import annotations

import sys
from argparse import ArgumentParser
from collections.abc import Sequence
from typing import IO

from .boundaries import Boundaries
from .catalogue import DEFAULT_LANGUAGE, LANGUAGES, text
from .errors import HelpRequested, UsageError
from .roles import Role, RoleOptions, order
from .steps import Plan

CORE_FLAGS = ("role", "remove", "purge")
BOTH = "both"
LANGUAGE_FLAG = "--lang"


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
    lang = boundaries.lang
    parser = Parser(
        prog="install",
        description=text(lang, "options.description"),
        stdout=boundaries.stdout,
        stderr=boundaries.stderr,
    )
    parser.add_argument("--role", help=text(lang, "options.help_role"))
    parser.add_argument(
        "--remove", action="store_true", help=text(lang, "options.help_remove")
    )
    parser.add_argument(
        "--purge", action="store_true", help=text(lang, "options.help_purge")
    )
    parser.add_argument(
        LANGUAGE_FLAG,
        choices=LANGUAGES,
        default=lang,
        help=text(lang, "options.help_lang"),
    )
    grouped: dict[str, list[str]] = {}
    for role in roles:
        options = RoleOptions(parser, role.name, lang)
        role.add_options(options)
        grouped[role.name] = options.dests
    return parser, grouped


def names_of(roles: Sequence[Role]) -> list[str]:
    return [role.name for role in roles]


def language_of(argv: Sequence[str], default: str) -> str:
    chosen = default
    for index, argument in enumerate(argv):
        if argument == LANGUAGE_FLAG and index + 1 < len(argv):
            chosen = argv[index + 1]
        elif argument.startswith(f"{LANGUAGE_FLAG}="):
            chosen = argument.partition("=")[2]
    return chosen


def chosen_language(argv: Sequence[str], default: str) -> str:
    chosen = language_of(argv, default)
    if chosen not in LANGUAGES:
        raise UsageError(
            text(
                DEFAULT_LANGUAGE,
                "options.unknown_language",
                value=chosen,
                available=", ".join(LANGUAGES),
            )
        )
    return chosen


def parse(argv: Sequence[str], boundaries: Boundaries, roles: Sequence[Role]) -> Plan:
    parser, grouped = parser_for(roles, boundaries)
    args = parser.parse_args(list(argv))
    lang = boundaries.lang
    if not roles:
        raise UsageError(text(lang, "options.no_roles"))
    if args.purge and not args.remove:
        raise UsageError(text(lang, "options.purge_needs_remove"))
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
                text(
                    boundaries.lang,
                    "options.unknown_role",
                    role=given,
                    available=", ".join([BOTH, *names_of(roles)]),
                )
            )
        return [given]
    if boundaries.stdin.isatty():
        return _asked(boundaries, names_of(roles))
    raise UsageError(text(boundaries.lang, "options.role_missing"))


def _asked(boundaries: Boundaries, names: Sequence[str]) -> list[str]:
    choices = [*names, BOTH] if len(names) > 1 else list(names)
    listing = "\n".join(
        f"    {index + 1}. {name}" for index, name in enumerate(choices)
    )
    asking = text(boundaries.lang, "options.ask_role", listing=listing)
    boundaries.stdout.write(f"{asking}\n")
    answer = boundaries.stdin.readline().strip()
    number = int(answer) if answer.isdigit() else 0
    picked = choices[number - 1] if 1 <= number <= len(choices) else answer
    if picked == BOTH:
        return list(names)
    if picked in names:
        return [picked]
    raise UsageError(text(boundaries.lang, "options.bad_choice", answer=answer))
