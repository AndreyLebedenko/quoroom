# Task english-release-04: Send, inbox, status and room notices in the room language

**Status:** Planned.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-03 (the error helper and the catalogue).
**Estimate:** 3 hours.

## Summary

The broker's remaining answers (`say`, `inbox`, `status`) and the notices it
posts into the Matrix room use the broker catalogue and the error contract of
task 03. The status of a session becomes a code (`listening`, `processing`,
`not_listening`) with its text rendered separately.

## Why

A human watching Element sees the broker's depth-limit and rate-limit notices,
so they must be in the room language. `status` returns a Russian word that is
both the state and its text, and tests match the text.

## Context you need

- `broker.py`: `Registration.state` (returns the Russian word), `handle_say`
  (empty message, depth limit, rate limit, no addressee, no connected agent),
  `handle_status`, the depth-limit notice posted to the room, the literals
  between about lines 575 and 650.
- `bridge/tests/test_sessionchat.py`: assertions on the not-listening text and
  on the slot advice that quotes the state.
- `client.py` `do_status` prints the broker's text raw.

## Boundary

- `broker.py` (those handlers, `Registration.state`, and the places `advice`
  uses the state), `broker_messages/*.json`, `client.py` `do_status` (reads the
  new fields), tests.
- The envelope text for agents is task 06; startup and logs are task 05.

## Requirements

- `Registration.state()` returns a code; the sentence that names the state is
  rendered from the catalogue and is, under `ru`, the same Russian words as now.
- `/status` returns per session `state` (code) and the rendered line; the client
  shows the rendered line and may use `state`.
- Notices posted into the room (depth limit reached, rate limit) are in the room
  language. Codes go only into HTTP answers, never into the Matrix body.
- A `say` that succeeds with a warning (published but no agent received it) also
  carries a code. The exact shape is stated in the report.

## Tests

- A table over every `say` outcome and every status state, both languages.
- The depth-limit notice posted to a fake room is in the configured language.
- Existing tests unchanged.

## Acceptance criteria

- [ ] No Cyrillic literal in `handle_say`, `handle_status`, `Registration.state`.
- [ ] `state` is a code in the JSON; the Russian state words appear only in
      `ru.json`.
- [ ] Room notices follow the room language.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
