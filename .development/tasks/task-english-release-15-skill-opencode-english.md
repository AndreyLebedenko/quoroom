# Task english-release-15: The OpenCode skill and command in English

**Status:** Planned.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-14 (same method and tests).
**Estimate:** 3 hours.

## Summary

`kit/en/opencode/skills/chatlogin/SKILL.md` (168 lines in Russian) and
`kit/en/opencode/command/chatlogin.md` (24 lines): the English counterparts of
the OpenCode skill and command. This task also removes the temporary
"language without a variant" fallback of task 13.

## Why

Same as task 14. The OpenCode skill differs by design from the Claude Code one
(the plugin lives inside the CLI, so there is no separate listener to start) and
the two must still agree on `login`, `say`, `ask`, `status` and the boundaries.

## Context you need

- `kit/ru/opencode/skills/chatlogin/SKILL.md` and `kit/ru/opencode/command/chatlogin.md`.
- Task 14's English Claude skill for shared phrasing, so the shared parts read the
  same in both.
- Task 13's agreement test and the fallback it introduced.

## Boundary

- The two files, the removal of the fallback in `kit.py`, tests.

## Requirements

- The requirements of task 14 apply to both files, including the quoted-phrase
  test and owner review.
- After this task, installing any language that lacks any file is a failing test,
  not a runtime fallback: a test enumerates every language and every kit path.
- `kit_variant_missing` and its fallback are deleted.

## Tests

- The agreement test across languages and across the two CLIs.
- The completeness test: every language has every kit file.
- The quoted-phrase test for both files.

## Acceptance criteria

- [ ] The English OpenCode skill and command match the Russian ones in commands,
      flags and rules.
- [ ] No fallback remains; the completeness test passes.
- [ ] The owner approved the text.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.

## Note from tasks 13 and 14 (orchestrator, 2026-10-05)

Review of task 13 settled that the kit variant is chosen PER CLI (a CLI with no
`<language>/<cli>` directory falls back to `ru` and raises `kit_variant_missing`);
`kit/en/claude/...` exists after task 14 and `kit/en/opencode/...` arrives here.
This task deletes the fallback block (`COMMON`'s sibling constants,
`FALLBACK_VARIANT`, `VARIANT_MISSING`, `REFUSALS`, `variant_of`) and the tests
named `TemporaryRussianOnlyVariantTests` / `TemporaryVariantFallbackTests`, as
the report of task 13 says, and adds the completeness test the card asks for.
The envelope's English first line is `=== AGENTSCHAT: incoming message ===` and the
`wait` frame titles are in the reports of tasks 06 and 09; the skill quotes them.
