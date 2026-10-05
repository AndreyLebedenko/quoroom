# Task local-installers-07: Server role removal and purge

**Status:** Completed (2026-10-04).
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

- [x] Tests for each requirement with mocked Docker and temporary
      directories, including cancel, partial install, repeat removal, and
      an unrecorded resource. These are the Windows functional flows of
      this role.
- [x] Test: the real role's discovery, run against a tree that holds every
      role's record, the saved bot passwords, and participant data, targets
      none of them.
- [x] Functional flow in the task 04 environment: remove keeps data and
      reinstall reuses it; confirmed purge removes only the server role's
      data; observations reported in the handoff.
- [x] Full suite, `node --test`, `ruff check`, `ruff format --check` green.

## Implementation notes

- Merged as 971c737. One design round, two code review rounds. The
  orchestrator made the last two review fixes itself (the confirmation text
  covers only roles that own a target; the log-removal command quotes
  paths) to save chat depth.
- Decisions taken in review:
  - The stop script stops the broker only (`-KeepDocker` /
    `--keep-docker`), in file-output mode, then `/status` is polled until
    silent. The stack goes down with `compose -f <repo>/docker/docker-compose.yml down`
    without `-v`.
  - The volume step is last. With the daemon down, files mounted into
    still-running containers and `docker/.env` are kept, and the run exits 1
    naming them. A repeat after Docker starts finishes.
  - A resource already absent counts as removed.
  - Broker state is an allow-list of the broker's own files, purged only
    when `continuwuity.toml` is in the server record.
  - On a hand-built server, removal takes the stack down and removes its
    containers and network. Everything else is kept and named.
  - Core change: `Role.purge_consequence` takes the purge targets, and
    `consequence_of` speaks only for roles that own a target.
- The functional lab run in tools/linux-container: remove keeps data,
  reinstall reuses it, `--role both --purge` removes both roles' data,
  and the repeats are clean. The daemon-down block of glm's report was not
  one verbatim run; the reviewer reproduced that path on the final code in
  scratch tests instead.
- glm first created a throwaway compose project on the host engine against
  the lab rule; the host was checked and left unchanged.
- Not verified live: the Windows removal on the human's stack, Element, a
  hand-built server, purge with a busy volume.
