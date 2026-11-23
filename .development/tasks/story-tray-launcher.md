# Story: Windows tray launcher for the stand

**Status:** Agreed with the owner on 2026-11-23, including Q1. No task
started.

## User-facing goal

The owner runs the stand on one Windows machine and wants to see and control
it without a PowerShell window. A tray icon shows the state of the stand by
colour, opens Element with a left click, and offers status, the connected
sessions and Start/Stop on a right click. The icon starts with Windows.

Single user: no exe, no code signing, no PyInstaller. The tray runs under
`bridge/.venv/Scripts/pythonw.exe`, started by a shortcut.

## UX contract

- **Icon colour** (the menu cannot carry colour - `pystray` menu items are
  text only, so colour lives on the icon):
  - grey - stopped on purpose: neither the stack nor the broker answers;
  - yellow - a Start or Stop the tray launched is still running;
  - green - port 443 answers and broker `GET /status` answers;
  - red - broken: exactly one of the two answers, or the last Start/Stop the
    tray launched exited with an error.
- **Tooltip:** the state in words; for red, the reason.
- **Left click** (the `default=True` menu item):
  - green - open `https://agentschat.local/` in the default browser;
  - any other state - a system notification "the stand is not running",
    nothing opens.
- **Right click** menu, top to bottom:
  - status line (text), for red with the reason;
  - one line per session from `/status` (the broker's own `line` field);
  - Start or Stop - one item, label by state; disabled while yellow.
    Start runs `start.ps1`; Stop runs the full `stop.ps1` (broker stopped,
    containers down, Docker Desktop left running);
  - Open log (`bridge/broker.log`);
  - Exit - closes the tray only; the stand keeps running.
- **Language:** `language` from `bridge/config.yaml`, as the scripts do;
  anything other than `ru` gives English.
- **Polling:** every 5 seconds.

## How it fits the existing architecture

The scripts stay the single source of truth for starting and stopping. The
tray launches them hidden and reads only their exit code and last output
line. The tray never owns the broker process, so the broker is still stopped
with `Stop-Process -Force` by `stop.ps1`; graceful broker shutdown is out of
scope.

State is read from facts, not from what the tray remembers: port 443
(Caddy) and `GET /status` on the broker (no token needed; it returns
`language` and `sessions[]` with `agent`, `state`, `line`). This keeps the
icon right when the stand was started or stopped from a console.

The tray code is a separate top-level package `bridge/quoroomtray/`, outside
the `sessionchat` package that participants install, so `pystray` and
`Pillow` never reach a participant's machine. They go to
`bridge/requirements-tray.txt`, not `requirements.txt`.

## Decisions

- **Q1: what the tray does at login.** Decided 2026-11-23 by the owner:
  option (a). The containers
  have `restart: unless-stopped`. If Windows shut down without `stop.ps1`
  and Docker Desktop starts with Windows, the containers come back by
  themselves but the broker does not - by the colour rules above the icon is
  red right after every such login. Options:
  a. at login, if 443 answers and the broker does not, run `start.ps1`
     (it is idempotent and only adds the broker);
  b. at login always run `start.ps1`;
  c. never start anything; red is the truth, the owner presses Start.
  Chosen: (a) - it repairs exactly the half-state, and a stand stopped on
  purpose stays stopped. Refined 2026-11-23 by the owner after task 04
  found that, after a reboot, the tray starts before Docker Desktop brings
  the containers back, so a single observation at tray start sees grey and
  the half-state appears later with nothing to repair it. The rule is
  therefore armed for the first 5 minutes after the tray starts: grey
  observations keep it armed; the half-state seen on two consecutive polls
  runs `start.ps1` once and disarms it; any other observation, any Start or
  Stop already running, or the end of the 5 minutes disarms it without
  acting. It fires at most once per tray start, so a broker the owner stops
  or that crashes later shows red instead of being restarted silently. The
  tray cannot tell a Windows login from a manual start, so the same applies
  when the owner starts the tray by hand.

## Boundaries

- No broker changes, no client-contract changes.
- Scripts change only in task 01 (Docker Desktop autostart).
- Browser: the default browser only. Choosing Chrome explicitly may come
  later; it is not in this story.
- Nothing in the automated suite needs Docker, a tray or a real broker: the
  probes, the state rules and the script runner are tested with `unittest`
  behind injectable seams; the `pystray` layer is a thin shell over them.

## Task sequence

1. `task-tray-01-docker-autostart.md` - `start.ps1` starts Docker Desktop
   when the daemon does not answer and waits for it.
2. `task-tray-02-state-model.md` - probes, state rules, menu model, script
   runner, language; unittest.
3. `task-tray-03-tray-ui.md` - the `pystray` shell: icon images, menu,
   left click, notifications, Exit; `requirements-tray.txt`.
4. `task-tray-04-autostart-and-docs.md` - start with Windows, login
   behaviour per Q1, READMEs, `docs/ARCHITECTURE.md`, manual handoff in
   `docs/VERIFICATION.md`.

## Acceptance criteria

- [ ] With Docker Desktop not running, Start brings up Docker Desktop, the
      stack and the broker; the icon goes yellow, then green.
- [ ] Stop leaves Docker Desktop running; the icon goes yellow, then grey.
- [ ] Left click on green opens Element in the default browser; on any other
      state it shows the notification and opens nothing.
- [ ] The menu lists the sessions `/status` reports.
- [ ] Killing the broker by hand turns the icon red with a reason.
- [ ] The icon starts with Windows and behaves at login as Q1 decides.
- [ ] `unittest`, `ruff check` and `ruff format --check` are green; the
      manual handoff is prepared and its result recorded in
      `docs/VERIFICATION.md` once the owner runs it.
