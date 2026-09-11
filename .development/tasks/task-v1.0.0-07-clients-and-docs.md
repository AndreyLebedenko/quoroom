# Task v1.0.0-07: Clients, skills and release

**Status:** Not started.
**Story:** `.development/tasks/story-v1.0.0-pubsub-core.md`
**Depends on:** tasks 05 and 06.

## Summary

Bring every consumer onto the new contract — the CLI, both skill copies
and the OpenCode plugin — then run the live check and write the release down.
This is the task where the broker's change becomes visible to the agents.

## Context you need

- The story card in full, especially the scenarios: the skills describe to an
  agent what the scenarios require of it.
- `bridge/sessionchat/client.py`: `do_login`, `do_wait`/`poll_once`,
  `do_inbox`, `do_say`, `do_ask`, `do_status`.
- `.opencode/plugins/agentschat.js` and its test `agentschat.test.mjs`.
- The two identical skill copies: `.claude/skills/chatlogin/SKILL.md` and
  `.opencode/skills/chatlogin/SKILL.md`. They must stay consistent with each
  other. Task 00 removed the Codex copy under `.agents/`.
- `README.md` («Что уже работает», «Чего пока нет»), `docs/SESSION_BRIDGE.md`,
  `docs/VERIFICATION.md`.
- No explanatory comments in code (AGENTS.md, Core 7). `docs/`, `README.md`
  and the skills stay Russian — they are read at runtime, not by the build.
  Tests: `unittest` from `bridge/`; the plugin test is `node --test`.

## Boundary

- Client, plugin, skills, docs. No broker behaviour changes — if something is
  missing broker-side, stop and say so rather than patching it here.
- Do not add commands the story does not require.
- Do not rewrite the skills' hard-won warnings (slot ownership, no receipt
  acknowledgements, no restart loops). They are live-run scar tissue; adapt
  their wording to the new contract and keep every rule.

## Requirements

- CLI: `login` (unchanged surface), `topics`, `subscribe`, `wait`, `body`,
  `ack`, `say` (with the client counter), `status`, `logout`. `inbox` keeps
  its name and now lists references.
- The client owns two things on disk beside the token in
  `~/.agentschat/<agent>.json`: the send counter, and what it has already seen.
  An LLM session cannot be relied on to remember either across a wake-up or an
  autocompaction — so neither may live only in the agent's context.
- `say` retries with the **same** counter value after an ambiguous failure, and
  never renumbers on retry. This is the whole point of the counter.
- `wait` prints a reference; the session decides to fetch the body or ack it
  unseen. Keep the envelope text identical to what agents read today once the
  body is fetched.
- Plugin: same contract, same endpoints, no plugin-specific path.
- Skills: state that login subscribes to `@room` and one's own name
  automatically and that `/topics` and `subscribe` are for extra streams only;
  describe the fetch-or-ack decision, the send
  counter and retry rule, and what `delivered` means and does not mean. State
  plainly that a message is not confirmed until `delivered` arrives.
- `README.md`: «Чего пока нет» loses the in-memory registry line; «Что уже
  работает» gains durable delivery. `docs/SESSION_BRIDGE.md` describes the
  pub-sub model and why the previous single-queue model was replaced.
- Live check, recorded in `docs/VERIFICATION.md` in the style of the existing
  entries: two sessions connected; write into the room while the broker is
  down; restart it; confirm both resume and receive the downtime messages
  exactly once. Also exercise a `say` retry with the same counter and confirm
  one event in the room.

## Acceptance criteria

- [ ] CLI covers the full contract; every command has a test.
- [ ] Send counter and seen-set are files on disk, not agent memory, and
      survive a client process restart.
- [ ] A `say` retry with the same counter produces one room event; a test
      asserts it end to end.
- [ ] Plugin passes `node --test` against the new endpoints.
- [ ] Both skill copies are byte-identical to each other and carry every
      pre-existing warning, adapted in wording only.
- [ ] Skills state that a send is unconfirmed until `delivered`.
- [ ] `README.md` and `docs/SESSION_BRIDGE.md` describe the shipped model; no
      stale claim about in-memory state remains.
- [ ] The live check is recorded in `docs/VERIFICATION.md` with what was run,
      what was observed, and the date.
- [ ] Full suite green; `ruff check` and `ruff format --check` clean.
