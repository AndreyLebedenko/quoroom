# Task: tray state model, probes and script runner

Status: Completed 2026-11-23. Implemented in `29ddb30`, reviewed by
opencode (accept, mutation-checked). Live checks (hidden PowerShell output
encoding, real start.ps1/stop.ps1 through the runner, the Windows tooltip
limit) are carried by task 04's manual handoff. Non-blocking review notes:
the on_finished guard moved to task 03; StandState invariants hold by
construction and are not pinned by tests.
Story: story-tray-launcher.md

## Summary

Everything the tray decides, without `pystray`, in `bridge/quoroomtray/`:

- **Probes** behind an injectable seam: TCP connect to `127.0.0.1:443`;
  `GET http://127.0.0.1:8770/status` with a short timeout, returning the
  parsed `sessions` or "no answer".
- **State rules**, a pure function of (443 answers, `/status` answers,
  action in progress, last action result) to one of grey / yellow / green /
  red plus a reason for red. The colour contract is in the story card.
  Exactly-one-answers is red; both silent is grey; an action in progress is
  yellow whatever the probes say. A failed last action is red until the
  probes show the state that action aimed at - green after a failed Start,
  grey after a failed Stop - or until a new action starts. This keeps the
  story's rule that state comes from facts: a stand repaired or stopped from
  a console stops being red on the next poll (lead decision, 2026-11-23).
- **Menu model**: the ordered items the UI will draw (status line, session
  lines from the broker's `line` field, Start or Stop with its enabled flag,
  Open log, Exit) as plain data.
- **Left-click decision**: open the Element URL on green, notify otherwise.
- **Script runner**: runs `powershell.exe -NoProfile -ExecutionPolicy Bypass
  -File <script>` hidden (`CREATE_NO_WINDOW`) in a background thread, reports
  exit code and the last non-empty output line. One action at a time.
- **Language**: `language` from `bridge/config.yaml`; `ru` or English. Tray
  strings live in a ru/en table like the broker's messages.
- **Login rule** per story Q1, option (a), as a pure function: 443 answers
  and `/status` does not - run `start.ps1`; any other combination - do
  nothing. Applied once at tray start-up, never on polls.

## Boundary

- New package `bridge/quoroomtray/` (not part of `sessionchat`, not in
  `pyproject.toml` packages) and its tests under `bridge/tests/`.
- No `pystray`/`Pillow` import in this task.
- No changes to the broker or the scripts.

## Acceptance criteria

- Every row of the colour contract has a test named after the situation
  (e.g. "the broker killed while the stack runs is red with a reason").
- The runner is tested with a fake process launcher: success, failure with
  last line as reason, second action refused while one runs.
- The menu model is tested for each state, including Start/Stop label and
  disabled while yellow, and session lines taken verbatim from `/status`.
- `unittest`, `ruff check`, `ruff format --check` green.
