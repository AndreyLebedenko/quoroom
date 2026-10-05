# Task english-release-19: Architecture and agent-integration guides in English

**Status:** Completed.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-06 (envelope), task english-release-08 (result line).
**Estimate:** 3 hours.

## Summary

English versions of `docs/ARCHITECTURE.md` (230 lines) and
`docs/AGENTS_INTEGRATION.md` (119 lines), with the new facts of this story
added where the Russian documents describe the contracts: the room language,
the error body with a code, the envelope `kind` codes, the `AGENTSCHAT-RESULT`
line.

## Why

A contributor or an integrator who does not read Russian needs two documents
before anything else: how the parts fit, and how an agent platform plugs in.
Both describe the very contracts this story changes, so they are updated and
translated in one pass; translating the old text and then editing it would
translate the contracts twice.

## Context you need

- The two Russian documents, `docs/SESSION_BRIDGE.md` for the decisions behind
  them (read, not translated), and the final text of tasks 02, 03, 04, 06, 08.
- AGENTS.md project-context rule 4: references to files use stable filename
  identity.
- Open question 1 of task 18 decides the file layout convention; follow it.

## Boundary

- The two new English documents, links in `README.md` and `README.ru.md`, a
  short "contracts" section in each that lists the codes introduced by tasks
  03-08 (the code list is generated into the report by those tasks).
- Out of scope: `docs/SESSION_BRIDGE.md`, `docs/VERIFICATION.md`,
  `docs/COORDINATION_PLAN.md`.

## Requirements

- Same structure and numbering as the Russian documents; facts translated, not
  re-verified, nothing strengthened (a Russian "not verified live" stays "not
  verified live").
- The Russian documents get the same additions about the new contracts, so the
  two stay in step.
- ASCII punctuation, UTF-8, commands and identifiers unchanged.

## Acceptance criteria

- [ ] Both documents exist in English with the sections of the Russian ones.
- [ ] Both languages document the room language, the error code body, the
      envelope kinds and the result line.
- [ ] READMEs link to the right documents.
- [ ] No code changed; the suite is untouched.

## Note from task 08 (orchestrator, 2026-10-05)

When documenting the `AGENTSCHAT-RESULT` line, state that a reader takes the last
line with that prefix, and that the login line has `mode` and `reconnected`, not
a session id. The exact format and code table are in the report of task 08;
`say` / `ask` are in the report of task 09 once it exists.
