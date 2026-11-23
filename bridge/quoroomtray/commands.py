import argparse
from collections.abc import Callable, Sequence
from enum import Enum

from .autostart import Autostart, AutostartOutcome
from .texts import TrayTexts

FAILURE_EXIT_CODE = 1


class TrayCommand(Enum):
    RUN = "run"
    INSTALL_AUTOSTART = "install_autostart"
    REMOVE_AUTOSTART = "remove_autostart"


def parse_command(argv: Sequence[str] | None = None) -> TrayCommand:
    parser = argparse.ArgumentParser(prog="python -m quoroomtray")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument(
        "--install-autostart",
        dest="command",
        action="store_const",
        const=TrayCommand.INSTALL_AUTOSTART,
        help="start the tray when the user logs in to Windows",
    )
    choice.add_argument(
        "--remove-autostart",
        dest="command",
        action="store_const",
        const=TrayCommand.REMOVE_AUTOSTART,
        help="stop starting the tray when the user logs in to Windows",
    )
    return parser.parse_args(argv).command or TrayCommand.RUN


OUTCOME_KEYS = {
    AutostartOutcome.INSTALLED: "autostart.installed",
    AutostartOutcome.REMOVED: "autostart.removed",
    AutostartOutcome.NOT_INSTALLED: "autostart.not_installed",
    AutostartOutcome.TARGET_MISSING: "autostart.target_missing",
}
SUCCESSFUL_OUTCOMES = frozenset(
    {
        AutostartOutcome.INSTALLED,
        AutostartOutcome.REMOVED,
        AutostartOutcome.NOT_INSTALLED,
    }
)


def run_autostart_command(
    command: TrayCommand,
    autostart: Autostart,
    texts: TrayTexts,
    echo: Callable[[str], object],
) -> int:
    try:
        if command is TrayCommand.INSTALL_AUTOSTART:
            outcome = autostart.install()
        else:
            outcome = autostart.remove()
    except OSError as failure:
        echo(texts.text("autostart.failed", detail=failure))
        return FAILURE_EXIT_CODE
    shortcut = autostart.shortcut
    echo(
        texts.text(
            OUTCOME_KEYS[outcome], shortcut=shortcut.path, target=shortcut.target
        )
    )
    return 0 if outcome in SUCCESSFUL_OUTCOMES else FAILURE_EXIT_CODE
