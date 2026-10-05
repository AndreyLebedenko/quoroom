# Task local-installers-01: CLI reads the full broker URL

**Status:** Completed (2026-10-03).
**Story:** `.development/tasks/story-local-installers.md`
**Depends on:** nothing.

## Summary

The `agentschat` CLI takes the broker address from `AGENTSCHAT_URL`, the same
variable and default the OpenCode plugin already uses. `AGENTSCHAT_PORT` is
removed with no fallback.

## Context you need

- Story, implementation gate item 3.
- `bridge/sessionchat/client.py`: `port()` and `base()` build
  `http://127.0.0.1:<AGENTSCHAT_PORT or DEFAULT_PORT>`.
- `bridge/sessionchat/kit/opencode/plugins/agentschat.js`: `BROKER` reads
  `AGENTSCHAT_URL`, default `http://127.0.0.1:8770`.
- `bridge/sessionchat/protocol.py`: `DEFAULT_PORT`.

## Boundary

- `client.py`, its tests, and documentation that mentions the CLI's address
  variable, including `docs/SESSION_BRIDGE.md` (AGENTS.md, project context
  item 2: same commit). No broker change, no plugin behavior change.
- Nothing may reject a non-local URL.

## Requirements

- `AGENTSCHAT_URL` unset or empty: the CLI uses `http://127.0.0.1:<DEFAULT_PORT>`.
- `AGENTSCHAT_URL` set: the CLI uses it as the base URL. A trailing `/` does
  not produce `//` in request paths.
- `AGENTSCHAT_PORT` is no longer read anywhere.
- Any refusal or diagnostic that names the broker address shows the URL
  actually in use.
- The CLI default and the plugin default are the same URL. Enforce this with
  a test that reads the plugin source, not with a comment.

## Acceptance criteria

- [x] Tests: default URL; override; trailing slash; a non-local URL accepted.
- [x] Test: the CLI default equals the plugin's `BROKER` default.
- [x] No reference to `AGENTSCHAT_PORT` remains in code, kit, or docs.
- [x] Full Python suite, `node --test`, `ruff check`, `ruff format --check` green.
