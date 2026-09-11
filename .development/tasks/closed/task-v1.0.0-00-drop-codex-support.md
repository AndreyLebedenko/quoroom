# Task v1.0.0-00: Drop Codex support and the poll delivery mode

**Status:** Completed (human review of 11 Sep 2026). Follow-ups from that
review: `AGENTS.md` Tooling note 4 now says the two skill copies differ by
design, and `docs/ARCHITECTURE.md` no longer lists `@codex` as a room member.
**Story:** `.development/tasks/story-v1.0.0-pubsub-core.md`
**Depends on:** nothing. Runs first, or in parallel with task 01. Everything
from task 02 onward assumes this is done.

## Summary

Remove Codex as a room participant and the `poll` delivery mode with it. This
is ground-clearing, not a feature: `poll` is the one mode that cannot carry the
ACK contract the rest of the story is built on, and every later task would have
to rewrite its exceptions before deleting them.

## Why (do not re-derive this)

A `poll`-mode agent is a subscriber that never acknowledges except when it
happens to speak. It has no liveness signal at all, so it is exempt from
`stale()`, needs its own branches in `state()` and `advice()`, gets its own
notice published into the room, and has its queue drained as a side effect of
`/say`. Six exceptions inside the delivery core. Task 04 requires all delivery
modes to carry one ACK contract; `poll` is the standing counterexample.

The capability is not lost: OpenCode runs as a plugin, a mode with real
delivery, and reaches the same models.

## Context you need

- `bridge/sessionchat/broker.py`: `Registration.polls` (~line 113) and its
  readers — `state()` (~135), `stale()` (~158), `advice()` (~173),
  `delivery_kinds` (~219-224), `on_message`'s `first_in_queue` notice (~338),
  `handle_say`'s `pending` (~550).
- `bridge/sessionchat/client.py`: `do_login`'s `poll` branch and `do_inbox`.
- `bridge/config.example.yaml`: the `codex` entry and its explanation.
- `README.md`: the delivery table and the "Ограничение Codex" paragraph.
- `docs/SESSION_BRIDGE.md`, `docs/ARCHITECTURE.md`, `docs/AGENTS_INTEGRATION.md`,
  `docs/INSTALL.md`, `docs/VERIFICATION.md` — each mentions Codex.
- `bridge/tests/test_sessionchat.py`, `bridge/tests/test_listener.py`.
- No explanatory comments — a rule worth stating is stated as a test
  (AGENTS.md, Core 7). Tests: `unittest`, from `bridge/`:
  `.venv/Scripts/python.exe -m unittest discover -s tests -t .`

## Boundary

- Deletion only. Do not restructure anything you are not deleting; the delivery
  core is rewritten in tasks 03-05 and this task must not front-run it.
- `inbox` / `drain()` stay — they are still the listener and plugin path until
  task 04 replaces them. Only the `poll`-specific behaviour goes.
- **Codex remains a coding agent working on this repository.** Only its
  participation in the room goes. Do not touch the `Codex` section of
  `AGENTS.md` beyond what is required below, and leave the 0.9 exception, the
  approval rules and `.agents/skills/` as a location alone.
- `bridge/config.yaml` is the human's local secret file. Update
  `config.example.yaml`; tell the human what to remove from theirs, do not
  guess at its contents.
- Do not delete anything under `bridge/live-checks/` — it is a record of what
  was run, and Codex appearing there stays true.

## Requirements

- Remove the `poll` mode: `Registration.polls`, every branch reading it, and
  `poll` from the accepted values of `delivery`. Accepted modes become
  `listener` (default) and `plugin`.
- Remove the room notice "сессия заберёт это при следующем обращении" and the
  `pending` payload from the `/say` response.
- Remove the `codex` agent entry from `config.example.yaml`, including the
  paragraph explaining the Unix-socket limitation. An unknown `delivery` value
  in a config must now fail loudly at startup rather than silently defaulting.
- `README.md`: drop the Codex row from the delivery table and the "Ограничение
  Codex" paragraph; the table keeps Claude Code and OpenCode.
- Move the app-server finding — the control socket exists only on Unix, and the
  desktop channel is occupied by the application itself, verified rather than
  read from documentation — into `docs/SESSION_BRIDGE.md` as the reason Codex
  is *not supported*. It stops explaining a mode and starts explaining a
  refusal. Do not delete it.
- Delete `.agents/skills/chatlogin/` — Codex reads `.agents/skills/` (the
  skill says so itself) and no longer joins the room. `.agents/` itself stays
  as Codex's skill location. Remaining copies: `.claude` and `.opencode`.
- Update those two: remove the poll-mode instructions ("listener запускать НЕ
  надо", "забери накопленное"). They stay identical to each other.
- Remove tests that exist only to cover `poll`. Tests that cover shared
  behaviour through a `poll` fixture are rewritten against `listener` or
  `plugin`, not deleted.
- Add a test asserting an unknown `delivery` value is rejected at startup.

## Acceptance criteria

- [x] No occurrence of `poll`, `polls` or `pending` as a delivery concept
      remains in `bridge/`.
- [x] `delivery: "poll"` in a config fails at startup with a message naming the
      accepted values; a test covers it.
- [x] `/say` no longer returns `pending`, and no room notice about deferred
      pickup can be produced.
- [x] `config.example.yaml` has no `codex` entry and still documents everything
      the broker reads and nothing more.
- [x] `README.md`'s delivery table has two rows, both verified live.
- [x] The Unix-socket finding is in `docs/SESSION_BRIDGE.md` as the reason for
      dropping Codex, with its "verified, not from documentation" standing
      intact.
- [ ] ~~`.agents/skills/chatlogin/` is gone; `.claude` and `.opencode` copies
      are byte-identical to each other and contain no poll-mode instruction.~~
      Closed by human decision of 11 Sep 2026: the two skill copies were never
      identical and are intentionally different (SESSION_BRIDGE.md said so all
      along); the byte-identical criterion was based on a stale picture of
      their contents. The `.agents/skills/chatlogin/` copy is deleted, and the
      only poll-mode instructions found in skills lived in the deleted copy.
      The `.claude` copy lost its `codex` mention; the `.opencode` copy did not
      mention Codex or poll. Note: `.agents/` itself disappeared with the
      skill because git does not keep empty directories; recreate it when a
      Codex skill actually appears.
- [x] `AGENTS.md` states that Codex works on the project but is not a room
      participant, and its `Codex` section is otherwise unchanged.
- [x] `bridge/live-checks/` is untouched.
- [x] Full suite green; `ruff check` and `ruff format --check` clean.
