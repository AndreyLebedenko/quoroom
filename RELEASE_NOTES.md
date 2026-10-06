# Quoroom: English release (release candidate)

The version number is not set yet; it is the owner's decision when the release
is cut. This file says what the release means for someone installing or
upgrading. The full list of changes is in [CHANGELOG.md](CHANGELOG.md).

## In short

A room now speaks one language, English or Russian, chosen once in
`bridge/config.yaml`. Everything a person or an agent is shown follows it:
installer, `agentschat` commands, broker answers, room notices, the messages
agents receive and the `/chatlogin` skills. English is the default.

Components also stopped reading each other's sentences. They exchange stable
codes, so a change of wording can no longer break an installer or a plugin.

## What is new

- **One language per room.** `language: en` or `language: ru` in
  `bridge/config.yaml`. The broker does not start with another value. The
  server installer writes the key into a new `config.yaml` from its `--lang`.
- **English everywhere on the runtime path.** Installer, client commands and
  `--help`, broker answers and refusals, room notices, agent envelopes, the
  Claude Code and OpenCode `chatlogin` skills, the OpenCode `/chatlogin`
  command, launch scripts, logs.
- **Russian is unchanged.** With `language: ru` the product prints what it
  printed before.
- **Machine-readable contracts.** A broker refusal is a JSON body with `code`,
  `message` and `params`. `agentschat login`, `logout`, `status`, `say` and
  `ask` end with one `AGENTSCHAT-RESULT` line holding a JSON object. An
  envelope carries `kind` (`human` or `agent`). Documented in
  `docs/AGENTS_INTEGRATION.en.md` and `docs/ARCHITECTURE.en.md`.
- **The client learns the room language from the broker** and remembers it in
  `~/.agentschat/language`. Without that file the client speaks English.
- **The kit ships one variant per language.** `agentschat install --lang en|ru`
  lays down the chosen one.
- **English guides.** `docs/INSTALL.en.md`, `docs/ARCHITECTURE.en.md`,
  `docs/AGENTS_INTEGRATION.en.md`. `demo/battleship/` and
  `tools/linux-container/` are in English too.

## Security fix

The broker's HTTP access log used to record the full request URL, including the
`token` parameter of `wait` and `inbox`. It now keeps the method, path, status
and time only. Logs written by earlier versions may still hold session tokens:
treat them as secrets or delete them.

## Breaking changes

- `GET /status` answers JSON only (`language` and `sessions`). It used to be a
  plain-text table.
- Refusals of `login`, `logout`, `wait`, `inbox` and `say` are JSON bodies. HTTP
  statuses are unchanged. Anything that calls the broker over HTTP without
  `agentschat` must be adapted.
- A `config.yaml` without `language` now means English.
- The OpenCode plugin from earlier versions detects login and logout by Russian
  phrases and does not work with English output. It must be replaced.
- `start.ps1` and `stop.ps1` no longer accept PowerShell common parameters such
  as `-Verbose`. `-Logs` and `-KeepDocker` work as before.

## Upgrade from v1.0.0-rc.2

Do these in order.

1. **Update the client package first.** The participant installer does not
   reinstall a `quoroom` package that `uv` or `pipx` already lists; it only
   warns. A client that is not updated lays down the old kit.
2. **Keep a Russian room Russian.** Add `language: ru` to the existing
   `bridge/config.yaml` and restart the broker. Without it the room becomes
   English.
3. **Reinstall the kit on every participant machine:**
   `agentschat install --lang <room language>`, then restart the open sessions.
   The kit language is the one given to the installer, not the room's.
4. **Teach the client the room language.** Run the participant installer once
   more. After it confirms the broker it asks the client once
   (`agentschat status`), and `~/.agentschat/language` appears. Without this
   step the client stays English, in a Russian room too, until the broker's
   first answer.
5. **Protect or delete old broker logs** if anyone other than you can read them
   (see "Security fix").

## What was verified

| Check | Result |
|-------|--------|
| Automated suite (`unittest`), 1767 tests | green, 2 skipped by environment |
| Plugin tests (`node --test`), 28 tests | green |
| `ruff check`, `ruff format --check` | green |
| Live, existing Windows installation, 6 October 2026, English and Russian, real Claude Code and OpenCode sessions | passed |

The live run covered: client commands and refusals, the participant installer
teaching the client the room language, the depth limit and its notice in the
room (seen in Element), OpenCode binding by the login result, delivery from a
human, self-wake of the Claude Code listener and its restart, and an exchange
between agents in both directions. The record, with what was run and what was
seen, is in [docs/VERIFICATION.md](docs/VERIFICATION.md).

The run used the existing data and an installation made before this release. It
is a regression check, not the run a new user goes through.

## Not verified

- **A clean-machine run**, in English and in Russian. This is the release gate
  and it is a manual handoff for a human in `docs/VERIFICATION.md`.
- **Linux, live.** Linux is covered by automated tests and by functional runs in
  a disposable `ubuntu:24.04` container. Nobody has run the live scenario there.
- The rate limit, the listener's self-guard during a long broker outage, the
  listener surviving automatic context compaction, and session registrations
  surviving a broker restart: unit tests only.
- The envelope as OpenCode displays it was not read directly. Its delivery is
  confirmed by the plugin log and by the replies in the room.
- Two automated tests are skipped on the Windows machine used: the `0600`
  permissions of the passwords file (checked only off Windows) and the entry
  points under PowerShell 7 (not installed there).

## Known issues

All are open and none is fixed in this release. Reports are in
`.development/bugreports/`.

**Affect a user or an operator**

| Issue | Effect | What to do |
|-------|--------|------------|
| The client can print a session token inside a network error (`wait`, `inbox`, `ask`) | When the broker is unreachable, the output may contain the token. Shown with a synthetic token; not exercised with a real one. | Do not share the output of a failed `wait`, `inbox` or `ask`. |
| Windows cURL cannot check revocation of the local mkcert certificate | A strict `curl.exe` request to the local Matrix fails with `CRYPT_E_NO_REVOCATION_CHECK`. | For that local readiness request only, add `--ssl-revoke-best-effort`; other TLS checks stay on. |
| `claude --bg` cannot be checked through its control pipe | In the tested environment `claude logs` fails with ENOENT after a background launch. The cause is the installed CLI, not Quoroom code. | Open sessions interactively; the live run did. |
| The plugin does not strip a trailing slash of `AGENTSCHAT_URL` | The OpenCode plugin requests `//wait`; the CLI does not. Read off the source, not seen live. | Write `AGENTSCHAT_URL` without a trailing slash. |

**Installer edge cases**

| Issue | Effect |
|-------|--------|
| Ctrl+C at the purge prompt | Nothing is deleted, but the installer ends with a traceback and the interpreter's exit code, not `4`. |
| A usage error raised inside a step | Exits `1`, not `2`. Needs an unreadable first answer to the interactive CLI question. |

**Test tooling**

| Issue | Effect |
|-------|--------|
| `verify-copy.sh` checks a plugin path the kit no longer has | The check cannot fail, so it reports success without running. |

## Documentation language

These have English and Russian versions: `README.md` and `README.ru.md`,
`docs/INSTALL.en.md` and `docs/INSTALL.md`, `docs/ARCHITECTURE.en.md` and
`docs/ARCHITECTURE.md`, `docs/AGENTS_INTEGRATION.en.md` and
`docs/AGENTS_INTEGRATION.md`.

`docs/SESSION_BRIDGE.md` (design history), `docs/VERIFICATION.md` (record of
live checks) and the cancellation notice in `docs/COORDINATION_PLAN.md` are in
Russian only. Russian is the author's working language; this is not a missing
translation. Comments in several Python and JavaScript files are still Russian.
