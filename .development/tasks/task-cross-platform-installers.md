# Task: Cross-platform installation for servers and participants

**Status:** Planned; implementation is blocked on the connection contract below.
**Story:** None. Standalone task.
**Depends on:** The per-user client kit and an approved, implemented remote
client-broker connection contract.

## Summary

Provide `install.ps1` for Windows and `install.sh` for Linux. A human runs
either entry point from a cloned Quoroom repository, selects the server or
participant role, and reaches a working installation without manually
coordinating several configuration files. Both entry points expose equivalent
choices, checks, and outcomes, including role-scoped removal.

The server hosts the Matrix infrastructure and broker. A participant machine
hosts the client kit and the human's existing Claude Code or OpenCode sessions.
Docker is required only for the server role. One machine can have both roles.

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
- Offer local and shared deployment scenarios explicitly.
- Use a shared Python implementation for configuration, client-kit setup,
  preservation of existing installations, and diagnostics. Shell entry
  points handle prerequisite checks and platform-specific preparation.
- Reuse `agentschat install`; do not build a second kit ownership mechanism.
- Make system dependency installation and privileged operations explicit
  steps. Do not silently change system trust, hosts files, or firewall rules.
- Keep repeat runs safe and useful after a partial or completed installation.

## Implementation gate

Before implementation, the project owner must approve and document:

1. The remote broker address and discovery/configuration mechanism used by
   both the CLI and the OpenCode plugin.
2. TLS termination and certificate trust for the client-broker connection,
   including the distinction between local and shared deployments.
3. Participant authentication and its binding to permitted agent identities,
   including how a participant obtains credentials without Matrix tokens.
4. The supported Windows shell and Linux distribution/version baseline,
   with the prerequisite installation procedure for each.

Remote broker support must exist and have a documented verification result
before this task configures it. HTTPS access to Element or Matrix alone does
not satisfy this prerequisite. The current single-machine locality contract
in project documentation must be revised explicitly for the approved shared
deployment model. This task does not choose or implement that model.

## Boundary

- Installation/removal entry points, shared setup logic, focused tests, and installation
  documentation only.
- No changes to message routing, delivery guarantees, room membership models,
  or the client-broker authentication protocol.
- Multi-room support, federation, macOS, public package publishing, and a
  general service manager are outside this task.
- Do not install, authorize, or launch agent CLI sessions for the user.
- Reuse existing start/stop mechanisms where they meet the approved platform
  contract. Surface missing platform support rather than hiding it in setup.

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
- Collect and validate the deployment mode, address, and configuration values
  required by the approved connection contract.
- Prepare configuration from maintained examples and guide certificate,
  account, and room setup. Automate steps supported by existing mechanisms;
  clearly identify remaining human steps and verify their results.
- Start the infrastructure and broker using the supported lifecycle commands.
- Verify readiness of both infrastructure and broker before reporting success.
- Provide the participant connection details without exposing Matrix tokens.

### Participant role

- Install the client CLI and selected Claude Code / OpenCode kit using the
  existing package and kit installation mechanisms.
- Configure the chosen server and participant credentials through the approved
  connection contract, consistently for the CLI and plugin.
- Verify connectivity, certificate trust, and authentication. Distinguish these
  failures from an agent session that has not yet joined the room.
- Require neither Docker nor server configuration files on this machine.
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
  not permission to delete. Purging a participant must not delete server data
  or another participant's state.
- Removal must work after a partial installation and be safe to repeat. Check
  only prerequisites needed for the requested cleanup, not those for a fresh
  installation. Report incomplete cleanup and retained resources accurately.

## Verification

Automated tests must use temporary installation roots and mocked system/network
boundaries; they must not modify the real home directory, trust store, hosts
file, or running Docker stack. Use the project's existing test tools.

Cover role selection, configuration validation, repeat runs, partial setup,
conflicting files, missing prerequisites, paths with spaces and Unicode,
connection failures, credential redaction, and propagation of failures through
both shell entry points. Include functional installation flows for each role
and platform against controlled dependencies. Run the full Python suite, the
OpenCode plugin tests, `ruff check`, and `ruff format --check`.

Cover removal of each role and both roles, partial installations, repeat
removal, retained-role dependencies, modified kit files, and default data
preservation. Test purge confirmation and cancellation, invalid flag combinations,
ownership conflicts, deletion boundaries, and cleanup failures. Include
functional removal and purge flows on both platforms using disposable fixtures.

Prepare a human-run handoff for all four installation scenarios: Windows server,
Windows participant, Linux server, and Linux participant. Include a local
server-plus-participant setup and a mixed-OS shared deployment with agents on
different machines. Exercise both supported agent CLIs outside the Quoroom
repository and confirm human-to-agent and agent-to-agent exchange in both
directions. Re-run installation and confirm existing configuration survives.
On a disposable installation, verify removal preserves data and reinstall can
reuse it; verify confirmed purge removes only the selected installation's data.

Record actual versions, commands, observations, and dates in
`docs/VERIFICATION.md`. Automated success and a prepared handoff do not mean
the live scenarios have passed; retain that distinction in release claims.

## Acceptance criteria

- [ ] The implementation gate is resolved and linked to approved project docs.
- [ ] `install.ps1` and `install.sh` provide equivalent server/participant flows.
- [ ] Shared behavior has one Python implementation and reuses the client kit.
- [ ] Local installation and shared deployment follow the approved contract.
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
- [ ] The four-scenario and mixed-OS live handoff is prepared; observed results
      are recorded separately from pending checks.

## Handoff

Report implementation and automated verification, outstanding human steps, and
the exact live-check procedure. Follow the repository review workflow before
closing the card or committing. Do not mark either platform as live-verified
until the human-run result is recorded.
