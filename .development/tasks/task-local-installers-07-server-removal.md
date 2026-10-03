# Task local-installers-07: Server role removal and purge

**Status:** Planned.
**Story:** `.development/tasks/story-local-installers.md`
**Depends on:** task 06.

## Summary

`--remove` and `--remove --purge` for the server role, and for both roles
together, on top of the shared layer and the ownership records of task 06.

## Context you need

- Story: "Removal".
- `stop.ps1`, `stop.sh`, `docker/docker-compose.yml` (named volumes
  `continuwuity-data`, `caddy-data`, `caddy-config`).
- Task 05 removal, for the both-roles case.

## Boundary

- Server removal steps in the shared layer and their tests.

## Requirements

- Remove: stop the broker and the stack, remove the stack's containers and
  network, keep volumes, configuration, credentials, and certificates.
  Remove `bridge/.venv` only if the installer created it. Pulled images are
  kept and reported.
- Purge, after the confirmation of task 02: additionally the stack's named
  volumes (room history), `docker/.env`, `continuwuity.toml`,
  `config.yaml`, broker state under `bridge/state/`, and leaf certificates
  the installer generated. The mkcert root CA and the hosts entry are never
  touched; the report says they remain and how to remove them by hand.
- Discovery of broker state under `bridge/state/` never covers the server
  ownership record or the saved bot passwords: the passwords are recorded
  targets and would otherwise be listed and deleted twice. Keep the server
  record outside that directory.
- Only resources in the server role's ownership record are removed.
  Resources that existed before the first install run are not in it; they
  are reported as kept, with the reason, and never deleted.
- Both roles: participant removal never deletes server data and server
  removal never deletes participant state.
- Removal checks only what cleanup needs (for example, a stopped Docker
  daemon is reported, not a reason to refuse removing files), works after a
  partial install, and is safe to repeat.

## Acceptance criteria

- [ ] Tests for each requirement with mocked Docker and temporary
      directories, including cancel, partial install, repeat removal, and
      an unrecorded resource. These are the Windows functional flows of
      this role.
- [ ] Test: the real role's discovery, run against a tree that holds every
      role's record, the saved bot passwords, and participant data, targets
      none of them.
- [ ] Functional flow in the task 04 environment: remove keeps data and
      reinstall reuses it; confirmed purge removes only the server role's
      data; observations reported in the handoff.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
