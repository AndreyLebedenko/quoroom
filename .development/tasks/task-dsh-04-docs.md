# Task: DSH participant docs and verification handoff

Status: In review. Docs written; manual handoff (VERIFICATION.md, scenario 3)
pending the human. `unittest discover`: one error, `test_installer_boundaries`
(Windows argv encoding), identical to master and outside this branch.
Story: story-dsh-participant.md
Branch: feat/dsh-participant

## Summary

Documentation for the DSH participant, in the same commit as the final state
of the story:

- `docs/SESSION_BRIDGE.md`: the DSH participant architecture (delivery mode
  `plugin`, the cordis plugin as in-process listener, `/chatlogin`
  + `/chatlogout` commands, `agent.followup` delivery, `agent/disposed`
  logout), updated in the same commit as the architectural change.
- `README.md` / `README.ru.md`: the DSH participant appears next to Claude
  Code and OpenCode, with the one-time machine setup and the per-session
  join command.
- `bridge/config.example.yaml`: the `deepseek` participant entry with
  `delivery: plugin` and a placeholder Matrix account.
- `docs/VERIFICATION.md`: the manual handoff (start the Docker stack, install
  the client and the DSH kit, open a DSH session, `/chatlogin deepseek`,
  send a message from the room, observe the envelope; `/chatlogout`), and
  the live findings once the human runs it.

## Boundary

- `docs/SESSION_BRIDGE.md`, `README.md`, `README.ru.md`,
  `bridge/config.example.yaml`, `docs/VERIFICATION.md`
- No code changes.

## Acceptance criteria

- `docs/SESSION_BRIDGE.md` states who consumes each mechanism and when it
  runs, and what breaks without it.
- The manual handoff is explicit: what to run, what to look for.
- `unittest discover` and `ruff check` / `ruff format --check` pass.
