import os
import webbrowser

from . import settings
from .app import run_tray
from .autostart import Autostart, stand_shortcut
from .commands import TrayCommand, parse_command, run_autostart_command
from .errorlog import ErrorLog
from .guard import exit_code_after_reporting
from .language import tray_language
from .named_mutex import claim_named_mutex
from .probes import StandProbes
from .shell_settings import ERROR_LOG, INSTANCE_MUTEX_NAME
from .shortcut_writer import write_shortcut_with_powershell
from .texts import TrayTexts


def run_stand_tray() -> int:
    from .shell.pystray_shell import PystrayShell

    return run_tray(
        lambda: claim_named_mutex(INSTANCE_MUTEX_NAME),
        PystrayShell,
        StandProbes().observe,
        TrayTexts(tray_language(settings.CONFIG_FILE)),
        webbrowser.open,
        os.startfile,
        ErrorLog(ERROR_LOG),
    )


def stand_autostart() -> Autostart:
    return Autostart(stand_shortcut(os.environ), write_shortcut_with_powershell)


def main(argv: list[str] | None = None) -> int:
    command = parse_command(argv)
    if command is TrayCommand.RUN:
        return exit_code_after_reporting(run_stand_tray, ErrorLog(ERROR_LOG))
    return run_autostart_command(
        command,
        stand_autostart(),
        TrayTexts(tray_language(settings.CONFIG_FILE)),
        print,
    )


if __name__ == "__main__":
    raise SystemExit(main())
