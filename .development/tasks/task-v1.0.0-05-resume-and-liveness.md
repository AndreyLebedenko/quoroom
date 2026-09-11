# Task v1.0.0-05: Resume from ACK, and one liveness rule

**Status:** Not started.
**Story:** `.development/tasks/story-v1.0.0-pubsub-core.md`
**Depends on:** task 04.
**Consumes:** `spike-v1.0.0-resume-position.md` — it establishes *how* a
recorded position becomes a readable point in the room. Build resume on its
recorded finding, not on an assumption about `/messages`.

## Summary

Make the ACK position do its two jobs: rebuild a subscription's queue after a
restart by reading the room from that point, and decide when a subscription is
dead. Removes `started_ms` blinding and the three-term `max()` in `stale()`.

## Context you need

- Story scenarios S4, S5, S6 and the section "What collapses".
- `bridge/sessionchat/broker.py`: `on_message`'s `started_ms` filter (~line
  300), `Registration.stale()` (~line 144), `state()`, `advice()`,
  `handle_login`'s stale-slot release.
- `bridge/sessionchat/protocol.py`: `STALE_SECONDS` and its rationale — that
  rationale is about a polling listener and does not survive this task; the new
  threshold rests on acknowledgement instead.
- The spike's entry in `docs/VERIFICATION.md`: whether `/rooms/{id}/context`
  resolves an event id to a pagination token, or whether the token has to be
  captured at delivery time and stored. `GET /messages` takes `from` as a
  pagination token, never an event id — do not assume otherwise.
- No explanatory comments — a rule worth stating is stated as a test
  (AGENTS.md, Core 7). Where this task rewrites code whose existing comments
  carry a rule, that rule becomes a test in the same change. Tests: `unittest`,
  from `bridge/`: `.venv/Scripts/python.exe -m unittest discover -s tests -t .`

## Boundary

- `bridge/sessionchat/broker.py`, `bridge/sessionchat/protocol.py`,
  `bridge/tests/`. Nothing else.
- Reading room history here serves resume only. Exposing history to agents is
  v1.1.0 — add no endpoint for it.
- Outbound (`/say`, `delivered`) is task 06.
- No new configuration keys; thresholds are constants in `protocol.py` beside
  the existing ones.

## Requirements

- **Resume.** At startup, and when a registration reattaches, each subscription
  rebuilds its queue by reading the room forward from its recorded position —
  resolved the way the spike established — and
  matching events against that subscription's topic (the task-03 rules). There
  is no "never acknowledged" case to handle: task 03 seeds every subscription
  with the room's position at creation, so resume has one code path.
- Remove the `started_ms` filter in `on_message`. Resume position replaces it;
  keeping both would re-blind the broker to the downtime it just recovered.
- Bound the read: a page size and a cap, with a clear log line when a
  subscription is so far behind that the cap truncates it. Truncation must be
  visible, not silent.
- **Redelivery.** A reference handed over before a crash and never acknowledged
  reappears after resume. The client deduplicates by `event_id`; the broker
  does not try to remember what it already showed.
- **Liveness.** One rule replaces `stale()`'s `max(registered_at,
  last_delivery, last_contact)`: a subscription that has not acknowledged
  within X is dead, and its registration's slot is released. The clock is
  `acked_at`, or `created_at` while `acked_at` is NULL — a seeded position is
  not an acknowledgement and must not be read as one. Delete
  `last_contact` and `last_delivery` and every read of them, including in
  `state()`, `advice()` and the login log line.
- A freshly restored registration that has not yet acknowledged anything needs
  a grace period before X applies — it may be a session whose listener died
  with the broker and which is on its way back. Choose the constant, name it,
  and pin its justification as a test — an invariant against the constants it
  depends on, so it breaks if one of them moves. Do not silently reuse
  `STALE_SECONDS`, whose reasoning was about continuous polling.
- `state()` and `advice()` are rewritten on the new evidence. Neither may claim
  a session is alive on the strength of a stored row: the broker's existing
  refusal to assert liveness from an indirect signal stands, and this task
  turns that refusal into a test.

## Acceptance criteria

- [ ] After a simulated restart, a subscription resumes from its
      `acked_event_id` and receives everything published while the broker was
      down, exactly once per subscription.
- [ ] A subscription that has never acknowledged resumes from its seeded
      position, by the same code path as one that has, and never reads the room
      from the beginning.
- [ ] The `started_ms` filter is gone; no test depends on it.
- [ ] A reference handed over and not acknowledged before a restart is
      redelivered.
- [ ] Truncation of a very stale subscription logs a clear line naming the
      subscription and the gap.
- [ ] `stale()` is one condition on acknowledgement; `last_contact` and
      `last_delivery` no longer exist anywhere in `bridge/`.
- [ ] A restored registration is not released during its named grace period,
      and is released after it if it never acknowledges.
- [ ] No delivery mode is exempt from the liveness rule; task 00 removed the
      one that had to be.
- [ ] `state()` never reports «слушает» for a registration restored from the
      store that has not contacted this broker instance.
- [ ] Full suite green; `ruff check` and `ruff format --check` clean.
