# Task english-release-22: `agentschat install --lang` remembers the language

**Status:** Planned.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** tasks english-release-07 (client language source) and 11 (kit install).
**Blocks:** closing task english-release-20 (the Russian run expects this behaviour).
**Estimate:** 1-2 hours.

## Summary

When a person runs `agentschat install --lang en|ru`, the client stores that
language in `~/.agentschat/language`, so everything the client says by itself
from then on is in the language the person asked for, before any broker has
answered.

## Why

Owner decision (2026-10-06), recorded in the story log as the open item of task
20. Today the client learns the room language only from a broker answer. On a
participant machine of a Russian room, `agentschat --help` and a first failure
(the broker is unreachable at the first command) are in English until the first
successful `login`. Before the story the client always spoke Russian, so the
criterion "`ru` prints what it printed before" is not met in that window.

The owner chose to let the person say the language explicitly, per install,
rather than have the installer ask the broker: the person may need to state the
language of this machine in this case. The fallback to English when nothing was
ever stated stays; it is the documented default of the story.

## Context you need

- `bridge/sessionchat/client_language.py`: `remember()`, `remembered()`,
  `RoomLanguage` (precedence: explicit `--lang`, the broker's answer in this run,
  the remembered file, `en`).
- `bridge/sessionchat/client.py`: `do_install`, `do_uninstall`, `add_language`,
  `ROOM_LANGUAGE`, `STORE`, `learn_language`.
- `bridge/sessionchat/installer/participant.py`: `language_flags` always passes
  `--lang <installer language>` to `agentschat install`, so the participant
  installer gets this behaviour without a change of its own.
- Task 07 card and report: why the value is a plain, non-secret, machine-wide file
  and what happens with two brokers on one machine (the last answer wins).

## Boundary

- `client.py` (`do_install` only), tests, and the documents that state the old
  behaviour: `CHANGELOG.md` (the "Added" line about `~/.agentschat/language` and
  the upgrade note that says `install` does not write it), `docs/INSTALL.en.md`
  and `docs/INSTALL.md` (section "Room language" / the Russian equivalent, if they
  say how the client learns the language), and the handoff in
  `docs/VERIFICATION.md` (step R1 and the "Выведено из кода" item about the
  client language: the handoff is not a recorded run, so it may be edited; any
  recorded result stays untouched).
- Not in scope: `uninstall` (a `--lang` there only chooses the language of its
  own messages), the broker, the participant installer, the precedence rules, and
  what purge removes.

## Requirements

- `agentschat install --lang <L>` writes `<L>` to `~/.agentschat/language` after
  the kit step succeeded. Not written when `--lang` is absent, when the install
  is refused for a conflict (exit 5 under `--json`, 1 otherwise) or fails, and
  never for `uninstall`.
- An explicit `--lang` overwrites a different remembered value: the person's
  statement beats the cache. The next broker answer still overwrites it with the
  room's language (unchanged precedence); the documents say so in one sentence.
- Without `--lang`, nothing is written and the client behaves exactly as before:
  remembered value, else English.
- The write reuses `client_language.remember()` (atomic, ignores OS errors); no
  second code path for the file.
- `--json` output of `install` is unchanged.

## Tests

- `install --lang ru` on an empty home: the file holds `ru`; `agentschat --help`
  in a new process with the same home is Russian; same for `en`.
- No `--lang`: no file is created; an existing file is left untouched.
- A conflicting install (foreign files, no `--force`): the file is not written
  or changed.
- An explicit `--lang en` over a remembered `ru` replaces it; a later broker
  answer carrying `ru` replaces it again.
- `uninstall --lang ru` does not write the file.
- The home directory is redirected in every test; tests never touch the real home.
- The existing participant-installer tests that pass `--lang` still pass; list any
  existing test edit in the report.

## Acceptance criteria

- [ ] After `agentschat install --lang ru` on a clean home, `--help` and a failure
      before any broker contact are Russian.
- [ ] Nothing is written without `--lang`, on a refused install, or on uninstall.
- [ ] CHANGELOG, INSTALL guides and the VERIFICATION handoff no longer say that
      `install` does not write the language file, and R1 expects Russian from the
      start.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green
      (sequentially).
- [ ] Report `.development/reports/task-english-release-22-install-remembers-language.md`
      lists the tests added, each document line changed, and every edit to an
      existing test.
