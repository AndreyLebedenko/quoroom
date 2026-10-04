# Task local-installers-06: Server role install

**Status:** Completed (2026-10-04).
**Story:** `.development/tasks/story-local-installers.md`
**Depends on:** tasks 02-04.

## Summary

Install of the server role on top of the shared layer: prerequisites,
certificates, configuration, accounts, room, broker start, and readiness,
following `docs/INSTALL.md` steps 0-8 and automating what existing
mechanisms support.

## Context you need

- Story: "Server role", gate items 1 and 2, and the ownership rule for
  pre-existing resources.
- `docs/INSTALL.md` steps 0-8, `docker/.env.example`,
  `docker/continuwuity/continuwuity.toml.example`,
  `bridge/config.example.yaml`, `bridge/register_account.py` (prints the
  access token once and stores nothing), `start.ps1`, `start.sh`.
- AGENTS.md, locality contract item 3: secret locations; never print them.

## Boundary

- Server install steps in the shared layer and their tests. No change to
  the broker, the Docker stack, or the start/stop scripts.
- The task 02 stdlib-only rule covers the core and the participant role.
  Server steps that need PyYAML run after the virtualenv step, through the
  `bridge/.venv` interpreter; the system interpreter never imports PyYAML.

## Requirements

- Prerequisites: Docker CLI, running daemon, Compose v2, `mkcert`.
  Missing ones are human steps with the story's platform instructions.
- Human steps, checked and never performed (gate item 2): the server name
  resolves to loopback (hosts entry; print the exact line and file for the
  platform); the mkcert root CA is installed (print `mkcert -install` and
  that it needs administrator rights). Trust is confirmed by a TLS handshake
  with the system's default trust after the stack starts.
- Create `bridge/.venv` and install `requirements.txt` if absent.
- Generate the leaf certificate with `mkcert` into `docker/caddy/certs/` if
  absent.
- Create `docker/.env`, `continuwuity.toml`, and `config.yaml` from their
  examples when absent; generate the registration token. Existing files are
  validated, never overwritten without confirmation.
- The broker port is the start scripts' fixed 8770. If an existing
  `config.yaml` sets another `sessionchat_port`, report the mismatch with
  the start scripts as a conflict; do not edit the scripts.
- Accounts, in this order, before registration closes: the human's account
  (mandatory, because closing registration otherwise leaves the human
  unable to log in to Element; password read without echo, or from an
  environment variable for non-interactive runs, redacted), then the bot
  accounts. Bot passwords are generated and saved under `bridge/state/`
  before registering, so an account whose token was lost by an interrupted
  run is recovered by logging in with the saved password instead of
  registering again. Credentials are written into `config.yaml` without
  printing them. Then close registration and restart the homeserver.
- Room: a human step. Print what to create and whom to invite, then accept
  and validate the room id (`!` or `#` prefix, not a space) from a prompt or
  an option.
- Start the broker through the start script and confirm readiness of both
  the infrastructure and the broker before reporting success.
- Ownership record (server role): files this run created from examples, the
  generated certificates, the saved bot passwords, `bridge/.venv` if this
  run created it, and the compose project's volumes if they did not exist
  before this run. Pre-existing resources are not recorded.
- Final report: the participant's broker URL, no Matrix tokens.

## Acceptance criteria

- [x] Tests for each requirement with mocked Docker, subprocesses, network,
      and temporary directories; no real hosts file, trust store, or stack.
      These are the Windows functional flows of this role.
- [x] Tests: repeat run registers nothing twice and keeps existing files;
      a run interrupted after registration and before `config.yaml` was
      written recovers the token by login; secrets never appear in output.
- [x] Functional flow in the task 04 environment, with its room helper:
      server install, repeat; observations reported in the handoff. The
      human steps (hosts entry, `mkcert -install`) are performed the way the
      human would, through `tools/linux-container/run.sh exec-root`, never
      by the installer. Document `exec-root` in that directory's README.
- [x] Full suite, `node --test`, `ruff check`, `ruff format --check` green.

## Implementation notes

- Merged as fe68ab8. One design round with two revisions, then four code
  review rounds.
- Decisions taken in review:
  - The installer registers accounts and edits `continuwuity.toml` only
    when that file is in the server ownership record. On a hand-built
    server, a missing account or open registration is a human step.
    Accounts are never recorded.
  - Account existence is checked with `GET /register/available`.
  - The human registers first with the configured token. The token
    continuwuity prints at first start is read from the logs only after a
    401 "Invalid registration token", and only for that account.
  - Registration closure is the file value plus a probe with a wrong token
    (403).
  - Missing `user_id`, `access_token` and `device_id` are inserted under an
    agent the human declared, even in a `config.yaml` the installer did not
    create. Existing values other than `PASTE_` placeholders are a conflict.
  - Core additions in `boundaries.py`: `run(stdin=, output=)` with DEVNULL
    stdin by default, `resolve`, `secret`, `Probe.untrusted`. PyYAML and
    requests stay in `bridge/installer_host.py` under the venv.
- Room ids: fresh continuwuity issues `!opaque` ids with no server part;
  both forms are accepted and none is rewritten.
- Not verified live: Windows, the no-echo password prompt and the
  interactive name prompt (the lab has no tty), Element. These are left for
  the human's live scenarios in task 08.
