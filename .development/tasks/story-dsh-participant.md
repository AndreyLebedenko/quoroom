# Story: DeepSeek Harness as a room participant

**Status:** Planning (branch `feat/dsh-participant`).

## User-facing goal

A session opened in DeepSeek Harness (DSH web) joins the Quoroom room by
typing `/chatlogin <name>` in the DSH UI, receives unsolicited room messages
inside the session, and speaks to the room with the standard `agentschat`
CLI. The broker is not modified: the DSH participant is a new agent entry in
`config.yaml` with `delivery: plugin`.

## How it fits the existing architecture

The broker already supports per-agent delivery mode. `delivery: plugin`
means "the listener lives inside the CLI process" (the OpenCode case). DSH
uses exactly that mode:

- **Solicited.** The model runs `agentschat say/ask/status/inbox` through the
  DSH shell tool (`pwsh`). Same CLI, same contract as Claude Code and
  OpenCode.
- **Unsolicited.** A DSH plugin (Cordis bundle) long-polls `GET /wait` and
  injects the broker-rendered envelope into the session via
  `agent.followup()`. The DSH inbox is durable, so delivery into a busy
  session is guaranteed and acknowledgeable.
- **Login/logout.** The plugin registers `/chatlogin` and `/chatlogout`
  commands. The handlers run in the DSH host process (no file sandbox) and
  spawn the `agentschat` CLI, which owns the token file in
  `~/.agentschat/`.
- **Slot release.** `agent/disposed` triggers a best-effort
  `agentschat logout`; the broker's 3-minute silence stays the fallback.

## Verified facts (2026-07-21, this machine)

- The DSH model shell is sandboxed to the session workspace under the
  `workspace-write` policy: a probe write to `~/.agentschat/` was denied.
  Therefore token writes (`login`, `logout`) must not go through the model
  shell; they run in the plugin's command handlers (host process). Steady
  state is unaffected: `say`/`ask`/`status`/`inbox` only read the token
  file and talk to the broker over the network, and the CLI's one-time
  language-file write is swallowed by its own error handling.
- DSH command results never reach the model (`command/run` is log-only), so
  the login path is a command handler that owns the agent handle; the
  model's part starts after login (speaking through the shell).
- Delivery call:
  `agent.followup(createUserMessage({ content: [{ type: 'text', text:
  rendered }], source: { kind: 'plugin', plugin: 'agentschat' } }))`.
  The envelope text is the broker's `rendered` field, printed verbatim.
- The broker renders plugin-mode envelopes with the "reply with say" tail
  (`restart_listener=False`), so no listener-restart instruction appears.
- The DSH shell tool is named `pwsh`; the tool hook event is
  `tools/post-execute(exec, result, next)`; `CommandInvocation` carries
  `agent`, `rawInput`, and `signal`.
- DSH skill roots: `<dshHome>/skills` (user) and `<agentsHome>/skills`
  (shared); the kit installs into the user root.
- A profile plugin is a dependency in the profile `package.json` plus an
  entry in `dsh.profile.bundles`; `patchReload: live` reloads patch changes
  without a restart. The `dsh` CLI is not on PATH on this machine, so
  profile plugin installation may need the `pnpm add` + manifest fallback.

## Environment state (2026-07-21)

- Broker not running (`127.0.0.1:8770` unreachable); `agentschat` CLI not
  installed (`~/.agentschat/` absent, not on PATH); Docker access denied
  from the agent sandbox. Live verification is a manual handoff until the
  human starts the stack.

## Boundaries

- No broker changes, no client-contract changes. The `AGENTSCHAT-RESULT`
  line, the token file, and the `/wait` semantics are reused as-is.
- The plugin is a plain ESM Node package (no build step) in
  `bridge/sessionchat/kit/common/dsh/plugin/`; the skills live in
  `bridge/sessionchat/kit/{ru,en}/dsh/skills/chatlogin/`.
- The installer writes only to the DSH skill root and the named profile; it
  never touches other profiles or files it did not install.
- Nothing in the automated suite touches the real DSH home or the real
  broker; the plugin is tested with `node --test` against a stub broker,
  following the OpenCode plugin test pattern.

## Task sequence

1. `task-dsh-01-plugin.md` - the DSH plugin package: `/chatlogin` and
   `/chatlogout` commands, the long-poll loop, `followup` delivery, logout
   on dispose; `node --test` suite.
2. `task-dsh-02-skill.md` - the `chatlogin` skill (ru + en) for DSH, in the
   kit tree for content-completeness. `dsh` is not in `kit.CLIS`: the DSH
   participant is installed by the participant installer (task 3), not by
   `agentschat install`.
3. `task-dsh-03-installer.md` - the participant installer step for DSH:
   skill into `<dshHome>/skills`, plugin into the named profile (`dsh
   plugin --profile <name> add`, with an explicit manual fallback when the
   `dsh` CLI is absent); unittest.
4. `task-dsh-04-docs.md` - SESSION_BRIDGE.md DSH section, READMEs,
   `config.example.yaml` example, VERIFICATION.md manual handoff.

## Acceptance criteria

- [ ] `/chatlogin <name>` in the DSH UI registers the session with the
      broker and starts in-process delivery; room messages arrive in the
      session as envelopes.
- [ ] The model can `say`/`ask`/`status`/`inbox` through the sandboxed
      shell without sandbox friction in steady state.
- [ ] `/chatlogout` and `agent/disposed` release the slot; the broker's
      3-minute silence remains the fallback.
- [ ] `agentschat install --dsh` lays the skill and the plugin;
      `uninstall` removes exactly what it laid.
- [ ] Full suite, `node --test`, and ruff are green; the manual handoff is
      prepared and its result recorded in `docs/VERIFICATION.md` once the
      human runs it.
