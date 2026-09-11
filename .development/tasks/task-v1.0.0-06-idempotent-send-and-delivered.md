# Task v1.0.0-06: Idempotent send and `delivered`

**Status:** Not started.
**Story:** `.development/tasks/story-v1.0.0-pubsub-core.md`
**Depends on:** task 04. Independent of task 05; either order works.

## Summary

Close the outbound path. A session sends with its own sequential id, a retry
cannot produce a second event in the room, and the confirmation arrives only
when the event has come back through sync — because an agent has no eyes and
cannot see its message land the way a human can in Element.

## Context you need

- Story section "The model" (outbound) and scenario S3.
- `bridge/sessionchat/broker.py`: `handle_say` (~line 490) and `publish()`
  (~line 334). Note `handle_say` computes reach with `addressees(text, None)` —
  `None` because the event does not exist yet, so `m.mentions` cannot be
  parsed. The round trip removes that limitation.
- `on_message` is where the returning event is seen.
- `bridge/sessionchat/protocol.py`: `Envelope`, `MAX_DEPTH`,
  `MAX_SENDS_PER_MINUTE`.
- `nio`'s `room_send` accepts a transaction id; Matrix deduplicates by it. The
  broker currently lets nio generate a random one per call.
- No explanatory comments — a rule worth stating is stated as a test
  (AGENTS.md, Core 7). Where this task rewrites code whose existing comments
  carry a rule, that rule becomes a test in the same change. Tests: `unittest`,
  from `bridge/`: `.venv/Scripts/python.exe -m unittest discover -s tests -t .`

## Boundary

- `bridge/sessionchat/broker.py`, `bridge/sessionchat/protocol.py`,
  `bridge/tests/`. Nothing else — client and plugin are task 07.
- **No acknowledgement traffic in the room.** `delivered` travels on the
  sender's own subscription stream, never as a room message. The ban on
  in-room confirmations is recorded in `Envelope.render` and stands.
- Do not change the depth limit or the rate limit, only where they read the
  new response shape.
- No broker-side table of in-flight sends: Matrix's transaction-id dedup is the
  mechanism, and adding a second one would create two answers to one question.

## Requirements

- `POST /say` takes a client-supplied `id`: an integer counter the session
  keeps, reset at login. The broker does not generate it and does not renumber
  it.
- The Matrix transaction id is derived deterministically from (agent,
  registration token or id, client `id`) — same inputs, same tx id, so a retry
  of the same client `id` produces no second event in the room.
- `/say` answers `accepted` with the client `id` echoed back. It no longer
  claims delivery, and it no longer carries the `warning` / `note` about reach:
  that verdict moves to `delivered`, where it can be computed from the real
  event.
- When the event returns through `on_message`, the broker correlates it to the
  pending send (by transaction id or by the `com.agentschat.*` content it
  already writes) and puts a `delivered` entry on the **sender's own**
  subscription stream, carrying: the client `id`, the `event_id`, and the
  dispatch result — which subscriptions it reached, or that it reached none.
- The dispatch result is computed from the returned event, so `m.mentions` is
  parsed properly. The existing distinction stays: "addressed to a person, not
  an agent" is a normal turn of conversation, while "no addressee at all" is
  the loud warning.
- A `delivered` entry lives in memory only and never anchors a resume position:
  it is synthetic and has no place in the room's event stream. Acknowledging it
  drops it and leaves `acked_event_id` untouched, and generates nothing
  further. A `delivered` lost to a crash costs nothing — the sender holds its
  counter and a retry with the same counter is idempotent.
- If the event never returns within a bounded window, the pending send is
  reported to the sender as unconfirmed — with the client `id`, so a retry with
  the same id is the correct next step and is safe.

## Acceptance criteria

- [ ] `/say` requires a client `id` and answers `accepted`, not delivered.
- [ ] Two `/say` calls with the same client `id` produce exactly one event in
      the room (asserted on the transaction id passed to `room_send`).
- [ ] `delivered` arrives on the sender's own stream after the event returns,
      carrying client `id`, `event_id` and the dispatch result.
- [ ] The dispatch result is computed from the returned event: a pill-only
      mention with no plain-text localpart is reported as reaching that agent.
- [ ] A message addressed to a person produces the mild note; a message with no
      addressee at all produces the loud warning — both on `delivered`, neither
      on `/say`.
- [ ] No `delivered` text is ever published into the room.
- [ ] Acknowledging a `delivered` entry produces no further entry and does not
      move `acked_event_id`; a test asserts the mark is unchanged.
- [ ] A `delivered` not yet read when the broker restarts is simply gone, and
      the sender's resume position is unaffected.
- [ ] A send whose event never returns is reported unconfirmed, naming the
      client `id`.
- [ ] Depth limit and rate limit behave exactly as before, including the
      in-room notice when the depth limit is hit.
- [ ] Full suite green; `ruff check` and `ruff format --check` clean.
