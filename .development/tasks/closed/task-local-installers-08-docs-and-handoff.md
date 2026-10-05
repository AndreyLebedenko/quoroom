# Task local-installers-08: Documentation and live handoff

**Status:** Completed.

**Completion note:** documentation and handoff delivered; reviewed over two rounds,
all findings fixed. Hand-verified live only on Windows: the owner
ran Windows scenario 1 on 2026-10-05 and reported it passed. The Linux live
scenario has not been run (no native Linux host); Linux is not recorded as
verified live. Linux scenario stays pending in `docs/VERIFICATION.md`. A one-letter
typo in the Docker daemon check step name was fixed in `server.py` during the
Windows run.

**Story:** `.development/tasks/story-local-installers.md`
**Depends on:** tasks 01-07.

## Summary

User documentation for the installers and the prepared human-run live
checks for Windows and the Linux container.

## Context you need

- Story: "Verification", "Acceptance criteria", "Handoff".
- AGENTS.md: `README.md` and `docs/` are Russian; VERIFICATION records what
  was run, what was observed, and the date.
- `.development/bugreports/registration-token-first-account.md` (task 06):
  continuwuity rejects the configured `registration_token` until the first
  account is created with the token it prints at first start.

## Boundary

- `docs/INSTALL.md`, `README.md`, `docs/ARCHITECTURE.md`, and
  `docs/VERIFICATION.md` (pending section only), and the comment on
  `registration_token` in `docker/continuwuity/continuwuity.toml.example`.
  Code only for the participant report wording items in the acceptance
  criteria (`participant.py` and its tests).
  `docs/SESSION_BRIDGE.md` belongs to task 01.

## Requirements

- `docs/INSTALL.md` step 3a and the `continuwuity.toml.example` comment
  match the first-account behaviour in the task 06 bugreport; close that
  bugreport.
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
  are recorded only after the human runs them.
- The Windows handoff also covers, from tasks 06-07:
  - the interactive admin name prompt and the no-echo password prompt,
    which the lab could not reach (no tty);
  - the owner's server is hand-built: the installer registers nothing and
    edits no config there, and open registration
    (`allow_registration = true`) stops every server run with exit 3 until
    the human closes it; say how;
  - `--role server --remove` on a hand-built server stops the stack and
    removes its containers and network, and keeps everything else;
  - `stop.ps1` finds the broker by command line machine-wide, so a removal
    run from another checkout stops the live broker; run the scenario from
    the live checkout only.

## Acceptance criteria

- [x] Every command in the docs matches the implemented flags.
- [x] The participant's final report says what to restart and then the
      `/chatlogin` step (since task 05 the restart line comes from
      `agentschat install`'s own summary mid-run; check the human can still
      find it, and adjust the wording if not).
- [x] A repeat participant `--remove` after the package is already gone
      does not say "вернуться в комнату можно новым входом": that wording
      depends on `Removal.package_gone`, which only the run that removed the
      package sets (task 05 review, round 6). Fix the wording with a test.
- [x] The handoff is complete enough for the human to run it without this
      conversation.
- [x] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
