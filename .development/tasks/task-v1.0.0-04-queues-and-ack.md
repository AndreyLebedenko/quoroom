# Task v1.0.0-04: Reference queues and ACK

**Status:** Not started.
**Story:** `.development/tasks/story-v1.0.0-pubsub-core.md`
**Depends on:** task 03.
**Consumes:** `closed/spike-v1.0.0-resume-position.md` — it chose anchoring by
event id, so nothing is captured when a reference is queued.

## Summary

Replace the envelope queue with a queue of references, and make receipt an
explicit client act: the session fetches a body by `event_id` or skips it, and
either way acknowledges. The acknowledgement is what lets the broker forget.

## Context you need

- Story sections "The model" (queues, notification, ACK) and scenarios S1, S2.
- `bridge/sessionchat/broker.py`: `Registration.inbox` / `drain()`,
  `handle_wait` (~line 457), `handle_inbox`.
- `bridge/sessionchat/protocol.py`: `Envelope` and its `render()` — the
  envelope text stays the delivered form; only what is queued changes.
- `bridge/sessionchat/store.py`: `record_ack` from task 01.
- `closed/spike-v1.0.0-resume-position.md`, section "Recommendation": no
  pagination token is captured here; queue entries stay
  `(event_id, origin timestamp)`.
- The two delivery modes (`listener`, `plugin`) come from `config.yaml` via
  `delivery_kinds`; task 00 removed `poll`. Both must carry the same ACK
  contract; a per-mode exception would undo the point.
- No explanatory comments — a rule worth stating is stated as a test
  (AGENTS.md, Core 7). Where this task rewrites code whose existing comments
  carry a rule, that rule becomes a test in the same change. Tests: `unittest`,
  from `bridge/`: `.venv/Scripts/python.exe -m unittest discover -s tests -t .`

## Boundary

- `bridge/sessionchat/broker.py`, `bridge/sessionchat/protocol.py`,
  `bridge/tests/`. Nothing else — client and plugin are task 07.
- Redelivery after a missing ACK, the liveness rule and resume-from-position
  are task 05. This task keeps `stale()` as it is.
- Outbound (`/say`, `delivered`, transaction ids) is task 06.
- Queue entries hold `(event_id, origin timestamp)` and no message text. The
  body is fetched from Matrix on demand.

## Requirements

- A subscription's queue holds references, not envelopes. `on_message` appends
  `(event_id, ts)` to each matching subscription's queue.
- `GET /wait` and `GET /inbox` hand over references, not rendered envelopes.
  Each carries enough for the session to decide without fetching: `event_id`,
  origin timestamp, sender, and the sender's kind (человек / агент).
- `GET /body?event_id=…` returns the rendered `Envelope` for one reference,
  fetched from Matrix. The envelope's existing rules are unchanged, including
  `restart_listener` per mode and the depth line.
- `POST /ack` takes `event_id` and one subscription's topic. It is the same
  operation whether the session fetched the body or decided it already had it —
  there is no separate `skip` endpoint, only a session that acks without
  fetching. It writes `acked_event_id` / `acked_at` through the store on
  **every** call, not at some later flush, and drops the reference from the
  queue.
- Handing a reference over is **not** receipt. Nothing is dropped from a queue
  until its ACK arrives; a reference handed over but not acknowledged stays.
- The same event may reach one session through two subscriptions (`@room` and
  its own name). Both entries are queued and both are acknowledged separately;
  deduplication by `event_id` is the client's job and the broker must not
  collapse them.
- Ordering within one subscription is the order events arrived.
- No pagination token is captured when a reference is queued, and `record_ack`
  takes none. The spike verified live that a recorded `acked_event_id` is
  resolvable whenever resume needs it (task 05), so the sync response's
  `prev_batch` is not kept.
- `acked_event_id` is a **contiguous** high-water mark. Acknowledgements may
  arrive out of order; the mark advances only across an unbroken acknowledged
  prefix, so an ACK for a later entry while an earlier one is outstanding
  leaves the mark where it was. Anything else strands the earlier entry at the
  next resume.

## Acceptance criteria

- [ ] `on_message` appends references; no message text is held in the broker
      beyond the current request.
- [ ] `/wait` and `/inbox` return `event_id`, timestamp, sender and sender kind,
      and no body.
- [ ] `/body` renders the same envelope text the old path produced, including
      the per-mode `restart_listener` instruction and the depth line.
- [ ] `/ack` writes through the store on every call; a reopened store shows the
      new position.
- [ ] A reference handed over and never acknowledged is still in the queue.
- [ ] An event matching two subscriptions of one session produces two
      references, acknowledged independently.
- [ ] Order within a subscription is preserved across mixed fetch/ack sequences.
- [ ] Out-of-order ACK: acknowledging the second entry while the first is
      outstanding leaves `acked_event_id` unmoved; acknowledging the first then
      advances it past both.
- [ ] Both delivery modes drive the same endpoints; no mode-specific branch
      exists in the ACK path.
- [ ] Full suite green; `ruff check` and `ruff format --check` clean.
