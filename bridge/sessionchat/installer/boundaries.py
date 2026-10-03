import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

PROBE_TIMEOUT = 5.0
WINDOWS = "windows"
LINUX = "linux"


@dataclass(frozen=True)
class Probe:
    status: int | None
    error: str | None


@dataclass(frozen=True)
class Boundaries:
    repo: Path
    home: Path
    env: Mapping[str, str]
    stdin: IO[str]
    stdout: IO[str]
    stderr: IO[str]
    run: Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]
    probe: Callable[[str], Probe]
    platform: str

    @classmethod
    def real(cls) -> "Boundaries":
        return cls(
            repo=repository_root(),
            home=Path.home(),
            env=os.environ,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
            run=run_command,
            probe=answers,
            platform=platform_name(),
        )


def repository_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def platform_name() -> str:
    return WINDOWS if sys.platform.startswith("win") else LINUX


def run_command(argv: Sequence[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(list(argv), capture_output=True, text=True, check=False)


def answers(url: str, timeout: float = PROBE_TIMEOUT) -> Probe:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as response:
            return Probe(response.status, None)
    except urllib.error.HTTPError as error:
        return Probe(error.code, None)
    except urllib.error.URLError as error:
        return Probe(None, describe(error))
    except OSError as error:
        return Probe(None, describe(error))


def describe(error: BaseException) -> str:
    reason = getattr(error, "reason", error)
    if isinstance(reason, ssl.SSLCertVerificationError):
        message = getattr(reason, "verify_message", None) or str(reason)
        return f"сертификат не подтверждён: {message}"
    return str(reason)
