# Task english-release-11: The sentences of install and uninstall; the installer forwards its language

**Status:** Completed.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-07, task english-release-10.
**Estimate:** 2 hours.

## Summary

The human sentences of `agentschat install` and `uninstall` (the action words,
the summaries, the restart hint, the conflict explanation, the help) move to the
client catalogue. The commands take `--lang en|ru`. The participant installer
passes its own `--lang` through, so one run speaks one language and the Russian
block disappears from an English participant install.

## Why

After task 10 nothing parses these sentences, so they can be translated freely.
This is the gap accepted for the installer release (recorded in `docs/INSTALL.md`
and `CHANGELOG.md`); this task closes it.

## Context you need

- `kit.py`: the action words, `KitConflict`'s message, `install_summary`,
  `uninstall_summary`, `restart_hint`, the temporary id-to-Russian table from
  task 10 (removed here).
- `client.py`: `do_install` / `do_uninstall`, the parser for these subcommands.
- Task 07's resolution rule: `--lang` > broker answer > remembered > `en`.
- `installer/participant.py`: where it runs `agentschat install` and `uninstall`.

## Design to settle (AGENTS.md 0.4)

1. **Which language the installer passes.** The installer's `--lang` is the
   language of the installer's own output, but the kit must match the room. When
   the participant installer has reached the broker (its `check_broker` step),
   it can read the room language from `/status`. Recommended: pass the room
   language when known, otherwise the installer's `--lang`; state the case where
   the two differ and what the human sees.

## Boundary

- `kit.py`, `client.py` (install/uninstall parser and sentences),
  `client_messages/*.json`, `installer/participant.py` (the forwarded flag),
  tests, `docs/INSTALL.md` and `CHANGELOG.md` (remove the "Russian block"
  limitation).
- Which kit files are installed per language is task 13; this task changes
  sentences only.

## Requirements

- `ru` output identical to today's; `en` output English, ASCII punctuation.
- `--lang` appears in the help of both subcommands.
- The step line shows the action word for the language; the JSON of task 10 is
  unchanged by the language.

## Tests

- Table over every action, summary and the conflict sentence, both languages.
- An end-to-end test that runs the real `python -m sessionchat.client install
  --lang en` against a temporary home and asserts no Cyrillic on stdout and
  stderr.
- A participant install under `en` prints no Cyrillic at all, client lines
  included (the earlier tests excluded them; this task removes the exclusion).

## Acceptance criteria

- [ ] An English participant install contains no Russian.
- [ ] `kit.py` and the install part of `client.py` have no Cyrillic literal.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.

## Note from task 10 (orchestrator, 2026-10-05)

The participant installer now runs `agentschat install --json` /
`uninstall --json` and no longer echoes the client's human lines into its own
report (`_spoken` was removed in task 10). So the earlier "client lines
included" Cyrillic exclusion no longer exists to remove, and the installer's
report shows no per-file lines. Decide in this task, with the owner's wording
in mind, whether the per-file lines should come back; if so, the installer
renders them itself from the JSON document with its own catalogue keys (never
by parsing client prose), and the report lists the new keys. If not, say so in
the report and keep the test that proves the installer's report holds no
client text.
