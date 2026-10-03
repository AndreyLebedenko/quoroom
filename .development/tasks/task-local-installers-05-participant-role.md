# Task local-installers-05: Participant role

**Status:** Planned.
**Story:** `.development/tasks/story-local-installers.md`
**Depends on:** tasks 01-04.

## Summary

Install, removal, and purge of the participant role on top of the shared
layer: the `agentschat` CLI as a user tool, the client kit for the chosen
agent CLIs, and the broker address.

## Context you need

- Story: "Participant role", "Removal", gate item 1 (prerequisites) and the
  ownership rule for pre-existing resources.
- `docs/INSTALL.md` step 9: `uv tool install --editable`, pipx fallback,
  `uv tool update-shell`, `agentschat install` / `uninstall`, `--claude`,
  `--opencode`.
- `bridge/sessionchat/kit.py`: the kit manifest `~/.agentschat/kit.json`;
  `uninstall` keeps entries for files the user edited, and the manifest file
  is deleted only when it becomes empty.
- `~/.agentschat/<agent>.json`: broker tokens written by `agentschat login`.
- Task 01: `AGENTSCHAT_URL`.

## Boundary

- Participant steps in the shared layer and their tests. Reuse
  `uv`/`pipx` and `agentschat install` / `uninstall` as subprocesses; do not
  reimplement kit ownership.
- Never requires Docker or server configuration files.

## Requirements

- Prerequisites: Python per `requires-python`; `uv`, else `pipx`. A missing
  tool is a human step with the story's platform instructions.
- Install the package editable from this repository's `bridge/`; detect an
  existing installation and do not reinstall needlessly. Record in the
  participant ownership record that this run installed the package and with
  which tool; an installation found already present is not recorded.
- Invoke `agentschat` by the absolute path of the installed tool, so a fresh
  install works before PATH is updated. Separately check whether
  `agentschat` resolves on PATH; if not, print the platform command to fix
  PATH and that open sessions must be restarted.
- Run `agentschat install` with the human's choice of Claude Code, OpenCode,
  or both (an option, or a prompt when interactive). Its conflict refusal is
  reported as a conflict, not overridden.
- Broker address: option with default `http://127.0.0.1:8770`. With the
  default, nothing is written to the environment. With another value, print
  the exact command to set `AGENTSCHAT_URL` persistently for the platform;
  do not write it to profiles or the registry.
- Verify the broker answers at that address, as the story requires. An
  unreachable broker fails this verification step: nonzero exit, with the
  failure report naming the completed install steps and saying that a rerun
  after the server starts finishes the check. "Reachable, no session joined
  yet" is success, reported with the `/chatlogin` next step.
- Final report: what to restart, then the `/chatlogin` step.
- Removal: `agentschat uninstall` first, reporting files it keeps; then
  remove the package with the tool recorded as having installed it. A
  package not recorded is reported and kept.
- Purge, after confirmation: the participant role owns the client's own data
  in `~/.agentschat/` by definition, because the installed client creates
  it: the broker token files `<agent>.json`. The kit manifest is never
  deleted while it still has entries, because those entries protect files
  the user edited; `uninstall` already deletes it when empty. Any other file
  there is reported and kept.

## Acceptance criteria

- [ ] Tests for each requirement above with mocked subprocesses, network,
      a temporary home, and a temporary `UV_TOOL_DIR`; none touches the real
      home directory. These are the Windows functional flows of this role.
- [ ] Tests: repeat install changes nothing; install after a partial run
      continues; removal after a partial install works and is repeatable;
      purge with a kept edited kit file keeps `kit.json`.
- [ ] Functional flow in the task 04 environment: participant install,
      repeat, remove, purge; observations reported in the handoff.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
