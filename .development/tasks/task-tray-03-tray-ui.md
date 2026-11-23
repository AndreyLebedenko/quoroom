# Task: tray icon on pystray

Status: Not started
Story: story-tray-launcher.md

## Summary

A thin `pystray` shell over the task 02 model, started as
`pythonw -m quoroomtray` from `bridge/`:

- Four icon images (grey, yellow, green, red) drawn with `Pillow` at
  start-up; no binary assets in the repo.
- A poll loop every 5 seconds updates the icon, the tooltip and the menu.
- The left-click item (`default=True`) opens the URL with the default
  browser or shows a `pystray` notification, per the model's decision.
- Start/Stop calls the task 02 runner; Open log opens `bridge/broker.log`
  with the default handler; Exit stops the loop and leaves the stand alone.
- A second copy of the tray does not start (a named mutex or a lock file in
  `bridge/state/`).
- `bridge/requirements-tray.txt` with pinned `pystray` and `Pillow`; the
  runtime `requirements.txt` is not touched.

## Boundary

- `bridge/quoroomtray/` UI module, `bridge/requirements-tray.txt`.
- No logic in the UI module that the model could hold: the UI only maps the
  model's data to `pystray` calls.

## Acceptance criteria

- The suite does not import `pystray` (it is not installed in CI); a test
  pins that the model package does not depend on it.
- The single-instance guard is tested without a tray.
- A manual run on this machine: icon appears, colours follow Start/Stop,
  left click and menu behave as the story says. Recorded in task 04's
  handoff.
- `unittest`, `ruff check`, `ruff format --check` green.
