# Task v1.0.0-01: Store schema and I/O

**Status:** Not started.
**Story:** `.development/tasks/story-v1.0.0-pubsub-core.md`
**Consumes:** `spike-v1.0.0-resume-position.md` — its recommendation decides
whether `subscriptions` needs an `acked_token` column.

## Summary

Create the broker's durable store: a SQLite schema for registrations and
subscriptions, plus the functions that read and write it. Pure logic — nothing
in this task imports or touches the broker.

## Context you need

- Story sections "The store" and "What transfers from the Jarvis journal".
- `bridge/sessionchat/broker.py`, the `Session` dataclass (~line 69): the
  fields that become registration columns. **Do not modify broker.py here.**
- `D:\AI\Jarvis\src\jarvis\journal\corpus.py` for the schema-version pattern
  (`_check_schema_version`, `_connect_sqlite_read_only`). Copy the pattern, not
  the derived-index posture: this store is authoritative and has no `rebuild()`.
- Project rules: stdlib `sqlite3` only, no new dependency. No explanatory
  comments — a rule worth stating is stated as a test (AGENTS.md, Core 7).
  Tests are `unittest`, run from `bridge/` as
  `.venv/Scripts/python.exe -m unittest discover -s tests -t .`

## Boundary

- New module `bridge/sessionchat/store.py` plus tests in
  `bridge/tests/test_store.py`. No changes anywhere else.
- No broker wiring, no HTTP, no Matrix, no asyncio. Synchronous functions only.
- **Queue entries are not stored.** The undelivered queue is memory plus the
  ACK position; task 05 rebuilds it by reading the room. Do not add a table
  for it.
- No message bodies, ever.

## Requirements

- Database file under `bridge/state/`, path passed in by the caller (the
  constant lives in the broker, added in task 02). Create parent directories.
- Schema, version 1:
  - `meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)` holding `schema_version`.
  - `registrations(agent TEXT PRIMARY KEY, label TEXT NOT NULL, token TEXT NOT
    NULL, registered_at REAL NOT NULL, depth INTEGER NOT NULL DEFAULT 0)`.
    `agent` as primary key is what makes "one registration per agent" a
    property of the schema rather than of a code path.
  - `subscriptions(agent TEXT NOT NULL, topic TEXT NOT NULL, acked_event_id
    TEXT, acked_at REAL, PRIMARY KEY (agent, topic), FOREIGN KEY (agent)
    REFERENCES registrations(agent) ON DELETE CASCADE)`, plus
    `created_at REAL NOT NULL`.
  - `acked_token TEXT` in `subscriptions` if the spike recommends storing a
    pagination token at ACK time. **If the spike has not reported when this
    task starts, include the column as nullable anyway** — an unused nullable
    column costs nothing, while adding one later means migrating a live store
    holding real bearer tokens.
- API:
  - `insert_registration(...)` — fails with a distinct exception if the agent
    already has one. Task 02 depends on this failing rather than overwriting.
  - `update_registration(agent, *, label=None, depth=None)`.
  - `load_registrations()` → every row.
  - `delete_registration(agent)` — cascades to its subscriptions.
  - `add_subscription(agent, topic, created_at, seed_event_id,
    seed_token=None)` (idempotent) — the seed is the room's position at the
    moment of subscribing, written straight into `acked_event_id` /
    `acked_token`. A subscription is therefore never in a "no position yet"
    state, and resume has one code path instead of two. The caller supplies the
    seed; the store does not know about Matrix.
    `acked_at` stays NULL until a real ACK: seeding it would make the field
    claim an acknowledgement that never happened. `created_at` is the clock for
    a subscription that has not acknowledged yet.
  - `delete_subscription(agent, topic)`, `load_subscriptions(agent)`.
  - `record_ack(agent, topic, event_id, at, token=None)` — one statement, one
    commit. `token` is written only if the spike chose that route.
- On open: create the schema if absent; if `meta.schema_version` is newer than
  the code knows, raise a named exception instead of reading the file. Read-only
  paths use `file:...?mode=ro`.
- A truncated or non-database file raises a named exception carrying the file
  path and the recovery ("delete it and re-run `/chatlogin` in each session"),
  never a bare `sqlite3.DatabaseError`.
- Writes commit before returning. No write-behind, no batching.

## Acceptance criteria

- [ ] Round-trip: registration and subscriptions written, store reopened, rows
      read back identical (a test reopens the file between calls).
- [ ] `insert_registration` for an agent that already has one raises the named
      exception and leaves the existing row untouched.
- [ ] `delete_registration` removes the agent's subscriptions.
- [ ] A subscription is readable immediately after `add_subscription` with its
      seeded position in place; no row ever has a NULL `acked_event_id`.
- [ ] `acked_at` is NULL until `record_ack` is called; seeding does not set it.
- [ ] `record_ack` is durable: reopen after the call shows the new
      `acked_event_id` / `acked_at`, and `acked_token` when one was given.
- [ ] Opening a database whose `schema_version` is higher than the code's
      raises, and does not read any row.
- [ ] A truncated file and a non-SQLite file both raise the named exception
      with the path and the recovery in the message.
- [ ] Tests are pure — temporary directories only, no broker import, no
      network. Full suite green; `ruff check` and `ruff format --check` clean.
