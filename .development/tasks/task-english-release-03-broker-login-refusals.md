# Task english-release-03: Broker errors carry a code; login refusals localised

**Status:** Planned.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-02.
**Estimate:** 3 hours.

## Summary

Every refusal the broker sends for `login`, `logout` and the slot logic becomes
`{"code": "<stable_code>", "message": "<sentence in the room language>"}` with
the HTTP status unchanged. The sentences come from a broker catalogue. The client
reads `message` to show and `code` to decide.

## Why

Today the client prints `response.text` as it is (`explain()` in `client.py`),
and the broker's refusal is one Russian paragraph. The reader of a refusal is a
person or a language model, and the model also acts on it, so the code is the
stable thing and the sentence is for the reader. This task sets the error
contract that tasks 04, 05 and 08 reuse.

## Context you need

- `broker.py`: `Registration.advice`, `_release_stale`, `_refuse_taken_slot`,
  `handle_login`, `handle_logout`, `registration_of`. The strings are the 20 or
  so Cyrillic literals between about lines 170 and 520: the slot-taken advice
  with its seconds, the reconnect refusals, the delivery-mode refusal, the
  unknown-agent refusal.
- `client.py`: `explain(response)` is the single place that reads a refusal.
- `bridge/tests/test_sessionchat.py` asserts several of these texts.

## Design to settle (AGENTS.md 0.4)

1. **Error body shape.** Recommended: JSON `{"code", "message", "params"}`, where
   `params` are the numbers and names the sentence used. The broker no longer
   produces plain-text error bodies.
2. **Compatibility.** Client and broker ship in one package and one version, so
   there is no mixed-version window. Say so in the report and do not keep the
   old text path.

## Boundary

- `broker.py` (the login / logout / slot / delivery refusals and one helper that
  builds an error response from a code, an HTTP status and named parameters),
  a new `bridge/sessionchat/broker_messages/{en,ru}.json`, `client.py`
  (`explain` only), `bridge/pyproject.toml` package-data, tests.
- Send, inbox and status refusals are task 04; startup is task 05.

## Requirements

- One `broker.<meaning>` key per sentence. Codes are stable snake_case words
  (`slot_taken`, `slot_silent`, `reconnect_without_registration`, ...); the
  report lists them all.
- Sentences with seconds, agent names or delivery modes use placeholders; the
  Russian rendering is identical to today's.
- Every refusal keeps its HTTP status.
- No token appears in a message or in `params`.

## Tests

- A table over every code: status, code, and `message` equal to the old Russian
  text under `ru`; the `en` text has no Cyrillic.
- The client prints `message`; where it branches at all, a test proves it
  branches on `code` and not on text.
- Existing tests unchanged (the broker runs with `language: ru`).

## Acceptance criteria

- [ ] No Cyrillic literal remains in the login / logout / slot code.
- [ ] Every refusal in scope has a code, a status and a catalogue key.
- [ ] `ru` output identical to before; `en` output English only.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
