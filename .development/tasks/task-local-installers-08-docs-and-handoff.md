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
  available as a fallback. State that a participant `--purge` deletes the
  broker token files of every agent even when `--claude` or `--opencode`
  narrows the removal (task 05 review, round 4; the confirmation lists
  them).
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
  follows the story's live access path. The lab's 443 guard reads the
  English state names of `netstat` (`LISTEN`/`LISTENING`); on a localized
  Windows only its Docker-ports check is reliable, so the handoff tells the
  human to stop the Windows stack first and confirm 443 is free. Results
  are recorded only after
  the human runs them.

## Acceptance criteria

- [ ] Every command in the docs matches the implemented flags.
- [ ] The participant's final report says what to restart and then the
      `/chatlogin` step (since task 05 the restart line comes from
      `agentschat install`'s own summary mid-run; check the human can still
      find it, and adjust the wording if not).
- [ ] A repeat participant `--remove` after the package is already gone
      does not say "вернуться в комнату можно новым входом": that wording
      depends on `Removal.package_gone`, which only the run that removed the
      package sets (task 05 review, round 6). Fix the wording with a test.
- [ ] The handoff is complete enough for the human to run it without this
      conversation.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
