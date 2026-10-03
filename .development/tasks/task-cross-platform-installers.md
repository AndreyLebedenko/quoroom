# Task: Cross-platform installation for servers and participants

**Status:** Planned; implementation is blocked on the implementation gate below.
**Story:** None. Standalone task.
**Depends on:** The per-user client kit (completed).

## Summary

Provide `install.ps1` for Windows and `install.sh` for Linux. A human runs
either entry point from a cloned Quoroom repository, selects the server or
participant role, and reaches a working installation without manually
coordinating several configuration files. Both entry points expose equivalent
choices, checks, and outcomes, including role-scoped removal.

This task covers the local scenario only: everything runs on one machine, as
the locality contract in `AGENTS.md` requires. The server role hosts the
Matrix infrastructure and broker. The participant role hosts the client kit
and the human's existing Claude Code or OpenCode sessions. The two roles stay
separate even on one host: each can be installed, verified, and removed on
its own, and a machine may have both.

## Context you need

- `AGENTS.md`, `README.md`, `docs/INSTALL.md`, `docs/SESSION_BRIDGE.md`,
  `docs/ARCHITECTURE.md`, and `docs/VERIFICATION.md`.
- `story-client-kit.md` and the existing `agentschat install` / `uninstall`
  implementation, including its ownership manifest and conflict handling.
- `bridge/pyproject.toml`, dependency lists, configuration examples, the
  packaged client kit, and the client and plugin connection settings.
- `start.ps1`, `stop.ps1`, `start.sh`, `stop.sh`, and the Docker configuration.
- Current source and verification records take precedence over assumptions
  about which planned broker features have already shipped.

## Approved direction

- Support Windows and Linux from the first installer release.
- Local scenario only: the server and participant roles run on the same host.
- The broker address is a parameter with a local default. Do not add code or
  tests that reject a non-local address: a shared deployment is a planned
  later extension, and it must be addable without reworking this installer.
  This task does not implement, document, or verify a shared deployment.
- Matrix access tokens stay with the broker only (locality contract, item 2).
  This is a security rule, not a locality rule, and it applies unchanged.
- Use a shared Python implementation for configuration, client-kit setup,
  preservation of existing installations, and diagnostics. Shell entry
  points handle prerequisite checks and platform-specific preparation.
- Reuse `agentschat install`; do not build a second kit ownership mechanism.
- Make system dependency installation and privileged operations explicit
  steps. Do not silently change system trust, hosts files, or firewall rules.
- Keep repeat runs safe and useful after a partial or completed installation.

## Implementation gate

Before implementation, the project owner must approve and the card must record:

1. The supported Windows shell and Linux distribution/version baseline, with
   the prerequisite installation procedure for each.
   - Windows: approved 2026-10-03. Windows PowerShell 5.1 is the minimum;
     `install.ps1` must also run unchanged on PowerShell 7.x, so it uses no
     construct that 5.1 lacks.
   - Linux: approved 2026-10-03. Ubuntu 24.04 LTS with Docker Engine and the
     Docker Compose v2 plugin. No native Linux machine is available, so both
     the functional flows and the live scenario run in a disposable
     `ubuntu:24.04` container paired with a `docker:dind` engine. The server
     role starts its stack inside that engine. Running the Linux server role
     against the host's Docker Desktop engine is forbidden: the compose file
     fixes `container_name` values and the project name derives from the
     `docker` directory, so it would act on the live Windows stack, and a
     purge would delete its room history. The live result is recorded as
     "Linux verified in an Ubuntu 24.04 container", not as native Linux:
     the hosts check, browser certificate trust, and apt prerequisites on a
     Linux desktop stay unverified.
2. How the installer handles privileged steps: the hosts entry for the server
   name (`docs/INSTALL.md`, step 1) and installing the mkcert root CA into the
   system trust store (step 2), on both platforms.
   - Approved 2026-10-03. The installer only checks these steps. When a check
     fails, it prints the platform-specific instructions for the human to
     perform them, stops with a nonzero exit code, and states how to resume.
     A repeat run re-checks them. The installer never performs them itself and
     never requests elevation.
3. The form of the broker address parameter.
   - Approved 2026-10-03. The CLI reads the full broker URL from
     `AGENTSCHAT_URL`, default `http://127.0.0.1:8770`, the same variable and
     default as the OpenCode plugin. `AGENTSCHAT_PORT` is removed, with no
     fallback. This client change is in scope for this task.

## Boundary

- Installation/removal entry points, shared setup logic, focused tests, and
  installation documentation only. The single exception is the CLI's broker
  address parameter (implementation gate, item 3).
- No changes to message routing, delivery guarantees, room membership models,
  or the client-broker protocol and its authentication.
- Out of scope: shared (multi-machine) deployment, remote broker support,
  TLS for the client-broker connection, participant credential distribution,
  mixed-OS setups, multi-room support, federation, macOS, public package
  publishing, and a general service manager.
- Do not install, authorize, or launch agent CLI sessions for the user.
- Reuse existing start/stop mechanisms where they meet the approved platform
  baseline. Surface missing platform support rather than hiding it in setup.

## Requirements

### Entry points and common behavior

- Provide an interactive role selection and equivalent documented parameters
  on both platforms. Allow installing both roles on one machine.
- Check prerequisites before modifying installation state. If Python is
  unavailable, the shell entry point identifies the missing prerequisite and
  the documented next step without invoking Python.
- Handle repository paths containing spaces and Unicode, and resolve project
  resources relative to the entry point rather than the working directory.
- Keep configuration generation and validation in the shared Python layer.
- Preserve existing configuration, credentials, and user-owned files. Explain
  conflicts and obtain explicit confirmation before replacing existing values
  or files; retain the kit installer's ownership and overwrite rules.
- Never print credentials in diagnostics or include them in generated examples.
- On failure, return a nonzero exit code, identify the failed step and any
  completed changes, and explain how to resume. Do not report partial setup as
  success or automatically remove existing state to recover.
- A repeat run must not duplicate accounts, rooms, kit registrations, or
  configuration entries. Interrupted setup must be detected and validated
  before continuation.

### Server role

- Check the supported Docker environment and broker prerequisites.
- Collect and validate the configuration values the server needs, including
  the broker address parameter with its local default.
- Prepare configuration from maintained examples and guide certificate,
  account, and room setup. Automate steps supported by existing mechanisms;
  clearly identify remaining human steps and verify their results.
- Start the infrastructure and broker using the supported lifecycle commands.
- Verify readiness of both infrastructure and broker before reporting success.
- Report the broker address the participant role must use, without exposing
  Matrix tokens.

### Participant role

- Install the client CLI and selected Claude Code / OpenCode kit using the
  existing package and kit installation mechanisms.
- Configure the broker address consistently for the CLI and the plugin, using
  the local default unless the human supplies another value.
- Verify that the broker answers at that address. Distinguish an unreachable
  broker from an agent session that has not yet joined the room.
- Require neither Docker nor server configuration files for this role, even
  when the server role is installed on the same machine.
- Report any required shell/session restart and the next `/chatlogin` step.

### Removal

- Support `--remove` in both entry points, with selection of the server,
  participant, or both roles. Keep removal logic in the shared Python layer.
- By default, remove role-owned installed software and integrations while
  preserving configuration, credentials, and room history. Stop the selected
  server's broker and containers before removal; retain its data volumes.
- Remove the participant kit through `agentschat uninstall` before removing
  its CLI package. Preserve its protection of user-modified files and report
  files left in place. Do not implicitly force their deletion.
- Do not remove system dependencies, shared certificates, unrelated settings,
  or resources still required by a retained role. Do not delete the repository.
- Support `--remove --purge` for explicit deletion of selected-role data,
  including configuration, credentials, and server data volumes containing
  room history. Show the exact resources and data-loss consequences and require
  explicit confirmation before destructive actions. Cancellation leaves state
  unchanged. `--purge` without `--remove` is invalid.
- Determine ownership before deletion; unknown ownership is a reported conflict,
  not permission to delete. Purging the participant role must not delete
  server data, and purging the server role must not delete participant state.
- Removal must work after a partial installation and be safe to repeat. Check
  only prerequisites needed for the requested cleanup, not those for a fresh
  installation. Report incomplete cleanup and retained resources accurately.

## Verification

Automated tests must use temporary installation roots and mocked system/network
boundaries; they must not modify the real home directory, trust store, hosts
file, or running Docker stack. Use the project's existing test tools.

Cover role selection, configuration validation, the broker address parameter
and its default, repeat runs, partial setup, conflicting files, missing
prerequisites, paths with spaces and Unicode, connection failures, credential
redaction, and propagation of failures through both shell entry points.
Include functional installation flows for each role and platform against
controlled dependencies. Run the full Python suite, the OpenCode plugin tests,
`ruff check`, and `ruff format --check`.

Cover removal of each role and both roles, partial installations, repeat
removal, retained-role dependencies, modified kit files, and default data
preservation. Test purge confirmation and cancellation, invalid flag
combinations, ownership conflicts, deletion boundaries, and cleanup failures.
Include functional removal and purge flows on both platforms using disposable
fixtures.

Prepare a human-run handoff for two live scenarios: Windows with both roles
on one machine, and Linux with both roles on one machine. In each, exercise
both supported agent CLIs outside the Quoroom repository and confirm
human-to-agent and agent-to-agent exchange in both directions. Re-run
installation and confirm existing configuration survives. On a disposable
installation, verify removal preserves data and reinstall can reuse it;
verify confirmed purge removes only the selected role's data.

Record actual versions, commands, observations, and dates in
`docs/VERIFICATION.md`. Automated success and a prepared handoff do not mean
the live scenarios have passed; retain that distinction in release claims.

## Acceptance criteria

- [ ] The implementation gate is resolved and recorded in this card.
- [ ] `install.ps1` and `install.sh` provide equivalent server/participant flows.
- [ ] Shared behavior has one Python implementation and reuses the client kit.
- [ ] The broker address is a parameter with a local default, applied
      consistently to the CLI and the plugin; nothing rejects a non-local value.
- [ ] Participant installation does not require Docker or expose Matrix tokens.
- [ ] Repeat and interrupted runs preserve existing state and report conflicts.
- [ ] Both entry points support role-scoped `--remove`, preserving data by default.
- [ ] Participant removal reuses `agentschat uninstall` and protects modified files.
- [ ] `--remove --purge` lists its targets and requires confirmation before changes.
- [ ] Removal and purge respect ownership and retained roles, including after
      partial installation; repeated removal is safe.
- [ ] Prerequisite and connection errors are actionable and never report success.
- [ ] Automated coverage and functional flows pass with no real-machine changes.
- [ ] All required project tests and style checks pass.
- [ ] `docs/INSTALL.md` documents both platforms, both roles, prerequisite and
      privileged steps, reruns, `--remove`, `--purge`, and retained data.
- [ ] README links to the installation entry points and states the verified
      platform scope. User-facing documentation remains Russian.
- [ ] The Windows and Linux live handoff is prepared; observed results are
      recorded separately from pending checks.

## Handoff

Report implementation and automated verification, outstanding human steps, and
the exact live-check procedure. Follow the repository review workflow before
closing the card or committing. Do not mark either platform as live-verified
until the human-run result is recorded.
