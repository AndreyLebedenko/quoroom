from __future__ import annotations

import getpass
import os
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import IO, Protocol

from .catalogue import DEFAULT_LANGUAGE, text

PROBE_TIMEOUT = 5.0
WINDOWS = "windows"
LINUX = "linux"


class Runner(Protocol):
    def __call__(
        self,
        argv: Sequence[str],
        stdin: str | None = ...,
        output: Path | None = ...,
        env: Mapping[str, str] | None = ...,
    ) -> "subprocess.CompletedProcess[str]": ...


class Resolver(Protocol):
    def __call__(self, name: str) -> Sequence[str]: ...


class SecretReader(Protocol):
    def __call__(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class Probe:
    status: int | None
    error: str | None
    untrusted: bool = False


@dataclass(frozen=True)
class Boundaries:
    repo: Path
    home: Path
    env: Mapping[str, str]
    stdin: IO[str]
    stdout: IO[str]
    stderr: IO[str]
    run: Runner
    probe: Callable[[str], Probe]
    platform: str
    resolve: Resolver
    secret: SecretReader
    lang: str

    @classmethod
    def real(cls, lang: str = DEFAULT_LANGUAGE) -> "Boundaries":
        return cls(
            repo=repository_root(),
            home=Path.home(),
            env=os.environ,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
            run=run_command,
            probe=partial(answers, lang=lang),
            platform=platform_name(),
            resolve=resolved,
            secret=partial(ask_secret, lang=lang),
            lang=lang,
        )


def repository_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def platform_name() -> str:
    return WINDOWS if sys.platform.startswith("win") else LINUX


def run_command(
    argv: Sequence[str],
    stdin: str | None = None,
    output: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> "subprocess.CompletedProcess[str]":
    sink = None
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        sink = output.open("w", encoding="utf-8", errors="replace")
    try:
        done = subprocess.run(
            list(argv),
            input=stdin,
            stdin=None if stdin is not None else subprocess.DEVNULL,
            stdout=sink if sink is not None else subprocess.PIPE,
            stderr=subprocess.STDOUT if sink is not None else subprocess.PIPE,
            text=True,
            check=False,
            env=None if env is None else {**os.environ, **env},
        )
    finally:
        if sink is not None:
            sink.close()
    if output is None:
        return done
    return subprocess.CompletedProcess(
        done.args,
        done.returncode,
        output.read_text(encoding="utf-8", errors="replace"),
        "",
    )


def resolved(name: str) -> tuple[str, ...]:
    try:
        found = socket.getaddrinfo(name, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return ()
    return tuple(dict.fromkeys(item[4][0] for item in found))


def ask_secret(prompt: str, lang: str = DEFAULT_LANGUAGE) -> str:
    typed = getpass.getpass(prompt)
    if typed != getpass.getpass(text(lang, "boundaries.repeat_password")):
        raise ValueError(text(lang, "boundaries.password_mismatch"))
    return typed


def answers(
    url: str, timeout: float = PROBE_TIMEOUT, lang: str = DEFAULT_LANGUAGE
) -> Probe:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as response:
            return Probe(response.status, None)
    except urllib.error.HTTPError as error:
        return Probe(error.code, None)
    except urllib.error.URLError as error:
        return Probe(None, describe(error, lang), certificate_refused(error))
    except OSError as error:
        return Probe(None, describe(error, lang), certificate_refused(error))


def describe(error: BaseException, lang: str) -> str:
    reason = getattr(error, "reason", error)
    if isinstance(reason, ssl.SSLCertVerificationError):
        message = getattr(reason, "verify_message", None) or str(reason)
        return text(lang, "boundaries.certificate_unverified", message=message)
    return str(reason)


def certificate_refused(error: BaseException) -> bool:
    return isinstance(getattr(error, "reason", error), ssl.SSLCertVerificationError)
