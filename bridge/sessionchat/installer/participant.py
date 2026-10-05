from __future__ import annotations

import json
import os
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from .. import kit
from .boundaries import Boundaries, WINDOWS
from .catalogue import text
from .errors import UsageError
from .ownership import PurgeTarget, prune_record_home
from .report import Left, left_lines
from .roles import Role, RoleOptions
from .steps import FoundStep, NeedsHuman, Run, State

ROLE = "participant"
INSTALLER_HOME = ".quoroom"
STORE = ".agentschat"
KIT_MANIFEST = "kit.json"
PACKAGE = "quoroom"
PACKAGE_KIND = "package"
SESSION_KIND = "session"
REQUIRED_PYTHON = (3, 10)
DEFAULT_BROKER = "http://127.0.0.1:8770"
URL_DEST = "participant_broker_url"
CLAUDE_DEST = "participant_claude"
OPENCODE_DEST = "participant_opencode"
PATHEXT = ".COM;.EXE;.BAT;.CMD"
SERVER_ROLE = "server"
JSON_FLAG = "--json"
INSTALL_ENTRY = {"windows": "install.ps1", "linux": "install.sh"}


@dataclass(frozen=True)
class Tool:
    name: str
    listed: tuple[str, ...]
    install: tuple[str, ...]
    uninstall: tuple[str, ...]
    bin_query: tuple[str, ...]
    path_command: str


UV = Tool(
    "uv",
    ("tool", "list"),
    ("tool", "install", "--editable"),
    ("tool", "uninstall"),
    ("tool", "dir", "--bin"),
    "uv tool update-shell",
)
PIPX = Tool(
    "pipx",
    ("list", "--short"),
    ("install", "--editable"),
    ("uninstall",),
    ("environment", "--value", "PIPX_BIN_DIR"),
    "pipx ensurepath",
)
TOOLS = {UV.name: UV, PIPX.name: PIPX}


@dataclass(frozen=True)
class PythonStep:
    name: str
    running: tuple[int, int]

    def check(self, run: Run) -> State:
        return State.DONE if self.running >= REQUIRED_PYTHON else State.TODO

    def apply(self, run: Run) -> None:
        raise NeedsHuman(
            run.t(
                "participant.python_too_old",
                running=".".join(str(part) for part in self.running),
                required=f"{REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}",
            )
        )


@dataclass(frozen=True)
class ToolStep:
    name: str = "find_uv_or_pipx"

    def check(self, run: Run) -> State:
        return State.DONE if tool_of(run) is not None else State.TODO

    def apply(self, run: Run) -> None:
        raise NeedsHuman(tool_instruction(run))


@dataclass(frozen=True)
class PackageStep:
    name: str = "install_package"

    def check(self, run: Run) -> State:
        tool = owning_tool(run)
        if tool is None:
            return State.TODO
        if owned_tool(run) != tool.name:
            run.warn_once(
                f"present:{tool.name}", found_message(run, tool, owned_tool(run))
            )
        return State.DONE

    def apply(self, run: Run) -> None:
        tool = tool_of(run)
        if tool is None:
            raise NeedsHuman(tool_instruction(run))
        result = run.boundaries.run([tool.name, *tool.install, str(package_dir(run))])
        if result.returncode != 0:
            raise RuntimeError(tool_failure(run, tool, result))
        run.record(ROLE, PACKAGE_KIND, tool.name)


@dataclass
class KitInstallStep:
    name: str = "install_kit"
    handled: bool = False
    clis: tuple[str, ...] = ()
    written: bool = False

    def wanted(self, run: Run) -> tuple[str, ...]:
        if not self.clis:
            self.clis = wanted_clis(run)
        return self.clis

    def refreshable(self, run: Run) -> tuple[str, ...]:
        edited = stale_files(run)
        return tuple(cli for cli in self.wanted(run) if not edited.get(cli))

    def check(self, run: Run) -> State:
        if self.handled or not self.refreshable(run):
            return State.DONE
        return State.TODO

    def apply(self, run: Run) -> None:
        clis = self.refreshable(run)
        if clis:
            result = run.boundaries.run(
                [str(agentchat(run)), "install", *cli_flags(clis), JSON_FLAG]
            )
            if result.returncode != 0:
                raise RuntimeError(kit_failure(run, result, kit.COMMAND_INSTALL))
            report = kit_report(run, result, kit.COMMAND_INSTALL)
            if not report.ok:
                raise RuntimeError(kit_failure(run, result, kit.COMMAND_INSTALL))
            self.written = report.wrote
        self.handled = True


@dataclass
class Removal:
    uninstalled: bool = False
    package_gone: bool = False
    asked: tuple[str, ...] = ()


@dataclass
class KitRemoveStep:
    name: str = "remove_kit"
    handled: bool = False
    removal: Removal = field(default_factory=Removal, kw_only=True)

    def check(self, run: Run) -> State:
        if self.handled or not manifest_path(run).is_file():
            return State.DONE
        return State.TODO

    def apply(self, run: Run) -> None:
        path = agentchat(run)
        self.removal.asked = removal_clis(run)
        if not path.exists():
            run.warn(run.t("participant.agentschat_missing", manifest=KIT_MANIFEST))
        else:
            result = run.boundaries.run(
                [str(path), "uninstall", *cli_flags(self.removal.asked), JSON_FLAG]
            )
            if result.returncode != 0:
                raise RuntimeError(kit_failure(run, result, kit.COMMAND_UNINSTALL))
            self.removal.uninstalled = True
        self.handled = True


@dataclass
class PackageRemoveStep:
    name: str = "remove_package"
    removal: Removal = field(default_factory=Removal, kw_only=True)

    def check(self, run: Run) -> State:
        tool_name = owned_tool(run)
        if tool_name is None:
            if owning_tool(run) is not None:
                run.warn_once(
                    "unrecorded-package",
                    run.t("participant.package_unrecorded", package=PACKAGE),
                )
            return State.DONE
        using = clis_using_package(manifest_clis(run), self.removal)
        if using:
            run.warn_once("package-in-use", package_in_use(run, using))
            return State.DONE
        return State.TODO

    def apply(self, run: Run) -> None:
        tool_name = owned_tool(run)
        tool = TOOLS.get(tool_name)
        if tool is not None and tool_reports_package(run, tool):
            result = run.boundaries.run([tool.name, *tool.uninstall, PACKAGE])
            if result.returncode != 0:
                raise RuntimeError(tool_failure(run, tool, result))
            self.removal.package_gone = True
        elif tool is not None:
            run.warn(run.t("participant.package_stale_record", tool=tool.name))
        run.forget(ROLE, PACKAGE_KIND, tool_name)
        prune_record_home(record_path(run.boundaries))


@dataclass(frozen=True)
class BrokerStep:
    name: str = "check_broker"

    def check(self, run: Run) -> State:
        return State.DONE if answered(run) else State.TODO

    def apply(self, run: Run) -> None:
        error = run.boundaries.probe(f"{broker_url(run)}/status").error
        raise RuntimeError(broker_refusal(run, error))


def participant_consequence(targets: Sequence[PurgeTarget], lang: str) -> str:
    sessions = text(lang, "participant.consequence_sessions")
    if any(target.role == SERVER_ROLE for target in targets):
        return sessions
    return f"{sessions} {text(lang, 'participant.consequence_room_safe')}"


def participant_role(version: tuple[int, int] | None = None) -> Role:
    removal = Removal()
    kit = KitInstallStep()
    return Role(
        name=ROLE,
        record_path=record_path,
        install=(
            PythonStep("check_python", version or sys.version_info[:2]),
            ToolStep(),
            PackageStep(),
            kit,
            BrokerStep(),
        ),
        remove=(
            KitRemoveStep(removal=removal),
            PackageRemoveStep(removal=removal),
        ),
        purge=(session_step(),),
        purge_consequence=participant_consequence,
        report=partial(report, removal=removal, kit=kit),
        add_options=add_options,
    )


def add_options(options: RoleOptions) -> None:
    options.add(
        "--broker-url",
        default=DEFAULT_BROKER,
        help=options.t("participant.help_broker_url", default=DEFAULT_BROKER),
    )
    options.add(
        "--claude", action="store_true", help=options.t("participant.help_claude")
    )
    options.add(
        "--opencode", action="store_true", help=options.t("participant.help_opencode")
    )


def record_path(boundaries: Boundaries) -> Path:
    return boundaries.home / INSTALLER_HOME / "installer" / f"{ROLE}.json"


def store(run: Run) -> Path:
    return run.boundaries.home / STORE


def manifest_path(run: Run) -> Path:
    return store(run) / KIT_MANIFEST


def package_dir(run: Run) -> Path:
    return run.boundaries.repo / "bridge"


def session_step() -> FoundStep:
    return FoundStep(
        "remove_session_files",
        ROLE,
        SESSION_KIND,
        found=lambda run: broker_tokens(store(run)),
    )


def broker_tokens(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return [
        str(path)
        for path in sorted(directory.glob("*.json"))
        if path.name != KIT_MANIFEST and is_token(path)
    ]


def kept_files(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    tokens = set(broker_tokens(directory))
    return [
        str(path)
        for path in sorted(directory.iterdir())
        if path.name != KIT_MANIFEST and str(path) not in tokens
    ]


def is_token(path: Path) -> bool:
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(stored, dict) and bool(stored.get("token"))


def present_tools(run: Run) -> list[Tool]:
    return [tool for tool in (UV, PIPX) if tool_present(run, tool)]


def tool_of(run: Run) -> Tool | None:
    found = present_tools(run)
    return found[0] if found else None


def tool_present(run: Run, tool: Tool) -> bool:
    try:
        return run.boundaries.run([tool.name, "--version"]).returncode == 0
    except OSError:
        return False


def tool_reports_package(run: Run, tool: Tool) -> bool:
    try:
        result = run.boundaries.run([tool.name, *tool.listed])
    except OSError:
        return False
    return result.returncode == 0 and PACKAGE in listed_names(result.stdout or "")


def listed_names(output: str) -> set[str]:
    names = set()
    for line in output.splitlines():
        parts = line.strip().lstrip("-").split()
        if parts:
            names.add(parts[0])
    return names


def owning_tool(run: Run) -> Tool | None:
    recorded = owned_tool(run)
    if recorded in TOOLS and tool_reports_package(run, TOOLS[recorded]):
        return TOOLS[recorded]
    for tool in present_tools(run):
        if tool_reports_package(run, tool):
            return tool
    return None


def resolved_tool(run: Run) -> Tool:
    return owning_tool(run) or tool_of(run) or UV


def found_message(run: Run, tool: Tool, recorded: str | None) -> str:
    said = run.t("participant.package_found", package=PACKAGE, tool=tool.name)
    if recorded:
        said += " " + run.t("participant.package_found_record", recorded=recorded)
    return said


def package_in_use(run: Run, using: set[str]) -> str:
    return run.t(
        "participant.package_in_use", package=PACKAGE, clis=", ".join(sorted(using))
    )


def tool_failure(run: Run, tool: Tool, result) -> str:
    detail = (result.stderr or result.stdout or "").strip()
    return run.t("participant.package_install_failed", tool=tool.name, detail=detail)


def owned_tool(run: Run) -> str | None:
    tools = run.ownership_of(ROLE).of_kind(PACKAGE_KIND)
    return tools[0] if tools else None


def bin_dir(run: Run, tool: Tool) -> Path:
    answer = tool_answer(run, tool, tool.bin_query)
    if answer:
        return Path(answer)
    return run.boundaries.home / ".local" / "bin"


def tool_answer(run: Run, tool: Tool, argv: Sequence[str]) -> str:
    try:
        result = run.boundaries.run([tool.name, *argv])
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def agentchat(run: Run) -> Path:
    return bin_dir(run, resolved_tool(run)) / exe_name(run.boundaries)


def exe_name(boundaries: Boundaries) -> str:
    return "agentschat.exe" if boundaries.platform == WINDOWS else "agentschat"


def found_on_path(run: Run) -> Path | None:
    boundaries = run.boundaries
    names = (
        [
            f"agentschat{extension}"
            for extension in boundaries.env.get("PATHEXT", PATHEXT).split(";")
        ]
        if boundaries.platform == WINDOWS
        else ["agentschat"]
    )
    for directory in boundaries.env.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        for name in names:
            candidate = Path(directory) / name
            if candidate.is_file():
                return candidate
    return None


def stale_files(run: Run) -> dict[str, list[str]]:
    edited: dict[str, list[str]] = {}
    for target, entry in read_manifest(run).items():
        if not target.is_file() or kit.digest(target.read_bytes()) == entry.sha256:
            continue
        edited.setdefault(entry.cli, []).append(str(target))
    return edited


def manifest_clis(run: Run) -> set[str]:
    return {entry.cli for entry in read_manifest(run).values()}


def manifest_files(run: Run) -> tuple[str, ...]:
    return tuple(str(target) for target in read_manifest(run))


def read_manifest(run: Run) -> dict[Path, kit.Entry]:
    path = manifest_path(run)
    try:
        return kit.load_manifest(path)
    except (OSError, ValueError):
        return {}
    except (KeyError, TypeError) as broken:
        raise RuntimeError(
            run.t("participant.manifest_unreadable", manifest=KIT_MANIFEST, path=path)
        ) from broken


def clis_using_package(remaining: set[str], removal: Removal) -> set[str]:
    if not remaining or not removal.uninstalled:
        return remaining
    return remaining - set(removal.asked)


def flagged_clis(run: Run) -> set[str]:
    given = run.plan.answers.get(ROLE, {})
    return {
        cli
        for cli, dest in zip(kit.CLIS, (CLAUDE_DEST, OPENCODE_DEST))
        if given.get(dest)
    }


def wanted_clis(run: Run) -> tuple[str, ...]:
    picked = flagged_clis(run)
    installed = manifest_clis(run)
    if not picked and not installed:
        picked = set(asked_clis(run) if run.boundaries.stdin.isatty() else kit.CLIS)
    return tuple(cli for cli in kit.CLIS if cli in picked | installed)


def removal_clis(run: Run) -> tuple[str, ...]:
    picked = flagged_clis(run)
    if not picked:
        picked = manifest_clis(run) or set(kit.CLIS)
    return tuple(cli for cli in kit.CLIS if cli in picked)


def asked_clis(run: Run) -> tuple[str, ...]:
    both = run.t("participant.choice_both")
    choices = (*kit.CLIS, both)
    listing = "\n".join(
        f"    {number + 1}. {name}" for number, name in enumerate(choices)
    )
    run.say(run.t("participant.ask_clis", listing=listing))
    answer = run.boundaries.stdin.readline().strip()
    if answer.isdigit() and 1 <= int(answer) <= len(choices):
        answer = choices[int(answer) - 1]
    if answer in (both, "both"):
        return kit.CLIS
    if answer in kit.CLIS:
        return (answer,)
    raise UsageError(run.t("participant.cli_choice_unclear", answer=answer))


def cli_flags(clis: Sequence[str]) -> list[str]:
    return [f"--{cli}" for cli in clis]


def kit_report(run: Run, result, command: str) -> kit.Report:
    report = kit.Report.read(result.stdout or "", command)
    if report is None:
        raise RuntimeError(kit_failure(run, result, command))
    return report


def kit_failure(run: Run, result, command: str) -> str:
    report = kit.Report.read(result.stdout or "", command)
    if report is not None and report.code == kit.CODE_CONFLICT:
        return run.t(
            "participant.kit_conflict",
            detail=" ".join(
                [
                    run.t(
                        "participant.kit_conflict_files",
                        files=", ".join(str(step.target) for step in report.refused),
                    ),
                    run.t("participant.kit_conflict_force"),
                ]
            ),
        )
    detail = (result.stderr or result.stdout or "").strip()
    return run.t("participant.kit_failed", detail=detail)


def broker_url(run: Run) -> str:
    given = run.plan.answers.get(ROLE, {}).get(URL_DEST) or DEFAULT_BROKER
    return str(given).rstrip("/")


def env_lines(run: Run) -> list[str]:
    url = broker_url(run)
    if url == DEFAULT_BROKER:
        return []
    if run.boundaries.platform == WINDOWS:
        command = f'setx AGENTSCHAT_URL "{url}"'
    else:
        line = f"export AGENTSCHAT_URL={shlex.quote(url)}"
        command = f"printf '%s\\n' {shlex.quote(line)} >> ~/.profile"
    return [run.t("participant.set_url_permanently", command=command)]


def path_lines(run: Run) -> list[str]:
    if found_on_path(run) is not None:
        return []
    return [run.t("participant.path_missing", command=resolved_tool(run).path_command)]


def answered(run: Run) -> bool:
    return run.boundaries.probe(f"{broker_url(run)}/status").error is None


def broker_refusal(run: Run, error: str | None) -> str:
    lines = [
        run.t("participant.broker_silent", url=broker_url(run), error=error),
        *env_lines(run),
        *path_lines(run),
        run.t("participant.broker_retry"),
    ]
    return " ".join(lines)


def tool_instruction(run: Run) -> str:
    if run.boundaries.platform == WINDOWS:
        return run.t("participant.tool_missing_windows")
    return run.t("participant.tool_missing_linux")


def report(run: Run, removal: Removal, kit: KitInstallStep) -> None:
    if not run.plan.remove:
        _reported_installed(run, kit)
        return
    lines = removal_lines(run, removal)
    if run.plan.purge:
        lines += purge_lines(run)
    for line in lines:
        run.say(line)


def _reported_installed(run: Run, kit: KitInstallStep) -> None:
    for cli, files in sorted(stale_files(run).items()):
        run.say(run.t("participant.kit_edited_kept", cli=cli, files=", ".join(files)))
    for line in env_lines(run):
        run.say(line)
    for line in path_lines(run):
        run.say(line)
    run.say(run.t("participant.broker_answers", url=broker_url(run)))
    run.say(
        f"{restart_instruction(run, kit.written, kit.clis)} "
        f"{run.t('participant.chatlogin_next')}"
    )


def restart_instruction(run: Run, written: bool, clis: Sequence[str]) -> str:
    if not written:
        return run.t("participant.restart_unchanged")
    names = [kit.CLI_NAMES[cli] for cli in kit.CLIS if cli in clis]
    if len(names) == 1:
        return run.t("participant.restart_one", name=names[0])
    first, second = names
    return run.t("participant.restart_two", first=first, second=second)


def removal_lines(run: Run, removal: Removal) -> list[str]:
    remaining = manifest_clis(run)
    left = kit_left(run, remaining, removal)
    using = clis_using_package(remaining, removal)
    tool = owning_tool(run)
    if tool is not None:
        left.append(
            Left(
                package_in_use(run, using)
                if using
                else run.t("participant.package_left", package=PACKAGE, tool=tool.name)
            )
        )
    lines = (
        [run.t("participant.left_heading"), *left_lines(left)]
        if left
        else [run.t("participant.all_removed")]
    )
    lines += _missing_binary_lines(run, left, removal)
    if not run.plan.purge:
        lines.append(_session_files_line(run))
    entry = INSTALL_ENTRY.get(run.boundaries.platform, "install.sh")
    lines.append(run.t("participant.reinstall_hint", entry=entry))
    return lines


def _session_files_line(run: Run) -> str:
    key = (
        "participant.session_files_kept_reinstall"
        if owning_tool(run) is None
        else "participant.session_files_kept_relogin"
    )
    return run.t(key, store=STORE)


def kit_left(run: Run, remaining: set[str], removal: Removal) -> list[Left]:
    if not remaining:
        return []
    if not removal.uninstalled:
        return [Left(run.t("participant.left_kit_not_removed"), manifest_files(run))]
    asked = set(removal.asked)
    edited = stale_files(run)
    return [
        *(
            Left(run.t("participant.left_kit_not_asked", cli=cli))
            for cli in sorted(remaining - asked)
        ),
        *(
            Left(
                run.t("participant.left_kit_edited", cli=cli),
                tuple(edited.get(cli, [])),
            )
            for cli in sorted(remaining & asked)
        ),
    ]


def _missing_binary_lines(
    run: Run, left: Sequence[Left], removal: Removal
) -> list[str]:
    if not removal.package_gone or not any(item.files for item in left):
        return []
    return [run.t("participant.kit_files_orphaned")]


def purge_lines(run: Run) -> list[str]:
    directory = store(run)
    lines = [run.t("participant.sessions_deleted", directory=directory)]
    lines += _manifest_kept_lines(run)
    kept = kept_files(directory)
    lines += [
        *(run.t("participant.kept_not_session", path=path) for path in kept),
        *([] if kept else [run.t("participant.no_other_files")]),
    ]
    return lines


def _manifest_kept_lines(run: Run) -> list[str]:
    if not manifest_path(run).is_file():
        return []
    if not manifest_clis(run):
        return [run.t("participant.manifest_empty", manifest=KIT_MANIFEST)]
    key = (
        "participant.manifest_kept_manual"
        if owning_tool(run) is None
        else "participant.manifest_kept_auto"
    )
    return [run.t(key, manifest=KIT_MANIFEST)]
