# Task english-release-17: Operator tools and the scan that keeps it English

**Status:** Completed.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** all of tasks english-release-01 to 16.
**Estimate:** 2 hours.

## Summary

`bridge/register_account.py` speaks English (with `--lang ru`), the remaining
stray Russian in runtime files is removed, and one test fails when Cyrillic
appears in runtime code or templates outside the places that are allowed to
hold it.

## Why

The story's acceptance criterion is "no component decides by matching a
sentence" and "nothing Russian is left outside the catalogues"; the second half
needs a guard, or it decays after the first new message that someone writes in
Russian by habit.

## Context you need

- `bridge/register_account.py`: 10 Cyrillic literals (argparse help, errors,
  the line that introduces the YAML to paste into `config.yaml`).
- The list of tracked files with Cyrillic (`git ls-files | xargs grep -lI`):
  after tasks 01-16 what remains must be only documents, tests, `ru`
  catalogues, `kit/ru/`, the Russian READMEs, the demo and the tooling that the
  gate (task 20) classifies.
- `bridge/agentschat` (the sh launcher): its Russian comments.

## Boundary

- `register_account.py` (catalogue or a two-table approach like the wrappers; it
  is a standalone script, so a small inline table is acceptable - state the
  choice), the launcher comment, a new scan test, and the allowlist file the
  scan reads.
- Not in scope: `demo/`, `tools/linux-container/`, `docs/` - classified by the
  gate.

## Requirements

- `register_account.py` takes `--lang en|ru`, English default; behaviour and
  output structure unchanged; the pasted YAML block is not translated (it is
  data).
- The scan test lists every tracked file and fails if Cyrillic occurs in a file
  that is not in an explicit allowlist (documents under `docs/` and
  `README.ru.md`, `tests/`, `ru.json` catalogues, `kit/ru/`, `demo/`, `tools/`,
  the non-gating comment files named in the story). The allowlist is a plain
  list in the test, each entry with the reason it is allowed.
- A Cyrillic string literal in a runtime Python or JavaScript file outside
  `ru` catalogues fails a second, finer check (AST or token based), so a comment
  in Russian is not confused with a message in Russian.

## Tests

- The scan itself, run on the repository, and a unit test of the scan on a
  temporary tree (a stray literal is found, an allowlisted file is not).
- `register_account.py` under both languages.

## Acceptance criteria

- [ ] The scan passes on the repository and fails when a Russian message is
      added to runtime code.
- [ ] `register_account.py` is English by default.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.

## Note from task 12 (orchestrator, 2026-10-05)

Task 12 already contains a small JavaScript lexer (in
`bridge/tests/plugin/agentschat.test.mjs`) that strips comments and checks that
no Cyrillic remains in strings, templates and regexes of the plugin. Reuse its
approach (and a Python equivalent via `tokenize`/`ast`) for the finer check this
card asks for rather than inventing another. The plugin file still has Russian
comments by design (comments are out of scope for the story); the allowlist or
the lexer must say so.
