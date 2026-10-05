# Task english-release-12: The OpenCode plugin stops reading sentences

**Status:** Planned.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-08 (the result line).
**Estimate:** 2 hours.

## Summary

The OpenCode plugin recognises a login or a logout by the `AGENTSCHAT-RESULT`
line that task 08 adds, not by two Russian phrases, and its log is English.

## Why

`tool.execute.after` in `plugins/agentschat.js` binds a session when the CLI
output contains one Russian phrase and unbinds it when it contains another. In an
English room neither appears and the plugin never delivers anything. The plugin
also logs in Russian, which makes a log that switches language with the room.

## Context you need

- `bridge/sessionchat/kit/opencode/plugins/agentschat.js`: `tool.execute.after`,
  `note(...)` calls, the other Cyrillic log text.
- `bridge/tests/plugin/agentschat.test.mjs` (`node --test`): how the plugin is
  driven with fake tool events.
- Task 08's result line: `AGENTSCHAT-RESULT {...}` with `command`, `ok`,
  `agent`, `session`.

## Boundary

- The plugin file, its tests, and `docs/` only for a pointer if a document names
  the old detection (the full docs are tasks 18 and 19).
- The plugin has no language-specific parts after this task, so it is the same
  file for every kit language (task 13 relies on that).

## Requirements

- Login: a tool output that contains a result line with `command: login` and
  `ok: true` binds the session of that call to the agent named in the line.
  Logout likewise unbinds. A line with `ok: false` changes nothing.
- The plugin ignores all other text of the output.
- The result line is parsed defensively: malformed JSON is ignored and noted in
  the English log, never thrown.
- Every `note(...)` text is English; none of them is catalogued.
- Behaviour on delivery, polling and slot release is unchanged.

## Tests

- Fake events: login ok, login refused, logout ok, a result line surrounded by
  unrelated text, malformed JSON, and the old Russian phrases alone (must no
  longer bind).
- No Cyrillic anywhere in the plugin file (scan test).

## Acceptance criteria

- [ ] An English login binds a session; the Russian phrases alone do not.
- [ ] The plugin log is English only.
- [ ] `node --test` and the Python suite green; `ruff` clean.

## Note from task 08 (orchestrator, 2026-10-05)

The result line the client prints has no `session` key: the broker has no
session id and the plugin already knows the session of the tool call from the
hook itself. A login line is
`AGENTSCHAT-RESULT {"command":"login","ok":true,"agent":"<name>","mode":"listener|plugin","reconnected":false}`
and a logout line is `{"command":"logout","ok":true,"agent":"<name>"}`; a
refusal carries `"ok":false` and `"code"`. Read the LAST line of the output that
starts with `AGENTSCHAT-RESULT `: sentences before it can contain text the
participant chose (the session label), so an earlier line must never decide.
Read the report of task 08 for the exact format and the code table.
