# Task: DSH plugin package (cordis plugin, /chatlogin + /chatlogout)

Status: Completed
Story: story-dsh-participant.md
Branch: feat/dsh-participant

## Summary

A Cordis plugin package for DeepSeek Harness that joins a live DSH session to
the shared room. The plugin runs in the DSH host process (outside the model
sandbox), registers two handler commands, and owns the long-poll loop:

- `/chatlogin <name> [label]` runs `agentschat login --agent <name>
  [--label <label>]` in the host process, parses the `AGENTSCHAT-RESULT` line,
  and on success binds the agent name to the calling DSH agent and starts the
  poll loop. A `slot_taken` refusal with a stored token retries once with
  `--reconnect`.
- `/chatlogout [name]` runs `agentschat logout --agent <name>` and removes the
  binding on success. Without a name it unbinds the session of the calling
  agent.
- The poll loop reads `~/.agentschat/<name>.json`, long-polls
  `GET /wait?agent=<name>&token=<token>`, and delivers every broker-rendered
  envelope verbatim via `agent.followup()` as a user-role message with
  `source: {kind: "plugin", plugin: "agentschat"}`.
- `agent/disposed` releases the slot of the disposed agent (best-effort CLI
  logout). The last plugin instance to dispose stops all loops and releases
  all remaining slots (best-effort).

Tunables are validated config fields (env overrides for testability):
`brokerUrl`, `cli`, `retryMs`, `tokenlessLimit`, `loginTimeoutMs`,
`logoutTimeoutMs`, `waitTimeoutMs`. The plugin log is
`~/.agentschat/dsh-plugin.log`, English, no Cyrillic outside comments.

## Boundary

- `bridge/sessionchat/kit/common/dsh/plugin/` (package.json,
  cordis.patch.yml, src/index.js)
- `bridge/tests/plugin/dsh-agentschat.test.mjs`
- No changes to the broker, the client, kit.py, or the OpenCode plugin.

## Acceptance criteria

- `node --test bridge/tests/plugin/dsh-agentschat.test.mjs` passes.
- The plugin is dependency-free (node builtins only), ESM, no comments.
- Two sessions in one process bind under different names and do not disturb
  each other; a disposed agent releases exactly its own slot.
- A binding without a token file is dropped after the configured limit and
  never polls the broker without a token.
- A 409 from the broker drops the binding.
- The existing OpenCode plugin test still passes.
