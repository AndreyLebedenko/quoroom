import ctypes
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000


@dataclass(frozen=True)
class ScriptOutcome:
    exit_code: int
    output: str


def powershell_command(script: Path) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
    ]


def last_output_line(output: str) -> str:
    lines = [line.strip() for line in output.splitlines()]
    return next((line for line in reversed(lines) if line), "")


def console_encoding() -> str:
    try:
        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    except (AttributeError, OSError):
        return "utf-8"


def run_powershell_script(
    script: Path,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    encoding: str | None = None,
) -> ScriptOutcome:
    completed = run(
        powershell_command(script),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    output = completed.stdout.decode(encoding or console_encoding(), errors="replace")
    return ScriptOutcome(completed.returncode, output)
