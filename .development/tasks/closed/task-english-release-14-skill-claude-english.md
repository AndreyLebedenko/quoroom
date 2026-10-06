# Task english-release-14: The Claude Code chatlogin skill in English

**Status:** Implemented, awaiting owner review of the text.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-13 (the layout), task english-release-08 and task english-release-09 (the CLI text it describes).
**Estimate:** 3 hours.

## Summary

`kit/en/claude/skills/chatlogin/SKILL.md`: the English counterpart of the Claude
Code `chatlogin` skill (149 lines in Russian), equal in function to the Russian
one.

## Why

The skill is read by a model at the moment it decides how to join the room, how
to treat a refusal and when to answer. It is behaviour, not documentation. A
translation that is merely accurate can still change what the agent does, so the
English text is written for equal effect and checked for it.

## Context you need

- `kit/ru/claude/skills/chatlogin/SKILL.md` (the source of truth for behaviour).
- The English texts it refers to: the CLI sentences (tasks 08 and 09), the
  broker refusals (tasks 03 and 04) and the envelope (task 06). Where the Russian
  skill describes a refusal by its wording, the English skill describes it by the
  English wording that now exists in `en.json`, or by the refusal code.
- The OpenCode skill, which must agree functionally (AGENTS.md Tooling note 4).
- Task 13's agreement test.

## Boundary

- The one skill file and its tests. The OpenCode skill and command are task 15.

## Requirements

- Same sections, same rules, same commands and flags; ASCII punctuation; imperative
  mood addressed to the agent.
- The boundaries section is not softened or strengthened: what the agent may
  not do stays exactly as strict. Where the Russian skill is silent, the English
  one is silent.
- Every phrase of a broker refusal or CLI output that the skill quotes must exist
  in the English catalogue; a test reads the skill's quoted phrases and asserts
  each is present in `en.json`.
- The owner reviews the English text before the task is closed; the report lists
  every place where the English had to choose between two readings.

## Tests

- The agreement test of task 13 passes for `en` against `ru`.
- The quoted-phrase test above.
- No Cyrillic in the file; ASCII-only punctuation.

## Acceptance criteria

- [ ] The English skill matches the Russian one in commands, flags and rules.
- [ ] Every quoted phrase exists in `en.json`.
- [ ] The owner approved the text.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
