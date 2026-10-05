# Task english-release-20: The gate before the repository is opened

**Status:** Planned.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** all of tasks english-release-01 to 19.
**Estimate:** 2 hours of agent work, plus a human run on a clean machine.

## Summary

The last check before the owner opens the repository: the README says which
documents are still Russian, the files that do not belong in a public tree are
classified, the human runs the whole product once in English on a clean machine
and once in Russian, the result is recorded, and the CHANGELOG states what the
release is.

## Why

Every earlier task is verified by tests. What the owner is deciding is whether a
stranger succeeds, and no test covers that. The gate is that run, plus the
housekeeping that a public tree needs and a private one does not.

## Context you need

- The files with Cyrillic that remain after task 17: the Russian documents,
  `README.ru.md`, `tests/`, `ru` catalogues, `kit/ru/`, `demo/battleship/`,
  `tools/linux-container/`.
- `docs/VERIFICATION.md`: what a recorded live run looks like, and the manual
  handoff convention (AGENTS.md Testing protocol 4).
- `CHANGELOG.md`: the rc.2 section and the entries added by the installer
  bilingual task.

## Boundary

- `README.md`, `README.ru.md`, `CHANGELOG.md`, `docs/VERIFICATION.md` (a new
  recorded section, appended; earlier records untouched), and moves or removals
  that the owner approves for `demo/` and `tools/`.
- No code change. A defect found by the run becomes a bug report under
  `.development/bugreports/` (AGENTS.md "How to report an issue") and, if it
  blocks the gate, a task card; it is not fixed inside this task.

## Requirements

- The README names the documents that remain in Russian (the design history:
  `docs/SESSION_BRIDGE.md`, `docs/VERIFICATION.md`, `docs/COORDINATION_PLAN.md`)
  and says the Russian is the author's working language, not a missing
  translation.
- Owner decision, recorded in the card report: for `demo/battleship/` and
  `tools/linux-container/` keep with a note in the README, translate, or leave
  out of the public tree.
- Manual handoff prepared for the human: the exact commands for a clean-machine
  run with `language` unset (English) and then with `language: ru`, what to look
  for in each place (installer, each `agentschat` command, a refusal, the room
  notice at the depth limit, the envelope an agent receives, the skill text the
  agent follows), and where to write the result.
- The owner opens the repository only after the English run is recorded as
  passing in `docs/VERIFICATION.md`.

## Acceptance criteria

- [ ] The README states which documents are Russian and why.
- [ ] The decision about `demo/` and `tools/` is recorded and carried out.
- [ ] The handoff is prepared; the recorded English run passes (human).
- [ ] The recorded Russian run matches what the product printed before the story
      (human).
- [ ] CHANGELOG describes the release; the full suite, `node --test`,
      `ruff check`, `ruff format --check` are green on the release commit.
