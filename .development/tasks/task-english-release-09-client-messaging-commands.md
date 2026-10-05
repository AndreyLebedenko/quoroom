# Task english-release-09: wait, inbox, say, ask and the rest of the client text

**Status:** Planned.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-07.
**Estimate:** 3 hours.

## Summary

The remaining client sentences move to the client catalogue: the `wait` listener
messages, `inbox`, `say`, `ask`, the help and description of every subcommand
except `install` / `uninstall`, and the usage-level failures. The `wait`
listener's two machine-significant outputs are given a stable shape.

## Why

`wait` is the listener that wakes an agent; its output is read by a model. When
it ends it prints a framed notice (broker lost, listener stopped) that tells the
agent what to do next, and that notice must be in the room language like the
envelope. `say` and `ask` print a confirmation and warnings that today are
Russian sentences.

## Context you need

- `client.py`: `do_wait` and `poll_once` (the "broker lost" and "listener
  stopped" frames), `show_pending`, `do_inbox`, `message_text`, `do_say`,
  `do_ask` (the confirmation, the warning, the timeout), the `main()` parser
  definitions for every non-install subcommand.
- Task 08's result-line convention; follow it where a command's outcome matters
  to a program (`say`: sent or refused).
- The skills quote some of these frames (their texts are tasks 14 and 15).

## Boundary

- `client.py` (the commands above and `main()`'s parser, except `install` /
  `uninstall`), `client_messages/*.json`, tests.
- The listener frames keep their `=== AGENTSCHAT: ... ===` first line as an ASCII
  marker in both languages; the sentences inside are catalogued.

## Requirements

- Russian output identical to today's.
- Warnings that the broker already rendered (task 04) are printed as received.
- `say` and `ask` print the result line of task 08 with `"command":"say"` or
  `"ask"`, the event id when there is one, and `"warning"` code when the broker
  sent one.
- Argparse help and descriptions use the resolved language; `-h` itself stays
  argparse's own English.

## Tests

- Table over every `wait` ending, `inbox` with and without messages, `say` and
  `ask` outcomes, under both languages; no Cyrillic in `en`.
- The framed listener notices keep their ASCII first line in both languages.
- Existing tests unchanged.

## Acceptance criteria

- [ ] No Cyrillic literal in `client.py` outside `install` / `uninstall` (task 11
      finishes that).
- [ ] `say` / `ask` print a result line.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.

## Note from task 08 (orchestrator, 2026-10-05)

The result-line helper is `bridge/sessionchat/client_result.py` (`line()`,
`PREFIX`) and `client.report()`; reuse them, with the same conventions: ASCII
JSON, stdout, once per command after the sentences, a refusal sentence on stderr.
Broker answers for `say` carry `warning` (rendered) beside `warning_code`
(`unaddressed`) and `note` beside `note_code` (`addressed_to_person`); see the
report of task 04. `/wait` and `/login` answers now carry `language` (task 08).
