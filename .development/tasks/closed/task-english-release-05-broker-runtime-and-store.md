# Task english-release-05: Broker startup, logs and store errors

**Status:** Completed.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-03.
**Estimate:** 2 hours.

## Summary

The broker's startup refusals are catalogued (operator-facing, in the room
language). The broker's log lines become English in every configuration. The
store's errors become coded exceptions that the broker renders at the edge.

## Why

The store is a lower layer with no notion of a language; today it raises Russian
sentences that surface in the broker's start-up failure. A log is for whoever
debugs, and a log that switches language with the config is harder to search.

## Context you need

- `broker.py`: `run()` and `main()` (the port-in-use refusal, the ready line, the
  stop line, the `--agents` help) and the `log.info(...)` calls for a slot being
  freed, re-attached, connected, disconnected.
- `store.py`: the `StoreError` raise sites (corrupted file, newer schema, missing
  registration, duplicate, missing subscription; about 17 literals).
- Nothing outside the broker parses these lines (checked: the installer's
  `StartStep` polls HTTP, not output). Keep it that way.

## Boundary

- `broker.py` startup and log lines, `store.py`, `broker_messages/*.json`, tests.
- `StoreError` gains a code and parameters; the broker renders it. The store
  imports nothing from the broker.

## Requirements

- Log lines: English text, no catalogue, no Cyrillic. An existing test that
  matches Russian log words is adapted in construction only and listed in the
  report.
- Startup refusals (port taken, bad config) use the catalogue, except the
  language-key refusal of task 02, which stays English.
- `StoreError(code, **params)`: `str()` is an English developer sentence; the
  operator-facing text is rendered from `broker.store_<code>` keys.
- The broker's argparse help strings use the catalogue in the language of the
  config when one is readable, and English otherwise. The report says which.

## Tests

- Each `StoreError` code renders its text under both languages.
- The port-in-use path under both languages (the existing Russian test stays and
  runs with `ru`).
- No broker log record contains Cyrillic.

## Acceptance criteria

- [ ] `store.py` contains no Cyrillic.
- [ ] Every user-visible literal of `broker.py` is in the catalogue and every log
      literal is English.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
