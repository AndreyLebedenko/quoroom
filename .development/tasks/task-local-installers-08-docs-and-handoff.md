# Task local-installers-08: Documentation and live handoff

**Status:** Planned.
**Story:** `.development/tasks/story-local-installers.md`
**Depends on:** tasks 01-07.

## Summary

User documentation for the installers and the prepared human-run live
checks for Windows and the Linux container.

## Context you need

- Story: "Verification", "Acceptance criteria", "Handoff".
- AGENTS.md: `README.md` and `docs/` are Russian; VERIFICATION records what
  was run, what was observed, and the date.

## Boundary

- `docs/INSTALL.md`, `README.md`, `docs/ARCHITECTURE.md`, and
  `docs/VERIFICATION.md` (pending section only). No code.
  `docs/SESSION_BRIDGE.md` belongs to task 01.

## Requirements

- `docs/INSTALL.md`: both platforms, both roles, prerequisites per platform,
  the human steps (hosts, mkcert root CA) with exact commands, reruns,
  `--remove`, `--purge`, and what is retained. The manual procedure stays
  available as a fallback.
- README: links to `install.ps1` / `install.sh` and states the verified
  scope exactly: Windows, and Linux verified in an Ubuntu 24.04 container,
  not native Linux.
- `docs/ARCHITECTURE.md`: the installer as a new part (Russian): the shared
  layer and the two shells, the step model (state from checks, human steps),
  ownership records and the rule for pre-existing resources, purge
  confirmation before any destructive step, and the exit codes.
- `docs/VERIFICATION.md`: a pending handoff for the two live scenarios from
  the story (Windows, both roles; Linux container, both roles), each with
  the commands to run and what to observe. The Windows scenario follows the
  story's limits for the owner's live installation; the Linux scenario
  follows the story's live access path. Results are recorded only after
  the human runs them.

## Acceptance criteria

- [ ] Every command in the docs matches the implemented flags.
- [ ] The handoff is complete enough for the human to run it without this
      conversation.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
