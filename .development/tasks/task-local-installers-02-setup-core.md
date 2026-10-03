# Task local-installers-02: Shared setup core

**Status:** Planned.
**Story:** `.development/tasks/story-local-installers.md`
**Depends on:** nothing in code; read the whole story first, because every
later task builds on the interfaces defined here.

## Summary

The shared Python layer that both entry points call. It owns the command-line
contract, the step model, failure reporting, ownership records, credential
redaction, and confirmation. It contains no role-specific steps; tasks 05-07
add those on top of it.

## Context you need

- Story: "Entry points and common behavior", "Removal" (flag rules,
  ownership, purge confirmation).
- `bridge/sessionchat/kit.py`: the existing manifest and conflict handling;
  reuse its ideas, not its code paths for role state.
- AGENTS.md: SRP, no comments, `unittest` only, Russian runtime strings.

## Boundary

- A new package under `bridge/sessionchat/`, named for what it does; avoid
  `setup`, which reads as setuptools. No change to `client.py`, `kit.py`,
  or the broker.
- Standard library only. The participant role runs this layer with the
  system Python before any virtualenv or package exists, so it must import
  nothing outside the stdlib.
- Runnable as `python -m sessionchat.<package>` with `bridge/` on
  `sys.path`, independent of the working directory.

## Requirements

- Arguments: `--role server|participant|both`, `--remove`, `--purge`.
  Without `--role` and with an interactive stdin, ask the human to choose.
  Without `--role` and without an interactive stdin, fail with usage.
  `--purge` without `--remove` is a usage error. Role-specific options are
  added by later tasks through an extension point, not by editing a central
  list. Every interactive answer except a password also has an option, so a
  run can be fully non-interactive.
- `--role both`: install runs the server role first, so the participant's
  broker check can pass; removal runs the participant role first.
- Step model: a step has a check ("already done?") and an apply. A run
  checks each step, applies only what is not done, then re-checks it.
  State is discovered from checks, so an interrupted run is detected and
  validated on the next run without a separate progress file.
- A step can be a human step: it never applies; when its check fails, it
  prints the instruction for the human and stops the run (privileged steps
  from the story's gate item 2 use this).
- Failure report: the failed step, the changes this run completed, and how
  to resume. Exit code nonzero. Partial setup is never reported as success,
  and nothing is rolled back automatically.
- Ownership record: a role records the resources it created, at a location
  the role chooses and tests inject. Removal and purge act only on recorded
  resources; an existing resource without a record is a reported conflict.
- Redaction: secrets registered during a run (tokens, passwords,
  registration tokens) never appear in any output, including exceptions.
- Confirmation: destructive actions list the exact resources and the
  data-loss consequence, then require an explicit typed confirmation.
  Anything else cancels and leaves state unchanged. There is no flag that
  skips this confirmation.
- All system boundaries are injectable: filesystem roots, subprocess runner,
  network probe, stdin/stdout, environment.

## Acceptance criteria

- [ ] Each argument rule, including the invalid combinations, has a test.
- [ ] Tests prove: a completed step is not re-applied; an interrupted run
      resumes from checks; a failed step yields the failure report and a
      nonzero exit; a human step stops with its instruction.
- [ ] Tests prove a registered secret is absent from stdout, stderr, and a
      raised exception's text.
- [ ] Tests prove confirmation cancel leaves state unchanged and an
      unrecorded resource is reported, not deleted.
- [ ] A test proves the package imports only the standard library.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
