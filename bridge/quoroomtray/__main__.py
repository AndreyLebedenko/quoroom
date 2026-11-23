import os
import webbrowser

from . import settings
from .app import run_tray
from .errorlog import ErrorLog
from .language import tray_language
from .named_mutex import claim_named_mutex
from .probes import StandProbes
from .shell.pystray_shell import PystrayShell
from .shell_settings import ERROR_LOG, INSTANCE_MUTEX_NAME
from .texts import TrayTexts


def main() -> int:
    return run_tray(
        lambda: claim_named_mutex(INSTANCE_MUTEX_NAME),
        PystrayShell,
        StandProbes().observe,
        TrayTexts(tray_language(settings.CONFIG_FILE)),
        webbrowser.open,
        os.startfile,
        ErrorLog(ERROR_LOG),
    )


if __name__ == "__main__":
    raise SystemExit(main())
