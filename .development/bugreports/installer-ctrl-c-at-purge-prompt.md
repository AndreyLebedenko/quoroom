# Bugreport: Ctrl+C at the purge prompt does not give exit code 4

**Detected at:** d9ba9c4 (branch `task/local-installers-08-docs-and-handoff`,
code review of task 08, 2026-10-04)
**Status:** open, documented, not fixed here

## What the human sees

The purge question lists the targets and waits for the word `PURGE`. Pressing
Ctrl+C there does not cancel the run politely: Python raises `KeyboardInterrupt`,
nothing in the installer catches it, and the process ends with a traceback and
the interpreter's own exit code. On Windows that is `0xC000013A`, on Linux `130`.
The code for a declined purge is `4`, so a script that treats `4` as "declined"
and any other code as a failure sees a crash where a human decision happened.

## Cause

`main.py` asks for confirmation before the steps run and catches only
`Cancelled` (refusal, empty line, end of input) and `Exception`.
`KeyboardInterrupt` derives from `BaseException`, so neither arm matches, and
the failure path with code `4` is never reached. Nothing else is involved:
`Confirmation.ask` is a single `readline`, and the traceback is the default
`KeyboardInterrupt` report.

## Nothing is deleted

Read from the code, not inferred from a run: the confirmation is asked in
`main()` before `execute(...)` is called for any role, so no step of any role
has run at that point. `Confirmation.ask` only writes the list and reads a line.
So Ctrl+C at the prompt leaves the record and every file byte-identical, the
same as an explicit refusal - only the exit code and the output differ.

## Temporary decision

Task 08 documented the real behaviour in `docs/INSTALL.md` (section 3.2) and in
`docs/ARCHITECTURE.md` (the confirmation section): refusal, empty line and end
of input give `4` and change nothing; Ctrl+C changes nothing either but ends
with the interpreter's code and a traceback. The documentation does not promise
`4` for Ctrl+C anywhere.

## Future considerations

- The fix belongs to the core, not to a role: catching `KeyboardInterrupt` next
  to `Cancelled` in `main.py` would turn Ctrl+C into code `4` with the same
  message as a refusal, which is what a human means by it. It was left out of
  task 08 because that task's boundary is documentation plus two participant
  report strings.
- A script wrapping the installer should treat `0xC000013A` (Windows) and `130`
  (POSIX) at the purge prompt as a decline as well, until the core changes.
- The same code path exists for Ctrl+C at any interactive question of the
  installer (admin name, CLI choice), where there is nothing to delete but the
  exit code is equally unfriendly.
