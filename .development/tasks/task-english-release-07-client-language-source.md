# Task english-release-07: How the client knows the room language

**Status:** Planned.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-02 (the broker reports `language`).
**Estimate:** 2 hours.

## Summary

The client (`agentschat`) learns the room language from the broker, remembers it
in a small file for the moments when the broker cannot be reached, and exposes
one function that every later client message goes through. This task adds the
mechanism and an empty client catalogue; tasks 08, 09 and 11 fill it.

## Why

Most text the client prints when the broker answers can be taken from the
broker's answer (it already speaks in the room language, tasks 03-06). What the
client says by itself - the broker is unreachable, there is no stored token, a
usage error, `install` - has no broker to ask. If the client guessed, it would
flip between languages inside one session. A remembered value, refreshed on
every successful answer, removes the guess.

## Context you need

- `bridge/sessionchat/client.py`: `base()`, `credentials()`, `fail()`,
  `explain()`; the client stores per-agent credentials in `~/.agentschat/`.
- `/status` and the other broker answers carry `language` after task 02.
- Task 11 adds a `--lang` flag to `install` and `uninstall`; this task defines how
  an explicit flag, the remembered value and the default combine.

## Design to settle (AGENTS.md 0.4)

1. **Which broker answers refresh the value.** Recommended: every JSON answer
   that carries `language` (login, wait, say, status); the write is skipped when
   the value is unchanged.
2. **Precedence.** Recommended: explicit `--lang` > the broker's answer in this
   run > the remembered value > `en`.
3. **Where it is stored.** Recommended: a plain file `~/.agentschat/language`
   (not secret, not per agent), written atomically. A per-agent value would
   disagree with itself on one machine that serves two rooms; say in the report
   how two brokers on one machine behave (the last answered wins) and that it is
   accepted.

## Boundary

- `client.py` (language resolution and storage), `bridge/sessionchat/client_messages/{en,ru}.json`
  (created empty-of-meaning: only a key or two used by this task's tests),
  `bridge/pyproject.toml` package-data, tests.
- Nothing outside `~/.agentschat/` is written, and tests never touch the real home.

## Requirements

- One function `speak(key, **params)` in the client renders a catalogue sentence
  in the resolved language; tasks 08, 09 and 11 use it and no other path.
- An unreadable or invalid remembered value is ignored (English), never an error.
- `fail()` goes through `speak`.

## Tests

- Precedence table over the four sources; a broker answer refreshes the file; an
  unchanged answer does not rewrite it; a corrupt file falls back to English.
- The home directory is redirected in every test.

## Acceptance criteria

- [ ] With no broker and no remembered value the client speaks English.
- [ ] After one successful answer under `ru`, an unreachable-broker message is
      Russian.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
