# Task v1.0.0-02: Durable registrations

**Status:** Implemented on branch `task/v1.0.0-02-registrations-durable`,
awaiting human review (2026-09-13).
**Story:** `.development/tasks/story-v1.0.0-pubsub-core.md`
**Depends on:** task 01.

## Summary

Put registrations through the store so they survive a broker restart, keep
`handle_login` atomic under concurrent logins, and rename the entity to what it
actually is.

## Context you need

- Story sections "Concurrency hazard this story introduces" and "Naming", and
  scenario S5.
- `bridge/sessionchat/broker.py`: the `Session` dataclass (~line 69),
  `handle_login` (~line 379), `handle_logout`, `session_of`.
- `bridge/sessionchat/client.py`: `do_login` and `stored_token` — the session
  side already persists its token to `~/.agentschat/<agent>.json`. **Do not
  change client.py in this task.**
- `bridge/sessionchat/store.py` from task 01.
- No explanatory comments — a rule worth stating is stated as a test
  (AGENTS.md, Core 7). Where this task rewrites code whose existing comments
  carry a rule, that rule becomes a test in the same change. Tests: `unittest`,
  from `bridge/`: `.venv/Scripts/python.exe -m unittest discover -s tests -t .`

## Boundary

- `bridge/sessionchat/broker.py` and `bridge/tests/`. Nothing else.
- Registrations only. Subscriptions, queues and ACK are tasks 03-05; do not
  anticipate them beyond calling the store functions that already exist.
- Do not touch `on_message`, `publish`, `handle_say`, the depth limit or the
  rate limit.
- Do not change the wire protocol except where a restart previously produced a
  wrong answer.

## Requirements

- Rename `Session` → `Registration` and its field `since` → `registered_at`
  throughout `broker.py` and the tests. `last_contact` and `last_delivery` stay
  for now; task 05 removes them with `stale()`.
- Database path constant in `broker.py`, under `bridge/state/`. Not a config
  key.
- On startup: load registrations from the store into `self.sessions`. Restore
  `registered_at` and `depth` verbatim; never stamp them with the current time.
  `open_waits`, `listening_until`, `signal` and `inbox` start empty — a
  restored registration is not a live session, and `status` must not report one
  as listening.
- `handle_login` (new registration) writes the row via `insert_registration`
  and the write commits **before** the response carrying the token is built.
- `handle_login --reconnect` against a restored registration verifies the token
  and returns it, exactly as it does today for an in-memory one. Its branch
  currently requires `existing is not None`, so against an empty registry it
  silently creates a fresh registration with a new token — with restore in
  place that path becomes rare, but keep the behaviour honest: if no
  registration exists, say so plainly rather than reporting a reconnect.
- `handle_logout` (both forms) and slot release through `stale()` delete the
  row.
- **Atomicity.** `handle_login` is atomic today only because there is no
  `await` between reading and writing `self.sessions`. The store write
  introduces one. Guard the section — a per-agent `asyncio.Lock`, or treat
  `insert_registration`'s conflict exception as the authority — so that
  concurrent logins for the same agent produce exactly one registration and the
  loser gets the existing refusal.

## Acceptance criteria

- [ ] `Session` → `Registration`, `since` → `registered_at`; no occurrence of
      the old names remains in `bridge/`.
- [ ] A broker constructed over a store with existing rows restores them:
      `registered_at` and `depth` are byte-identical, `inbox` is empty, and
      `status` reports `НЕ СЛУШАЕТ` for every restored registration.
- [ ] A restored registration accepts `--reconnect` with the matching token and
      refuses a different one with the existing message.
- [ ] `--reconnect` when no registration exists reports that plainly instead of
      returning `reconnected`.
- [ ] The token row is committed before the login response is produced (a test
      that fails the response path still finds the row).
- [ ] Concurrent logins: a test fires N parallel `handle_login` calls for one
      agent and asserts exactly one succeeds, the others are refused, and the
      store holds one row.
- [ ] `handle_logout`, `logout --force` and `stale()` release each remove the
      row.
- [ ] Existing tests still pass unchanged in meaning; full suite green;
      `ruff check` and `ruff format --check` clean.

## Implementation notes (2026-09-13, after review fixes)

- `Registration` restore, store path constant, per-agent lock, honest
  `--reconnect` refusal: as planned. `session_of` was also renamed to
  `registration_of` and `self.sessions` to `self.registrations` — beyond the
  card's letter ("load into `self.sessions`"), accepted deliberately as the
  same rename carried to its consumers.
- **Depth is not persisted on delivery** in this task: the row is written with
  `depth=0` at login, and `handle_wait` keeps updating the in-memory copy
  only. "Restore `depth` verbatim" therefore always restores 0 until task 04/05
  make delivery write through. The restore-verbatim test seeds the row by hand
  to exercise the mechanism.
- **Known limitation, deferred to task 05 by design**: a restored registration
  has `last_contact = last_delivery = listening_until = 0`, so `stale()` counts
  from `registered_at`. Any registration restored more than STALE_SECONDS
  (180 s) after its last contact is treated as stale on the next login: a
  fresh login takes the slot (200), and `--reconnect` gets "не к чему". S5 for
  sessions older than 180 s does not work yet. Both reconnect tests above pass
  because they restart within milliseconds of the login; the stale-release
  tests age the registration manually. Do not mistake this for S5 working.
- **Sync SQLite in the event loop is accepted for this task**: login, logout
  and stale release are rare, off the notification path (the story's stop
  condition on latency covers this), and the write is one small statement.
  `_store_write` is `async` so task 03 can add a real suspension point inside
  the critical section without changing call sites.
- The parallel-login test suite has two layers: the plain N-parallel test,
  and a test that puts a real `await`-switch inside the critical section
  (a `_store_write` that sleeps before writing, emulating task 03's seed).
  The second is the one that fails if the lock or the `DuplicateAgent` branch
  is removed: winners must get 200, every loser 409 (not 500), and the winner's
  response token must equal the store row and the in-memory registration.
- Store-first ordering everywhere: logout and stale release write the deletion
  before popping memory, so a failed store write never resurrects a
  registration after restart; `DuplicateAgent` from `insert_registration` is
  handled explicitly — the stored row is re-read into memory and the login is
  refused 409 instead of 500.
