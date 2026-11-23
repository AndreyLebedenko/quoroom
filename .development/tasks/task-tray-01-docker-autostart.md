# Task: start.ps1 starts Docker Desktop itself

Status: Not started
Story: story-tray-launcher.md

## Summary

Today `start.ps1` exits with `docker_down` when the Docker daemon does not
answer. The tray's Start runs `start.ps1`, so with Docker Desktop not running
Start would always fail. After this task `start.ps1` starts Docker Desktop
and waits for the daemon before bringing the stack up.

- Daemon answers (`docker info` exit 0) - nothing changes.
- Daemon does not answer - print a progress line (`docker_starting`), run
  `docker desktop start` (the Docker Desktop CLI; it waits until the engine
  is ready). If that subcommand is absent (older Docker Desktop), start
  `Docker Desktop.exe` from `$env:ProgramFiles\Docker\Docker\` and poll
  `docker info` every 2 seconds.
- The engine is not ready within 180 seconds, or Docker Desktop is not
  installed - exit 1 with a message that says which (`docker_down` stays the
  message for "did not come up"; a new key for "Docker Desktop not found").
- `docker` not in PATH stays `docker_missing`, unchanged.

New messages go into both the English and the Russian table.

## Boundary

- `start.ps1`, `bridge/tests/test_launch_scripts.py`.
- `stop.ps1` unchanged: it already leaves Docker Desktop running.
- `start.sh` unchanged: the story is Windows only.
- Docs are updated in task 04.

## Acceptance criteria

- Tests, using the existing fake `docker` in the caller script, cover: daemon
  up - no start attempt; daemon down then up after `docker desktop start` -
  the stack is brought up; `docker desktop` subcommand absent - the exe
  fallback is used; never ready - exit 1 with the message; Docker Desktop
  not installed - exit 1 with its own message; every new message in ru and
  en.
- The existing script-text tests still pass (BOM, PowerShell 5.1 constructs,
  no Cyrillic outside the Russian table, comments only in the help).
- `unittest`, `ruff check`, `ruff format --check` green.
