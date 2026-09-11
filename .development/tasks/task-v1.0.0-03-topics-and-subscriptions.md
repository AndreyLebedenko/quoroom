# Task v1.0.0-03: Topics and subscriptions

**Status:** Not started.
**Story:** `.development/tasks/story-v1.0.0-pubsub-core.md`
**Depends on:** task 02.

## Summary

Make the delivery decision explicit: a session asks what streams exist,
subscribes to the ones it may have, and the broker records that. Replaces
`addressees()` as the thing that decides who a room event reaches.

## Context you need

- Story sections "The model" (Topics, Subscription) and scenario S1.
- `bridge/sessionchat/broker.py`: `addressees()` (~line 250) and its docstring
   — the false-positive history it records is the reason topics exist and must
  survive the change. `on_message` (~line 300) is where matching happens.
- `bridge/sessionchat/store.py`: `add_subscription`, `load_subscriptions`,
  `delete_subscription` from task 01.
- No explanatory comments — a rule worth stating is stated as a test
  (AGENTS.md, Core 7). Where this task rewrites code whose existing comments
  carry a rule, that rule becomes a test in the same change. Tests: `unittest`,
  from `bridge/`: `.venv/Scripts/python.exe -m unittest discover -s tests -t .`

## Boundary

- `bridge/sessionchat/broker.py`, `bridge/sessionchat/protocol.py` (topic name
  constants only) and `bridge/tests/`. Nothing else.
- Queues, notification, ACK and redelivery are task 04. This task routes an
  event to the right subscriptions and stops there — keep using the existing
  `inbox` as the sink so the broker stays working end to end.
- No history reading, no `delivered`, no changes to `publish` or `handle_say`.
- Do not add topics beyond the two below. Threads become topics in v1.1.0; do
  not prepare for them.

## Requirements

- Two topic kinds, and only two: `@room`, and the session's **own** name.
- `GET /topics` (authenticated by the existing token check) returns the list
  this registration may subscribe to. It contains `@room` and the caller's own
  name — never another agent's. The broker decides the list; the client cannot
  ask for anything outside it.
- `POST /subscribe` takes a topic, validates it against that same list, and
  records it. Requesting another agent's topic is refused with a message that
  says the list is broker-owned, not a permission the session can raise.
  Subscribing twice is not an error.
- `POST /unsubscribe` removes one.
- Creating a subscription seeds it with the room's current position, and the
  broker reads that position **before** the subscription starts matching
  events. A window in the other order loses whatever arrives inside it; a
  small overlap is safe, since the client deduplicates by `event_id`.
- **A successful login subscribes the registration to `@room` and its own name.**
  This is the permanent contract, not scaffolding for the tasks before the
  client catches up in 07: those two are implied by being in the room, and a
  session that had to remember a second call could log in and go silently deaf.
  `/subscribe` exists for streams a session may genuinely choose — none in
  v1.0.0, threads in v1.1.0. A restored registration keeps the subscriptions it
  had; it does not get a fresh default set.
- Subscriptions load from the store at startup alongside registrations, so a
  restart does not require re-subscribing.
- `on_message` matches an event to subscriptions instead of asking
  `addressees()` who the recipients are:
  - `@room` in the body or `m.mentions.room` → every `@room` subscription;
  - a mention of an agent (localpart with word boundaries, or a pill in
    `m.mentions.user_ids`) → that agent's own-name subscription.
  The matching rules themselves do not change — only where the answer is looked
  up. `addressees()` keeps its bounded-name and pill logic; it now answers
  "which topics does this event belong to".
- A sender never receives its own event, as today.
- An event that matches no subscription is published and delivered to nobody,
  exactly as now, including the existing warning on `/say`.

## Acceptance criteria

- [ ] `GET /topics` returns `@room` and the caller's own name, and never
      another agent's name, for each configured agent.
- [ ] `POST /subscribe` on another agent's topic is refused; the refusal names
      the broker as the owner of the list.
- [ ] Subscribing twice leaves one row; unsubscribe removes it.
- [ ] Login alone produces both default subscriptions; delivery works end to
      end with no client-side subscribe call.
- [ ] A new subscription is seeded with the current position, and an event
      published between the seed read and the subscription going live is
      delivered rather than lost.
- [ ] Unsubscribing from a default and logging in again does not silently
      re-add it for a restored registration.
- [ ] Subscriptions survive a broker restart with no re-subscribe call.
- [ ] A `@room` message reaches every `@room` subscriber except the sender.
- [ ] A message mentioning one agent by localpart or pill reaches that agent's
      own-name subscription only.
- [ ] The false positives `addressees()` was written against stay fixed:
      `@codex-extra` does not address `codex`, `claude-code-2` does not address
      `claude-code`, and a bare display name addresses nobody.
- [ ] A message matching no subscription still publishes and still produces the
      existing "нет обращения" warning.
- [ ] Full suite green; `ruff check` and `ruff format --check` clean.
