# Task english-release-13: The kit ships a variant per language

**Status:** Planned.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-11, task english-release-12.
**Estimate:** 3 hours.

## Summary

The kit's agent-facing files (the `chatlogin` skills and the OpenCode command)
exist once per language, and `agentschat install --lang` lays down the variant
for the chosen language. The language-neutral plugin is shared. The existing
Russian files become the `ru` variant unchanged; the English files are written in
tasks 14 and 15.

## Why

The skills are instructions a model follows, and they describe what the broker
and the CLI print. A room in English with Russian skills makes the agent reason
about English refusals from Russian instructions. The skill language must follow
the room language, chosen at install time.

## Context you need

- `bridge/sessionchat/kit/` today: `claude/skills/chatlogin/SKILL.md`,
  `opencode/skills/chatlogin/SKILL.md`, `opencode/command/chatlogin.md`,
  `opencode/plugins/agentschat.js`; `kit.py` reads these as package data.
- `kit.py`: `Step`, the manifest (entries by path and digest), `install`,
  `uninstall`.
- `bridge/tests/test_kit.py`, `test_kit_installer.py`.
- AGENTS.md Tooling note 4: the two `chatlogin` skills differ by design and must
  agree functionally on `login`, `say`, `ask`, `status` and the boundaries.

## Design to settle (AGENTS.md 0.4)

1. **Layout.** Recommended: `kit/common/` (the plugin), `kit/en/` and `kit/ru/`
   each holding `claude/...` and `opencode/...` with the same relative paths.
   The destination paths and the manifest keys do not include the language.
2. **A language with no variant.** Until task 15 lands, `en` variants of the
   skills do not exist. Recommended: the install of a language without a variant
   falls back to `ru` and reports the code `kit_variant_missing`; task 15 deletes
   the fallback and adds a test that every language has every file. State this
   temporary rule in the report.
3. **Changing the language later.** Reinstalling under another language
   replaces the variant files through the normal update path; a hand-edited
   file is kept or conflicts exactly as it does today. Say so in the install
   guide (task 18).

## Boundary

- `bridge/sessionchat/kit/**` (move the current files into `ru/` and `common/`
  without changing their bytes), `kit.py`, `bridge/pyproject.toml`
  package-data, tests, `docs/INSTALL.md` pointer for the layout.

## Requirements

- Moved Russian files are byte-identical to before (a test compares digests with
  the previous layout's values).
- `install` and `uninstall` act on the same destination paths as before; a
  manifest written by the previous layout is read by the new one.
- The functional-agreement test: for every language and both CLIs, the set of
  `agentschat` commands and flags mentioned in code spans of the skill is the
  same (a mechanical extraction), so the two languages and the two CLIs cannot
  drift apart silently.

## Tests

- Install for each present language into a temporary home: files, manifest,
  digests; reinstall under the other language updates the variant files.
- The fallback case and its code.
- Existing kit tests unchanged.

## Acceptance criteria

- [ ] `kit/ru/` is the old content, byte for byte; `kit/common/` holds the plugin.
- [ ] `install --lang` selects the variant; the manifest is language-independent.
- [ ] The agreement test exists and passes for the languages present.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
