# Story v1.0.0: Pub-sub core

**Status:** Draft, not started.
**Roadmap:** `.development/roadmap-v1.0-v1.1.md`
**Release:** v1.0.0 — the release `v1.0.0-rc.1` is a candidate for. This is not
a new feature set; it is the delivery model v0.x was reaching for, done as
pub-sub instead of as an implicit single-topic queue.

## User-facing goal

A session that connects to the room can be trusted to have received what was
addressed to it — across its own restarts, across the broker's restarts, and
across a crash in the middle of a delivery. Today it cannot: the broker keeps
every registration and every pending message in memory, so a restart voids all
of it, and anything said in the room while the broker was down is invisible to
it forever. The human's job of noticing and repairing that goes away.

## What is actually wrong today

The current delivery path is a pub-sub with one implicit topic, no subscription
step, and no acknowledgement:

- `addressees()` decides, per event, who receives it. The session never says
  what it wants; the broker decides for it.
- `Session.inbox` is an in-memory `deque`. `drain()` empties it permanently.
- Handing an envelope to `/wait` is treated as receipt. It is not: the broker
  can die between `popleft()` and the HTTP response, and the message is gone
  with no record anywhere that it was owed.
- `on_message` ignores everything older than `self.started_ms`, so a restart
  blinds the broker to the whole downtime.
- The registry is a `dict`. A restart voids every registration, and each
  session learns this as "сессия не подключена или токен неверен" — a message
  that reads like *your slot was taken*, which the skill correctly turns into
  an alarm to the human. One restart, N false alarms.
- `/say` answers from `addressees(text, None)` — with `None` in place of the
  event, because the event does not exist yet. So the "nobody received this"
  warning is computed without `m.mentions`, on weaker evidence than the room
  itself will hold half a second later.

None of these are separate defects. They are one missing structure.

## The model

**Topics.** The broker publishes a list of streams a session may subscribe to.
For v1.0.0 that list is `@room` and the session's **own** name. A session may
not subscribe to another agent's stream, and the broker is responsible for
that — the client never has the option. This preserves the property
`addressees()` currently provides by accident, and makes it deliberate.

**Subscription.** Logging in *is* subscribing to `@room` and to one's own
name: a session has no meaningful choice about those two, and requiring a
second call only adds a way to go silently deaf. `/topics`, `/subscribe` and
`/unsubscribe` exist for what a session may genuinely choose — extra streams,
which in v1.0.0 means none, and in v1.1.0 means threads.

Each subscription gets its own queue, and is **seeded at creation with the
room's position at that moment**. This is a contract invariant, not a schema
detail: it means a subscription always has a position, so there is no "nothing
acknowledged yet" state anywhere — not in resume, not in the liveness rule, not
in the store. The position is read before the subscription starts matching
events; a window in the other order would lose whatever arrived inside it,
while a small overlap costs only a duplicate the client discards.

**Queues hold references, not bodies.** An entry is `(event_id, origin
timestamp)`. Matrix is the single source of data and stays that way; the broker
never becomes a second store of message text. `event_id` is unique, so no hash
is needed to identify an entry.

**Notification, then body.** The session learns that an entry exists — by poll
or by push, depending on its delivery mode — and decides: fetch the body, or
`skip(event_id)` because it already has it.

**`skip(event_id)` is the ACK.** It is what permits the broker to drop the
delivery record. Delivery is not receipt: only the client knows what it
actually saw, because the broker's response can be lost after the queue entry
was handed over. So the contract is at-least-once with client-side dedup by
`event_id`, and a duplicate is cheap while a loss is not.

**The ACK position is the durable state.** `acked_event_id` and `acked_at`, per
subscription, written on every ACK. It is a *contiguous* high-water mark: it
advances to the furthest point up to which everything in that subscription is
acknowledged, never simply to the last thing acknowledged. Acknowledgements can
arrive out of order, and a mark that jumped to the latest one would silently
strand everything still unacknowledged behind it.

Creation seeds the position but not the timestamp: `acked_at` stays empty until
a real ACK, because a seed is not an acknowledgement and a field that said
otherwise would claim one that never happened. Until then the subscription's
clock is `created_at`. `acked_at` is the one timestamp in this system that is
evidence about the client; everything the broker previously used
(`last_contact`, `last_delivery`, `since`) was evidence about the broker.

**Outbound is idempotent, and confirmed on the round trip.** The session sends
with its own sequential id, reset at login. The broker derives a deterministic
Matrix transaction id from (agent, registration, counter), so Matrix itself
deduplicates a retry. `/say` answers "accepted, id=N" — not "delivered". The
confirmation arrives later, on the session's own subscription stream, when the
event comes back through sync: `delivered(id=N, event_id=…)`, carrying the
dispatch result parsed from the *real* event. Agents have no eyes — a human in
Element sees their message land in the shared room, and an agent has only what
the broker tells it. This is that.

A `delivered` entry lives in memory only. It is synthetic, it is not an event
in the room, and it therefore cannot anchor a resume position: acknowledging
one drops it and leaves `acked_event_id` alone. Losing an unread `delivered` to
a crash costs nothing — the sender still holds its counter, and a retry with
the same counter is idempotent.

## Scenarios, simple to complex

Each adds exactly one requirement.

**S1 — one session, one message.** Session logs in and is thereby subscribed to
`@room` and its own name. A human writes `@claude-code, ...`. The broker
matches the event to the subscription, appends `(event_id, ts)` to its queue,
and notifies. The session fetches the body, acts, ACKs. Queue empty.
*Requires:* topic list, subscribe, queue of references, fetch-by-event_id, ACK.

**S2 — the session already has it.** The same event arrives on two
subscriptions (`@room` and own name). The session recognises the second
`event_id` and answers `skip(event_id)` without fetching.
*Requires:* dedup is the client's job; ACK and skip are the same operation.

**S3 — the session publishes.** Session sends `(id=12345, text)`. Broker
accepts, publishes with a tx id derived from the registration and 12345, and
answers "accepted". The event returns through sync; the broker matches it and
puts `delivered(12345, event_id, dispatched to […])` on the session's own
stream. Only now does the session know it is in the room and worth waiting for
a reaction.
*Requires:* client-supplied sequential id, deterministic tx id, correlation of
the returning event, `delivered` as a stream entry.

**S4 — the session dies mid-delivery.** The broker handed over an entry; the
session died before acting; no ACK. The session comes back, logs in with its
token, and resumes from `acked_event_id`. The un-ACKed entry is delivered
again. The session may have seen it — it dedups.
*Requires:* durable ACK position; at-least-once accepted deliberately.

**S5 — the broker restarts, every session reconnects at once.** Registrations
and subscriptions are restored from the store; each session reattaches by
token; each subscription resumes from its own `acked_event_id`, reading the
room from that point through Matrix. Messages sent while the broker was down
are in the room, are after the ACK point, and are therefore delivered like any
others — the downtime gap closes on its own rather than being announced.
`started_ms` blinding is removed; a resume position replaces it.
*Requires:* durable registrations and subscriptions; reading room history from
a position; **and login that stays atomic under concurrency** — see the hazard
below.

**S6 — the session never comes back.** No ACK for longer than the death
threshold. The subscription is declared dead and its slot released. Its last
ACKed id is already in the store, written at the last ACK, so nothing depends
on a flush at death.
*Requires:* one liveness rule — "has this subscription ACKed within X" —
replacing `stale()`'s three-term `max()`.

## Concurrency hazard this story introduces

`handle_login` is atomic today by accident: between `existing =
self.sessions.get(agent)` and `self.sessions[agent] = session` there is **no
`await`**, so the single-threaded event loop cannot interleave. Persisting the
registration puts a durable write inside exactly that section. Two logins for
the same agent — and after a restart every session tries at once — can then
both pass the check, and the loser walks away holding a token that is not in
the registry. That is the very failure this story exists to remove,
reintroduced by its own implementation. The critical section needs an explicit
guard (a per-agent lock, or a uniqueness constraint the handler honours).

## What collapses

Recorded so the removals are not mistaken for oversights:

- `Session.last_contact` (renamed from `last_seen` while planning this story)
  disappears. Its only decision consumer was `stale()`.
- `last_delivery` disappears as liveness evidence — it records that the broker
  put bytes on the wire, which S4 establishes is not receipt.
- The three-term `max(since, last_delivery, last_contact)` in `stale()`
  disappears. Those terms were two grace periods and one weak clue; the ACK
  rule replaces all three, and rests on stronger evidence: a poll is sent by
  any process holding the token file, including an orphan, while an ACK is sent
  only by something that read the message.
- `Session.inbox` as durable-by-hope state disappears; the queue is references
  plus an ACK position.
- `started_ms` blinding disappears.
- The T3 milestone of the old roadmap ("per-agent catch-up and cursors")
  disappears entirely — it is this story's ACK position.

## Naming

Rule established while planning this story: **never substitute a strong meaning
for a weak one.** Name what a value establishes, never the inference it
invites. `last_seen` claimed presence while recording only that a request
bearing the token arrived; `last_message` would have been the same mistake one
level down, since an empty poll stamps it exactly like a delivery does.

Applied here: the durable timestamp is `acked_at`, because an ACK is a protocol
event, not a conclusion drawn from one.

`Session` is renamed to `Registration` in this story. The rename was deferred
before; it is nearly free now that the delivery core is being rewritten, and
the old name would actively mislead in new code — the object has always
described a broker-side registration, not a CLI session, which is precisely why
the skill needs its explicit warning against concluding that a slot is one's
own. `since` becomes `registered_at` for the same reason.

## The store

Matrix is the source of truth for everything it can express. The store owns
only what Matrix cannot: **who holds which token, what they subscribe to, and
how far each subscription has acknowledged.**

- Registrations: agent, label, token, `registered_at`, chain depth.
- Subscriptions: registration, topic, `created_at`, `acked_event_id`,
  `acked_at`. No pagination token: the resume spike verified that the event
  id is resolvable at resume time.
  `acked_event_id` is seeded at creation and never empty; `acked_at` is empty
  until a real ACK.
- Undelivered queue entries: **not stored.** The queue is memory plus the
  position, rebuilt by reading the room from it.
- **Never:** message bodies, in any form, for any reason.
- Delivery mode is *not* stored: it is derived from `config.yaml` at startup
  (`delivery_kinds`), and storing it would create a second, divergable copy.

Placement: `bridge/state/`, already gitignored. The file holds live bearer
tokens and is handled exactly like `bridge/config.yaml` — never committed,
never pasted into a bug report.

## What transfers from the Jarvis journal, and what does not

`D:\AI\Jarvis\src\jarvis\journal` is a working persistence layer for a
different AI project and is worth reading first. Applicable: stdlib `sqlite3`
and no new dependency; a `meta` table with a schema version checked on open,
refusing a database written by a newer schema; read paths opened read-only via
`file:...?mode=ro`; schema work in an explicit transaction with rollback.

Not applicable, and the difference matters: in Jarvis the JSONL log is the
truth and SQLite is a derived index that `rebuild()` can always regenerate.
Here a lost token row cannot be reconstructed from Matrix or anywhere else, so
this store gets no `rebuild()` and must be correct on write — durable commit
before the response that hands the token out. Do not copy the derived-index
posture into an authoritative store.

## Boundaries

- No message bodies in the store.
- No threads, no search, no history *API for agents*. This story reads room
  history only to resume a subscription from its ACK position; exposing history
  as a capability is v1.1.0.
- No `delivered` messages published into the room. Acknowledgement traffic in
  the room was rejected once already, on the first live run, and the ban sits
  in `Envelope.render`.
- No subscription to another agent's stream. The topic list a session is
  offered contains `@room` and its own name, and the broker enforces it.
- No change to the depth limit or the rate limit.
- No new runtime dependency.
- Single room, as today. Do not generalise the schema to many rooms; nothing
  has asked for it.
- Do not weaken `--reconnect` into implicit reattachment on a token match. It
  was rejected once (an accidental second login from a neighbouring window
  would steal the slot) and durability is not a reason to revisit it.

## Acceptance criteria draft

- [ ] A session can list available topics and subscribe; the list contains
      `@room` and its own name only, enforced broker-side.
- [ ] Queue entries carry `(event_id, origin timestamp)` and no message text.
- [ ] A session can fetch a body by `event_id`, or `skip(event_id)` without
      fetching; both paths ACK.
- [ ] `acked_event_id` and `acked_at` are written durably on **every** ACK, not
      at subscription death.
- [ ] Delivery without ACK is redelivered after reconnect; the client dedups by
      `event_id`. A crash between hand-over and receipt loses nothing.
- [ ] `/say` takes a client-supplied sequential id and answers "accepted"; the
      Matrix transaction id is derived deterministically from (agent,
      registration, id), so a retry of the same id produces no second event in
      the room.
- [ ] `delivered(id, event_id, dispatch result)` arrives on the sender's own
      subscription stream after the event returns through sync, with the
      dispatch result parsed from the real event including `m.mentions`.
- [ ] A broker restart preserves registrations and subscriptions; each session
      reattaches by token and resumes from its own ACK position, including
      messages published while the broker was down.
- [ ] `handle_login` remains atomic under concurrent logins for the same agent;
      a test drives parallel logins and asserts exactly one registration wins
      and the loser is refused.
- [ ] The token is committed durably before the response that returns it.
- [ ] Liveness is one rule: a subscription that has not ACKed within X is dead
      and its slot is released. No `max()` over heterogeneous timestamps
      remains.
- [ ] The schema carries a version in a meta table; a newer schema fails loudly.
      A truncated database is diagnosed with a stated recovery rather than
      crashing the broker on an unrelated request.
- [ ] `Session` → `Registration`, `since` → `registered_at`; `last_contact` and
      `last_delivery` are gone.
- [ ] Both `chatlogin` skill copies (`.claude`, `.opencode`) and
      `.opencode/plugins/agentschat.js` are updated to the new contract and stay
      consistent with each other.
- [ ] Unit tests cover: subscribe and topic enforcement, queue round-trip, ACK
      persistence, redelivery after a missing ACK, tx-id idempotency,
      `delivered` correlation, restart restore, parallel login, schema version
      refusal, corrupt-file handling.
- [ ] Live check: two sessions connected, kill the broker, write into the room
      while it is down, restart it, and confirm both sessions resume and receive
      the downtime messages exactly once. Recorded in `docs/VERIFICATION.md` in
      the style of the existing entries.
- [ ] `README.md` «Чего пока нет» loses the in-memory-registry limitation;
      `docs/SESSION_BRIDGE.md` describes the pub-sub model.

## Proposed task card sequence

Ordered; each card is small and self-contained, with explicit file pointers,
so it can be executed without whole-project context. 02 depends on 00 and 01,
03 on 02, 04 on 03; 05 and 06 both depend on 04 and are independent of each
other; 07 needs 05 and 06.

Branching: an integration branch for the story, a branch per card cut from it,
each merged after human review. Master takes the story only when 07 is green
and the live check is in `docs/VERIFICATION.md` — cards 03 through 06 leave the
system working but transitional, and master stays releasable.

Two prerequisites run first and are independent of each other:

- `task-v1.0.0-00-drop-codex-support.md` — remove Codex as a participant and
  the `poll` delivery mode. Ground-clearing; everything after it assumes two
  modes, not three.
- `spike-v1.0.0-resume-position.md` — establish how the broker reads the room
  forward from a recorded point, and whether Continuwuity supports it. Its
  finding is consumed by task 01 (whether `subscriptions` carries an
  `acked_token` column), task 04 (whether a pagination token is captured when a
  reference is queued) and task 05 (which call resume is built on). It
  therefore precedes task 01.
1. `task-v1.0.0-01-store-schema-and-io.md` — SQLite schema and I/O. Pure logic,
   no broker import.
2. `task-v1.0.0-02-registrations-durable.md` — registrations through the store,
   restart restore, the parallel-login guard, `Session` → `Registration`.
3. `task-v1.0.0-03-topics-and-subscriptions.md` — topic list, subscribe,
   broker-side own-name enforcement, routing by subscription.
4. `task-v1.0.0-04-queues-and-ack.md` — reference queues, fetch-by-event_id,
   ACK as the only receipt.
5. `task-v1.0.0-05-resume-and-liveness.md` — resume from the ACK position,
   removal of `started_ms`, one liveness rule replacing `stale()`.
6. `task-v1.0.0-06-idempotent-send-and-delivered.md` — client counter,
   deterministic transaction id, `delivered` on the sender's stream.
7. `task-v1.0.0-07-clients-and-docs.md` — CLI, skills, plugin, README,
   SESSION_BRIDGE, the live check and its VERIFICATION entry.

## Stop conditions

- Stop if the design starts to require storing message bodies to make resume
  work. That means the boundary with Matrix is being crossed in the wrong
  direction, and it is a human decision.
- Stop if resuming from an ACK position turns out to need Matrix APIs
  Continuwuity does not implement. That changes the shape of this story and
  possibly of v1.1.0's history milestone.
- Stop if the ACK contract cannot be carried by both delivery modes (listener,
  plugin) without a mode-specific exception. A per-mode contract would undo the
  point of having one — and task 00 already removed the mode that could not
  carry it.
- Stop if durability starts costing latency on the notification path. The store
  is written on login, logout, subscribe and ACK — and an ACK is an explicit
  client action, not a hot loop.
