# Task local-installers-03: Entry points install.ps1 and install.sh

**Status:** Planned.
**Story:** `.development/tasks/story-local-installers.md`
**Depends on:** task 02.

## Summary

`install.ps1` (Windows) and `install.sh` (Linux) in the repository root.
They find a suitable Python, check what must be checked before Python runs,
and hand every argument to the shared layer, returning its exit code.

## Context you need

- Story: gate item 1 (Windows PowerShell 5.1 minimum, must also run on 7.x;
  Ubuntu 24.04), "Entry points and common behavior".
- `start.ps1`, `start.sh`: existing style for the two shells.
- `pyproject.toml`: `requires-python`.

## Boundary

- The two scripts, their tests, nothing else. No configuration logic in the
  shells; anything beyond locating Python and passing arguments belongs to
  the shared layer.

## Requirements

- Resolve the repository from the script's own location, not the working
  directory. Paths with spaces and non-ASCII characters work.
- Find Python meeting `requires-python` (Windows: `py -3`, then `python`;
  Linux: `python3`). If none is found, print what is missing and the
  documented next step for that platform, and exit nonzero without
  invoking Python.
- Run the shared layer with `bridge/` on `PYTHONPATH`, pass all arguments
  through unchanged, and exit with its exit code.
- `install.ps1` uses nothing that Windows PowerShell 5.1 lacks (no `&&`,
  `||`, ternary, `??`). Windows PowerShell 5.1 reads a script without a BOM
  in the ANSI code page, so either save `install.ps1` as UTF-8 with BOM or
  keep it ASCII-only and leave Russian text to the Python layer.
- `install.sh` is POSIX `sh`, not bash.
- Python output reaches the console in UTF-8 on both platforms.

## Acceptance criteria

- [ ] Tests run each script with a stub shared layer and prove: arguments
      pass through unchanged, including values with spaces; the exit code
      propagates (zero and nonzero); the repository path with spaces and
      Cyrillic works.
- [ ] Tests prove the missing-Python path exits nonzero with the
      instruction and does not start Python.
- [ ] A test that needs a shell absent on the current machine is skipped
      with a stated reason, never silently passed.
- [ ] `install.ps1` tests run under `powershell.exe` (5.1); also under
      `pwsh` when present.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
