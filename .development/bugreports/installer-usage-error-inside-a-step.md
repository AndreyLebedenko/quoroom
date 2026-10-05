# Installer: a usage error raised inside a step exits 1, not 2

**Detected at:** `feat/local-installers` 52337f7, during the review of task
local-installers-05 (2026-10-03).

## Symptoms

When a role step needs an answer it cannot read (for example an unreadable
answer to the interactive CLI question) and raises `UsageError`, the
installer reports a step failure and exits with 1 (FAILED). The same mistake
made on the command line exits with 2 (USAGE).

## Suspected cause

`execute` in `sessionchat/installer/steps.py` maps every exception from
`check`/`apply` to FAILED; only `Cancelled` and `NeedsHuman` have their own
outcomes. `UsageError` is not one of them.

## Temporary decision

Left as is. The participant role (task 05) no longer asks the question on a
repeat run, so the case needs an unreadable first answer. A test in
`test_installer_participant.py` pins the current exit code, so a change is
deliberate. Changing the core mid-story for a cosmetic exit code was judged
not worth a new review round of the core.

## Future considerations

Map `UsageError` inside a step to USAGE in `execute`, update the pinned test,
and keep the failure report (which step asked) in the output.
