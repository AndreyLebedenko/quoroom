# Changelog

## Unreleased

Not yet versioned: the next version number is the owner's decision. This
section describes the English release; it becomes a version heading when the
release is cut.

### Added

- One language per room, set once in `bridge/config.yaml` with
  `language: en|ru`. English is the default, also when the key is absent. The
  broker refuses to start with any other value and reports the language in
  its answers. The server installer writes the key into a new `config.yaml`
  from its own `--lang` and never changes an existing file.
- Everything a person or an agent is shown follows the room language:
  broker answers and refusals, the notices posted into the room, the envelope
  agents receive, the `agentschat` commands and their `--help`, and the
  messages of `start` / `stop`, which fall back to the `language` key of
  `config.yaml` when `--lang` is not given. `register_account.py` follows only
  its own `--lang en|ru`; it never reads `config.yaml`. The Russian text is
  what the code printed before. The client learns the room language from the
  broker (see the entry on `~/.agentschat/language` below), and the kit follows
  the language given to the installer, not the room's (see the upgrade notes).
- Components exchange stable codes, not sentences. A broker refusal is a JSON
  body with `code`, `message` and `params`; `/status` reports a state code per
  session; an envelope carries `kind` as `human` or `agent` and the text the
  agent reads in `rendered`; `login`, `logout`, `status`, `say` and `ask` end
  with one `AGENTSCHAT-RESULT` line holding a JSON object. The installer and
  the OpenCode plugin read these codes and no longer match sentences. With
  `--json`, `agentschat install` (whose `--json` and `--lang` options are
  already in rc.2) now exits with code 5 when it refuses to overwrite foreign
  files; without `--json` it exits with code 1 as before.
- The client remembers the room language in `~/.agentschat/language`. The file
  is written only after the client has received its first JSON answer from the
  broker, and `agentschat install` does not write it; until then, and when it
  is absent, the client speaks English, including `--help` and a refusal to
  `say` without a login.
- The kit ships one variant per language (`en`, `ru`) plus the shared OpenCode
  plugin, and `agentschat install --lang en|ru` (already in rc.2) picks one.
  The Claude Code and OpenCode `chatlogin` skills and the OpenCode
  `/chatlogin` command exist in English.
- English guides: `docs/INSTALL.en.md`, `docs/ARCHITECTURE.en.md` and
  `docs/AGENTS_INTEGRATION.en.md`. The last two document the contracts above.
- A scan test that fails when Cyrillic appears in runtime code, scripts or
  templates outside the Russian catalogues, the Russian kit variant and a
  reasoned allowlist.
- A manual handoff in `docs/VERIFICATION.md` for the clean-machine run in
  English and in Russian.

### Changed

- `GET /status` answers JSON only (`language` and `sessions`); it used to be a
  plain-text table. Refusals of `login`, `logout`, `wait`, `inbox` and `say`
  are JSON bodies; the HTTP statuses are unchanged. Anyone calling the broker
  over HTTP without `agentschat` must adapt.
- `broker.log` and the OpenCode plugin log are English in every
  configuration.
- Store errors carry a code; at start a store failure is a single refusal in
  the room language, not a traceback.
- The comments of `docker/` and `bridge/config.example.yaml` are English.
  `start.ps1` and `stop.ps1` no longer accept PowerShell common parameters
  such as `-Verbose`; `-Logs` and `-KeepDocker` work as before.

### Upgrade notes

- An existing `bridge/config.yaml` without `language` now means English. A
  room that has been running in Russian needs `language: ru` added by hand,
  and the broker needs a restart.
- Update the client package first. The participant installer does not
  reinstall a `quoroom` package that `uv` or `pipx` already lists (it warns
  that the package may point to another copy of the repository or may not be
  editable). A client that is not updated lays down the old kit when you run
  `agentschat install`.
- The kit is a set of copies. On each participant machine run
  `agentschat install --lang <room language>` and restart the open sessions.
  The OpenCode plugin installed before this release decides that a session is
  logged in or out by Russian phrases and does not work with English output.
- The client's own language comes from `~/.agentschat/language`, which exists
  only after the first JSON answer from the broker and is not written by
  `install`. On an existing machine of a Russian room, `agentschat --help` and a
  refused `say` are English until the client has had its first contact with the
  broker.
- The language of the kit is the language given to the installer or to
  `agentschat install`, not the room's: the participant installer lays the kit
  down before it asks the broker. For a room in the other language run
  `agentschat install --lang <room language>` afterwards.

### Fixed

- `agentschat login` printed Russian text inside an English participant
  install; the sentences of every command now follow the room language.

### Known limitations

- The English run on a clean machine, and the Russian run that must match what
  was printed before this release, have not been recorded yet. They are a
  manual handoff for a human in `docs/VERIFICATION.md`.
- `docs/SESSION_BRIDGE.md` and `docs/VERIFICATION.md` are in Russian only,
  and so is the cancellation notice of `docs/COORDINATION_PLAN.md`; the README
  says so. Comments in several Python and JavaScript files are still Russian.
- The limitations of v1.0.0-rc.2 about the live Linux scenario and the
  untried broker-restart persistence still apply.

## v1.0.0-rc.2

### Added

- One-command installers: `install.ps1` (Windows) and `install.sh` (Ubuntu
  24.04) with `--role server|participant|both`, `--remove` and `--purge`.
  Steps are derived from checks, so a rerun continues where it stopped; steps
  only a human can do (hosts line, mkcert root, the human's account, the
  room) stop with exit code 3 and print the exact command.
- The installer is English by default; `--lang ru` (or `--lang=ru`) switches
  it to Russian. The flag also sets the language of the messages `install.ps1`
  and `install.sh` print before Python starts.
- Participant role: installs the `quoroom` client and the per-user kit
  (`agentschat install`) for Claude Code and OpenCode.
- The kit commands speak the language of the run: `agentschat install` and
  `agentschat uninstall` take `--lang en|ru`, and the participant installer
  passes its own `--lang` to the client. Under `--json` they answer with one
  document of codes, which is the same in both languages.
- Server role: Continuwuity, Element Web, Caddy with a local TLS certificate,
  the broker, accounts for the human and the bot agents.
- Removal and purge per role, with ownership records so the installer touches
  only what it created, and a confirmation word before any destructive step.
- Linux lab runner (`tools/linux-container`): a disposable Ubuntu 24.04
  container with its own Docker engine, for functional runs of the installer.
- The CLI reads the full broker URL from `AGENTSCHAT_URL`.
- `agentschat login --reconnect`, and several chat identities in one OpenCode
  process.
- `start.ps1` / `stop.ps1`, `start.sh` / `stop.sh`, `winstart.ps1`.
- Apache License 2.0, English `README.md` (Russian in `README.ru.md`).

### Changed

- Codex is no longer a room participant, and the poll delivery mode is gone.
- Only `@name`, an Element pill or `@room` addresses an agent.
- The first-generation bridge (`legacy/`) is removed from the tree. It remains
  in git history at the tag `v1.0.0-rc.1`.

### Fixed

- Messages were cut at their first newline.
- An unaddressed message reached nobody, silently.
- A session that is gone no longer holds its slot; the refusal says how long
  a slot stays taken.

### Known limitations

- The live Linux scenario has not been run by a human. Linux is verified by
  automated tests and functional runs in the lab container only. The Windows
  scenario was run by hand on 2026-10-05; see `docs/VERIFICATION.md`.
- Registrations surviving a broker restart are covered by unit tests only, not
  tried live; messages queued at restart are lost.
- `docs/` is written in Russian.
- `agentschat login` prints Russian text, so a participant install still shows a
  Russian block inside an English run. `agentschat install` and
  `agentschat uninstall` follow the language of the run.
- Open bug reports are in `.development/bugreports/`.
