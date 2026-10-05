# Task english-release-08: login, logout, status - localised, with a machine-readable result

**Status:** Planned.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-07.
**Estimate:** 3 hours.

## Summary

`agentschat login`, `logout` and `status` print their sentences from the client
catalogue in the room language, and each ends with one language-independent
result line that other programs can read. The help text of these subcommands is
catalogued.

## Why

The OpenCode plugin learns that a session logged in or out by looking for two
Russian phrases in the output of the CLI (`plugins/agentschat.js`,
`tool.execute.after`). That cannot survive a second language. The client cannot
be asked to keep a phrase stable; it can be asked to print a result line whose
shape is the contract.

## Context you need

- `client.py`: `do_login` (the success texts for a listener session, for a
  plugin session and for a reconnect; the instruction to start the listener
  in the background), `do_logout`, `do_status`, the parser entries for these
  subcommands.
- `kit/opencode/plugins/agentschat.js`: how it detects login and logout; it
  sees the whole text the CLI printed, not the exit code (task 12 changes it).
- Broker answers from tasks 03 and 04 carry `code`, `message` and `state`.

## Design to settle (AGENTS.md 0.4)

1. **The result line.** The plugin cannot add a flag to the command the agent
   runs, so the result is a last line of the default output. Recommended:
   `AGENTSCHAT-RESULT {"command":"login","ok":true,"agent":"<name>","session":"<id>"}`
   - one line, JSON after a fixed ASCII prefix, printed in every language; `ok`
   false carries `"code"` from the broker's refusal. Say in the report why a
   dedicated line beats a `--json` mode here.
2. **Where each sentence comes from.** A refusal comes from the broker (already
   rendered); success and the "start the listener" instruction are composed by
   the client from its catalogue, with variants (listener, plugin, reconnect)
   chosen in code.

## Boundary

- `client.py` for login, logout, status and their parser help;
  `client_messages/*.json`; tests. The result-line format is documented in
  `docs/AGENTS_INTEGRATION.md` only in task 19.
- `wait`, `inbox`, `say`, `ask` are task 09; `install` / `uninstall` are task 11.

## Requirements

- The Russian sentences are what the client printed before, character for
  character; the result line is added after them.
- The result line is printed exactly once per command, also on a refusal, and
  never contains a token.
- Exit codes are unchanged.

## Tests

- Table: each login variant, logout, status, a broker refusal, an unreachable
  broker, under both languages: the sentence, the result line, the exit code.
- A parser test that reads the result line and ignores the sentence (it replaces
  the sentence with other words and still gets the same result).
- No Cyrillic in any `en` output of these commands.

## Acceptance criteria

- [ ] `login` and `logout` print the result line in both languages.
- [ ] The prose of the three commands is catalogued; none remains in `client.py`.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
