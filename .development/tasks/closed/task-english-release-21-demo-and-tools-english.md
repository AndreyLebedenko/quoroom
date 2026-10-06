# Task english-release-21: demo/battleship and tools/linux-container in English

**Status:** Completed (2026-10-06).
**Story:** story-english-release.md (shared rules apply, except that these
files have no catalogue: see Boundary).
**Depends on:** task english-release-17 (the Cyrillic scan and its allowlist).
**Blocks:** task english-release-20 (the gate).
**Estimate:** 2 hours.

## Summary

The owner decided (2026-10-06) to translate `demo/battleship/` and
`tools/linux-container/` rather than keep them Russian behind a README note or
leave them out of the public tree. After this task neither directory contains
Cyrillic, and the scan from task 17 guards them like the rest of the tree.

## Why

A stranger who reads the README and opens `tools/linux-container` (the Linux lab
that `docs/INSTALL.en.md` points to) must be able to read what it prints and
what it says. The demo is the first thing a visitor can run to see agents work.
Both were left out of tasks 01-19 because they are not runtime.

## Context you need

- `demo/battleship/`: `BRIEF.md` (74 lines, the brief the agents receive),
  `server/README.md`, `server/main.py` (22 lines with Cyrillic), `server/test_main.py`
  (5 lines with Cyrillic).
- `tools/linux-container/`: `README.md` (108 Cyrillic lines), `run.sh`,
  `verify-copy.sh`, `verify-shared-home.sh`, `room-helper.py`, and the two compose
  files (no Cyrillic).
- `bridge/tests/test_cyrillic_scan.py`: the `Allowed("demo/", ...)` and
  `Allowed("tools/", ...)` entries and the `NOT_RUNTIME` tuple. These entries say
  "classified by the gate".
- `docs/INSTALL.en.md` and `CHANGELOG.md` mention the lab; they are not edited by
  this task.

## Boundary

- Translate every Russian word in the two directories into English: documents,
  strings printed or asserted by scripts, and comments. AGENTS.md rule 7 (no
  comments) applies to what you translate: a Russian comment is either removed
  because the code says the same, or kept as an English comment only when it falls
  under exception (b); say which in the report. `docs/VERIFICATION.md` is the place
  for facts about the outside world.
- Behaviour does not change: same commands, same options, same exit codes, same
  file layout, same compose projects and names. A string that another script or a
  test reads (grep in the lab scripts, `test_main.py`) is changed on both sides.
- In `bridge/tests/test_cyrillic_scan.py`: remove the two `Allowed` entries for
  `demo/` and `tools/`. Remove them from `NOT_RUNTIME` only if the finer
  (string-literal) check then passes on `demo/battleship/server/*.py` and
  `tools/linux-container/room-helper.py`; if a Python file there needs a
  Cyrillic literal that is data (a test fixture, for instance), say so and stop
  (AGENTS.md 0.1).
- No change to `README*.md`, `CHANGELOG.md`, `docs/`, runtime code under
  `bridge/sessionchat/` or the other tasks' files.

## Requirements

- `rg -P "[\x{0400}-\x{04FF}]" demo tools` finds nothing.
- ASCII punctuation in English text (AGENTS.md rule 9): no long dashes.
- `bash -n` passes on each shell script; `room-helper.py` compiles; the demo's
  own tests pass the way they did before (record how they are run).
- The lab cannot be run here (it needs Docker); the report says so and lists what
  was checked instead (syntax, a read-through for every printed string, grep for
  strings other scripts read).

## Tests

- The existing scan test, with the two entries removed, passes: that is the
  acceptance test for "no Cyrillic left".
- If a script's printed string is read by another script, a short test or the
  report names the pair and shows they agree.

## Acceptance criteria

- [ ] No Cyrillic in `demo/` and `tools/`.
- [ ] The scan allowlist no longer mentions the two directories.
- [ ] Behaviour unchanged: names, options, exit codes, compose project names.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green
      (sequentially).
- [ ] Report `.development/reports/task-english-release-21-demo-and-tools-english.md`
      lists every file touched, each comment removed or kept and why, and every
      edit to an existing test.
