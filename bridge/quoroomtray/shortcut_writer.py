import os
import subprocess
from collections.abc import Callable, Mapping

from .autostart import Shortcut
from .process import CREATE_NO_WINDOW, console_encoding

LINK_PATH = "QUOROOM_LINK_PATH"
LINK_TARGET = "QUOROOM_LINK_TARGET"
LINK_ARGUMENTS = "QUOROOM_LINK_ARGUMENTS"
LINK_WORKING_DIRECTORY = "QUOROOM_LINK_WORKING_DIRECTORY"
LINK_DESCRIPTION = "QUOROOM_LINK_DESCRIPTION"

WRITE_SHORTCUT_SCRIPT = (
    "$ErrorActionPreference = 'Stop'; "
    f"$link = (New-Object -ComObject WScript.Shell).CreateShortcut($env:{LINK_PATH}); "
    f"$link.TargetPath = $env:{LINK_TARGET}; "
    f"$link.Arguments = $env:{LINK_ARGUMENTS}; "
    f"$link.WorkingDirectory = $env:{LINK_WORKING_DIRECTORY}; "
    f"$link.Description = $env:{LINK_DESCRIPTION}; "
    "$link.Save()"
)


class ShortcutWriteError(OSError):
    pass


def shortcut_environment(shortcut: Shortcut, base: Mapping[str, str]) -> dict[str, str]:
    return {
        **base,
        LINK_PATH: str(shortcut.path),
        LINK_TARGET: str(shortcut.target),
        LINK_ARGUMENTS: shortcut.arguments,
        LINK_WORKING_DIRECTORY: str(shortcut.working_directory),
        LINK_DESCRIPTION: shortcut.description,
    }


def write_shortcut_with_powershell(
    shortcut: Shortcut,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    base_environment: Mapping[str, str] | None = None,
) -> None:
    completed = run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            WRITE_SHORTCUT_SCRIPT,
        ],
        env=shortcut_environment(
            shortcut, os.environ if base_environment is None else base_environment
        ),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stdout.decode(console_encoding(), errors="replace").strip()
        raise ShortcutWriteError(
            f"PowerShell exited with {completed.returncode}: {detail}"
        )
