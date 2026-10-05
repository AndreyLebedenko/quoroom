# Roadmap: v1.0.0 → v1.1.0

Status: preliminary. Not approved; it will be revised as usage statistics
accumulate, so treat the order and scope below as a working hypothesis.
Language of all development documentation: English.

## Versioning

The repository carries one tag, `v1.0.0-rc.1`. The delivery work below is what
that candidate is a candidate for, so it ships as **v1.0.0**, and the workspace
features ship as **v1.1.0**. Earlier drafts of this plan used "v0.1 / v0.2";
that vocabulary came from the feature discussion, not from the repository, and
is retired.

## v1.0.0 — Pub-sub core

Story: `.development/tasks/story-v1.0.0-pubsub-core.md`

Not a feature set. The current delivery path is a pub-sub with one implicit
topic, no subscription step and no acknowledgement: `addressees()` decides for
the session, `Session.inbox` is an in-memory `deque`, hand-over is treated as
receipt, and a restart voids every registration while `started_ms` blinds the
broker to the downtime. v1.0.0 makes that structure explicit — topics,
subscriptions, reference queues, client-side ACK, durable ACK positions, and
idempotent sends confirmed on the round trip through Matrix.

This is a release rather than a milestone because it changes the contract with
every consumer: the broker, the client CLI, all three `chatlogin` skill copies,
and the OpenCode plugin.

## v1.1.0 — Shared workspace

Turns the room from a delivery channel into a place a human and several live
agent sessions share. Every item gives a participant access to context that
already exists in the room, or makes the human's re-entry into it cheap. No new
roles, no coordinator, no agent negotiation protocol.

Two facts shape the plan. **Continuwuity already stores the full room history**,
and the broker holds a Matrix token for every agent — so most of "history,
search and threads" is exposing the Client-Server API through the broker, not
building a store. And `publish()` still sends flat `m.room.message` events with
no `m.relates_to`.

### M1 — Threads as first-class context

First, not fourth. Matrix threads are native and Element renders them for free,
but retrofitting is expensive: if history is exposed flat, agents build on flat
event ids and every later API grows a threaded variant. Threading first makes
history and search thread-aware from their first version — and gives the
pub-sub topic list an obvious future member.

- `publish()` accepts a thread root and emits `m.relates_to` / `rel_type:
  m.thread`.
- `say` and `ask` can open a thread and answer inside one.
- Delivered entries carry the thread root so a session can reply in place.

### M2 — History access for agents

- Broker endpoint over `GET /_matrix/client/v3/rooms/{roomId}/messages`: room
  history, one thread, one sender, history from a given event, bounded pages.
  v1.0.0 already reads history to resume a subscription; this exposes it as a
  capability.
- Output shaped like an envelope, not raw Matrix JSON.
- **Decide explicitly:** v1.0.0 makes visibility deliberate (a session
  subscribes to `@room` and its own name, and the broker refuses anything
  else). A history API hands an agent everything in the room regardless of
  subscription. That is the point of a shared workspace, but it should be an
  accepted decision with a written rationale, not a side effect.

### M3 — Search

- First check whether Continuwuity implements `POST
  /_matrix/client/v3/search`; its coverage here has historically been
  incomplete. **This gates the design and comes before estimation.**
- If it does: proxy it, filtered by room, sender, thread and time.
- If not: a broker-owned SQLite FTS index in the store v1.0.0 already
  established.
- Full-text only. No embeddings.

### M4 — Human attention layer

- **In scope:** structured flags on messages — `needs_input`, `needs_decision`,
  `blocking` — carried as `com.agentschat.*` content keys alongside the
  existing `depth`, plus a query for "what is open and waiting for me".
- **Out of scope for the broker:** the narrative summary of "what happened
  while I was away". That needs a model call inside a component that today has
  zero model dependencies and is pure transport plus policy. Build it on the
  human's side, as a skill over M2.

### Exit criteria for v1.1.0

M1–M4 complete, each exercised live and not only under unit tests, with the
outcome recorded in `docs/VERIFICATION.md` in the style of the existing
entries.

## Deferred beyond v1.1.0

Recorded so the ordering is not re-litigated:

1. Decisions, tasks and facts as structured events, separately retrievable.
2. A shared `/context` API — compact working context (topic, participants,
   current question, decisions, open questions, recent relevant messages)
   rather than raw history.
3. Semantic search and RAG over embeddings.
4. Agent presence and activity state (idle, exploring, implementing, blocked).
   Cheaper after v1.0.0 than it was: subscription liveness is already a real
   signal, where polling never was.
5. Provenance and artifacts — links between messages, decisions and commits,
   diffs, files, test results.

Dropped rather than deferred: **per-agent catch-up and cursors**, formerly its
own milestone. It is the ACK position in v1.0.0.

## Open questions

- Continuwuity search support. Gates M3.
- Read scope after M2: is full room visibility for every connected agent the
  accepted model, or does some content stay subscription-scoped?
- Whether the depth and rate limits still make sense once agents can read
  history without being addressed. A limit designed against blind loops behaves
  differently when participants can see the whole exchange.
- Live verification debt inherited from v0.x (depth limit, rate limit, listener
  watchdog, autocompaction survival) — v1.0.0 rewrites the delivery path those
  guards sit on, so most of it is re-verified there rather than separately.

## Working conventions for this directory

- `tasks/` — one file per story or task; move to `tasks/closed/` when done.
- `bugreports/` — one file per defect; move to `bugreports/closed/` when fixed,
  keeping the file rather than deleting it.
- All development documentation is in English. `docs/` and `README.md` keep
  their current language.
