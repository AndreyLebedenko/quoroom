# Task: start the tray with Windows, docs and manual handoff

Status: Not started
Story: story-tray-launcher.md

## Summary

- A command that creates or removes a shortcut in the user's Startup folder
  (`shell:startup`) pointing at `bridge/.venv/Scripts/pythonw.exe -m
  quoroomtray` with `bridge/` as working directory. Shape of the command
  (a tray flag or a small PowerShell script) is decided in this task.
- At start-up the tray applies the login rule from task 02 (story Q1,
  option (a)) once. `run_tray` has no hook for it yet (task 03 report); add
  one rather than calling it from `__main__.py` untested.
- A failure before the icon exists (for example `requirements-tray.txt`
  not installed, so importing pystray fails) must leave a trace: today
  `main()` is outside every guard and, under `pythonw` started from the
  Startup folder, the tray simply never appears (task 03 review,
  2026-11-23). Write it to the tray error log and exit non-zero, with a
  test.
- Bound `bridge/state/tray-errors.log` (a persistent error in the poll loop
  appends a traceback every 5 s), or record why it is not needed.
- Docs: `README.md` and `README.ru.md` (Start and stop section: the tray,
  installing `requirements-tray.txt`, the autostart command; the Docker
  Desktop autostart from task 01), `docs/ARCHITECTURE.md` (the tray as a
  part: reads facts, runs the scripts, never owns the broker), `docs/INSTALL.md`
  and `docs/INSTALL.en.md` if they describe starting the stand.
- `docs/VERIFICATION.md`: the manual handoff - what to run and what to look
  for, covering every acceptance criterion of the story that needs Docker or
  a real tray, including a reboot with and without `stop.ps1` before it.

## Boundary

- Shortcut creation and removal, the login rule, the docs listed above.
- `docs/SESSION_BRIDGE.md` only if the owner judges the tray an
  architectural decision; it does not change the broker or the session
  contract.

## Acceptance criteria

- Shortcut create/remove is tested against a temporary folder.
- A test pins that the login rule runs once at start-up and not on polls.
- READMEs stay in step.
- `unittest`, `ruff check`, `ruff format --check` green; the handoff is
  prepared.
