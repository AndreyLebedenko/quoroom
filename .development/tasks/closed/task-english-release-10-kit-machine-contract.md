# Task english-release-10: install and uninstall report actions as codes

**Status:** Completed.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** none; must land before task 11.
**Estimate:** 3 hours.

## Summary

`agentschat install` and `agentschat uninstall` can report, in a machine-readable
form, what they did to each file and whether they were refused, and the
participant installer reads that instead of the client's Russian sentences. No
sentence is translated in this task.

## Why

Two decisions of the installer depend on the client's prose today:

- whether the client wrote files is decided by looking for the words of
  `kit.Action` values (`participant.py`, the `written` flag, using `kit.WRITES`);
- whether the install was refused for foreign files is decided by finding the
  start of the `KitConflict` sentence in the output (`participant.py`,
  `CONFLICT`).

Both are the same mistake as step names used to be: text as identity. Translating
the client first would freeze it in two languages. This task removes the
dependency; task 11 then translates freely.

## Context you need

- `bridge/sessionchat/kit.py`: `Action` (enum whose values are Russian display
  words), `Step.line()`, `KitConflict`, `install`, `uninstall`, `install_summary`,
  `uninstall_summary`, `WRITES`.
- `bridge/sessionchat/client.py`: `do_install`, `do_uninstall`.
- `bridge/sessionchat/installer/participant.py`: where the output is parsed
  (the `written` detection and the conflict marker `CONFLICT`), and the fake
  `agentschat` in `bridge/tests/test_installer_participant.py`.
- The manifest stores entries by path and digest, not by action text; it must not
  change.

## Design to settle (AGENTS.md 0.4)

1. **Shape.** Recommended: `install --json` / `uninstall --json` print one JSON
   document `{"command": ..., "ok": bool, "code": "<none|conflict|...>",
   "steps": [{"action": "<installed|updated|overwritten|unchanged|conflict|
   removed|kept|gone>", "cli": "...", "target": "..."}]}` on stdout and nothing
   else; without `--json` the human sentences stay as they are until task 11.
2. **Exit code for a refusal.** Recommended: a dedicated code for a conflict
   (distinct from a generic failure), documented next to the installer's codes.
3. **Enum.** `Action` gets language-independent ids as values; the display word
   moves to the catalogue in task 11, so until then the human output maps id to
   the same Russian word in code (a temporary table, removed in 11).

## Boundary

- `kit.py`, `client.py` (`install` / `uninstall` flags and exit code),
  `installer/participant.py` (calls with `--json`, reads the document), tests.
- This task is allowed to change the fake client in
  `test_installer_participant.py` to print the JSON document: that is the input
  of those tests and it is the contract that changed. Their expectations stay
  unchanged and run under `ru`.

## Requirements

- The installer never inspects the client's prose after this task. A test proves
  it by running the installer scenarios with the client's sentences replaced by
  unrelated words.
- The manifest format and the files written are byte-identical to before.
- `--force` and the other flags behave as before.

## Tests

- JSON documents for: first install, no-op install, update, conflict (exit code
  and `code`), forced overwrite, uninstall with kept (hand-edited) files.
- The participant installer scenarios pass with the JSON fake client.
- A scan: `participant.py` no longer refers to `kit.Action` values or to the
  conflict sentence.

## Acceptance criteria

- [ ] No sentence of the client is parsed anywhere in `installer/`.
- [ ] A conflict is recognised by a code, not by text.
- [ ] Manifest and installed files unchanged.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
