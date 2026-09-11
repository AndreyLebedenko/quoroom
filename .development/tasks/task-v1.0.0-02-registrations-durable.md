# Task v1.0.0-02: Durable registrations

**Status:** Not started.
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
