# Changelog

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
- `agentschat install` and `agentschat login` print Russian text, so a
  participant install shows a Russian block inside an English run.
- Open bug reports are in `.development/bugreports/`.
