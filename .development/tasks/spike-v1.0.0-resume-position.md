# Spike v1.0.0: How to resume reading the room from a known point

**Status:** Not started.
**Story:** `.development/tasks/story-v1.0.0-pubsub-core.md`
**Runs before:** task 01. Independent of task 00.

## Summary

Find out how the broker can read the room forward from a point it recorded
earlier, and whether Continuwuity supports the way Matrix normally does it.
The answer decides a column in the task-01 schema, so it is settled before that
schema is written. Deliverable is a verified finding, not production code.

## Why this is a spike and not an assumption

`GET /_matrix/client/v3/rooms/{roomId}/messages` takes `from` as a **pagination
token**, not an event id. The story's resume depends on turning a recorded
position into such a token. The normal route is
`GET /_matrix/client/v3/rooms/{roomId}/context/{eventId}?limit=0`, which returns
`start` / `end` tokens around an event — and whether Continuwuity implements
`/context` is unverified. Discovering that at task 05 would invalidate work
already merged.

## Context you need

- Story scenario S5 and the section "The store".
- `bridge/sessionchat/broker.py`: the clients in `self.clients` already hold a
  Matrix access token per agent; `sync_forever` is how events arrive today.
- `docker/docker-compose.yml`: the homeserver is
  `ghcr.io/continuwuity/continuwuity:latest`.
- `docs/VERIFICATION.md` for the style of a recorded finding.

## Boundary

- Throwaway probing only: a scratch script, or `curl`/`Invoke-WebRequest`
  against the running local homeserver. Nothing merged into `bridge/`.
- Do not implement resume. That is task 05.
- Do not paste tokens into the finding.

## Questions to answer

1. Does Continuwuity implement `/rooms/{roomId}/context/{eventId}`? With
   `limit=0`? What does it return?
2. Given a token from that call, does `GET /messages?from=…&dir=f` return the
   events **after** the anchor, in order, and does it terminate cleanly at the
   live edge?
3. What does a sync response give per timeline chunk (`prev_batch`), and can a
   token captured at delivery time be stored and replayed later — the fallback
   that avoids `/context` entirely?
4. Do tokens survive a homeserver restart, or are they only valid for the
   session that issued them?
5. What is the practical page size, and what happens when the requested range
   is larger than the room's retained history?

## Deliverable

- An entry in `docs/VERIFICATION.md`: what was run, against which
  Continuwuity version, what was observed, and the date. Written as fact, not
  as inference from documentation.
- A one-paragraph recommendation appended to this card: **anchor by event id
  and resolve at resume time**, or **store a pagination token at ACK time**.
  Name the consequence for each consumer: task 01 (whether `subscriptions`
  carries `acked_token`), task 04 (whether a token is captured when a reference
  is queued — it is obtainable only from the sync response that carried the
  event), and task 05 (which call resume is built on).
- If neither route works, stop and report. That is a story-level problem, not
  a task-level one.

## Acceptance criteria

- [ ] All five questions answered against a running local Continuwuity, not
      from documentation.
- [ ] The finding is recorded in `docs/VERIFICATION.md`.
- [ ] The recommendation is written on this card and names the consequence for
      tasks 01, 04 and 05 by name.
- [ ] No code merged into `bridge/`.

## Recommendation (2026-09-11, verified live — see docs/VERIFICATION.md)

**Anchor by event id and resolve at resume time.** Continuwuity implements
`/rooms/{id}/context/{eventId}?limit=0`, its `start` token is the stream
position of that event, and forward `/messages` from it reads strictly after
it. Tokens survive a homeserver restart and are not account-bound. So the
recorded `acked_event_id` is resolvable whenever resume needs it, and nothing
must be captured at delivery time.

Consequences, by consumer:

- Task 01: no `acked_token` column. `subscriptions` carries `created_at`,
  `acked_event_id`, `acked_at` only. The nullable-column hedge is dropped
  together with the `token=None` parameter of `record_ack`.
- Task 04: nothing is captured when a reference is queued. The queue entry
  stays `(event_id, origin timestamp)`.
- Task 05: resume is built on `/context/{acked_event_id}?limit=0` to resolve
  the position, then `/messages?dir=f&from=<token>` to read forward. Seeding
  at subscription creation (task 03) resolves the position the same way.

Two behaviors resume must respect (both verified): forward reads are
**exclusive** of the anchor event — the anchor itself never reappears, which
is exactly the at-most-once property the ACK position wants; and a page's
`end` disappears at the live edge, which is the natural stop condition.
Pagination caps at 100 events per page regardless of the requested limit, so
the resume loop must paginate until `end` is absent.
