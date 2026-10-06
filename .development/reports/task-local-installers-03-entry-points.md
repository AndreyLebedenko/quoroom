# Report: task-local-installers-03-entry-points

**Branch:** `task/local-installers-03-entry-points` (from `feat/local-installers`)
**Base commit:** 4fca2f0
**Status:** third pass after review round 2, implemented and verified
automatically, not committed, no live check.

## Review round 2, item by item

1. **A launch failure never exits 0.** The probe now prints `sys.executable`, and
   the layer is started from that absolute path (the `-3` of the launcher is used
   for the probe only, because `CreateProcess` resolves nothing but `.exe`).
   `[System.Diagnostics.Process]::Start` is wrapped in `try`/`catch`; a failure
   prints the interpreter and the message and exits 9.
   `test_a_launcher_pointing_nowhere_never_exits_zero` puts a `python.bat` on
   `PATH` that names a path that does not exist and asserts the exit code is 9,
   never 0; `test_a_bat_launcher_naming_a_real_interpreter_reaches_the_layer` does
   the same with a `.bat` that names a real interpreter and asserts the layer
   runs.
2. **`$ErrorActionPreference = 'Continue'` is set explicitly**, so the caller's
   preference cannot turn a native stderr line into a terminating error.
   `NOISY_LAUNCHER` now writes to stderr (`1>&2`).
   `test_a_caller_with_stop_in_its_session_does_not_break_the_run` calls the
   script from a caller that sets `Stop` and makes the layer write to stderr and
   exit 1: the run must end 1, not something else.
   Honest limit: on this machine the behavioural tests do not fail when the
   explicit `Continue` is removed - 5.1 with `2>$null` on the probe line does not
   raise here. What pins the line is
   `test_the_windows_script_explicitly_survives_native_stderr`, which fails
   without it. The behavioural tests document the scenario; the assertion pins the
   rule.
3. **The Cyrillic POSIX test runs.** The review was right: it passes under Git
   `sh.exe` with both path forms. The skip and its false reason are gone. The
   round-1 diagnosis in the previous version of this report was wrong: `dirname`
   was simply absent from the restricted PATH, not "printing an empty string";
   the `dirname` shim stays, and its docstring now says why it exists (not every
   environment that has `sh` has `dirname` on `PATH`).
4. **The stray non-Russian characters are gone** from the test docstring.
5. **PYTHONPATH is replaced in both scripts**, as decided: the installer runs
   isolated from the user's value. `test_pythonpath_does_not_inherit_the_callers_value`
   on both platforms starts with a foreign `PYTHONPATH` and asserts the layer
   sees only `bridge/`. The POSIX helper no longer pops the variable.
6. **The comment above `Quote-Arg` is dropped**: the tests state the rules it
   described, and it attributed them wrongly.

## Mutation checks

| Bug put back | Result |
| --- | --- |
| `FileName` set to the bare launcher name instead of the absolute interpreter | 1 failure |
| `Start` called without `try`/`catch` | 17 failures |
| the probe stops printing `sys.executable` | 12 failures |
| `$ErrorActionPreference = 'Continue'` removed | 1 failure (the assertion that pins it) |
| `PYTHONPATH` prepended again in `install.sh` | 2 failures |
| the Cyrillic POSIX test replaced by nothing | the test fails |
| `Quote-Arg` bypassed, empty-value rule removed, trailing-backslash rule removed | 8 failures, 1 failure, 1 failure (from round 1, re-run) |
| `exit $process.ExitCode` replaced by `exit 0` | 5 failures |
| `PYTHONPATH` set in the caller's session | 13 failures |
| every UTF-8 knob removed | 1 failure on Windows, 7 on POSIX |
| the wrong prerequisite text back into `install.sh` | 2 failures |
| the layer check dropped in either script | 1 failure each |

Two mutations are not observable and are not defects: dropping `exec` in
`install.sh` (the script's exit status is the last command's either way) and
dropping `-X utf8` while `PYTHONUTF8=1` remains (UTF-8 mode is still on).

## Decisions

- **Exit code 9** for "Python not found", "the shared layer is missing" and "the
  interpreter named by the launcher does not start", in both scripts, asserted to
  be outside the core's codes.
- **Checked before Python**: only that `bridge/sessionchat/installer/__main__.py`
  exists.
- **The probe prints the interpreter**, so the launch never depends on what
  `CreateProcess` is willing to resolve. A `.bat` shim that names a real
  interpreter works; one that names a path that is not there exits 9.
- **Windows candidates** `py -3`, then `python`; **POSIX candidates** `python3`,
  then `python`. The version probe checks `sys.version_info >= (3, 10)`, and
  `VersionPinTests` reads `requires-python` from `bridge/pyproject.toml`.
- **PYTHONPATH is replaced** in both scripts.
- **BOM** on `install.ps1`, asserted by a test that runs on any platform.
- Accepted trade-off, as decided: PowerShell `*>` redirection does not capture the
  child's output. Task 08 must document it.

## Coverage of the acceptance criteria

| Criterion | Test |
| --- | --- |
| arguments pass through unchanged, including values with spaces | both platforms; Windows covers the empty value, an embedded quote and trailing backslashes |
| the exit code propagates, zero and nonzero | `test_a_successful_run_exits_zero`, `test_every_exit_code_of_the_core_passes_through` |
| the repository path with spaces and Cyrillic works | both platforms, on every run |
| the missing-Python path exits nonzero with the instruction and starts nothing | three tests per platform, including the approved prerequisite command |
| a launch failure is not exit 0 | `test_a_launcher_pointing_nowhere_never_exits_zero` |
| a test needing an absent shell skips with a stated reason | `pwsh` absent: "pwsh не найден в PATH: 7.x отдельно не проверен" |
| `install.ps1` tests run under `powershell.exe` 5.1, and `pwsh` when present | every Windows test runs through 5.1; the 7.x run skips with a reason |
| `install.sh` is POSIX `sh` | `sh -n` plus the banned-word list |
| Python output reaches the console as UTF-8 | `test_python_runs_in_utf8_mode` on both platforms |
| native stderr does not break the run | `test_a_layer_writing_to_stderr_keeps_its_exit_code`, `test_a_caller_with_stop_in_its_session_does_not_break_the_run` |

## What could not be tested here

- `pwsh` is not installed, so the 7.x run is skipped with a stated reason.
- The POSIX flow runs under Git Bash's `sh.exe` (bash in POSIX mode). `sh -n` and
  the banned-word list check it against POSIX `sh`; a real `dash` is not
  installed. Task 04's Ubuntu container is the native run.

## Verification, run from `bridge/` in order

- `.venv/Scripts/python.exe -m unittest discover -s tests -t .` - Ran 343 tests,
  OK, 1 skipped (`pwsh` absent, reason stated).
- The same suite from Git Bash - `Ran 343 tests ... OK`, the same one skip.
- `node --test tests/plugin/agentschat.test.mjs` - tests 4, pass 4, fail 0.
- `.venv/Scripts/ruff.exe check` - All checks passed.
- `.venv/Scripts/ruff.exe format --check` - 35 files already formatted.

`ruff` is not on PATH here, so it ran from the project virtualenv, version 0.16.6.

## Not done, by design

- No role, no step, no configuration logic in the shells.
- No change to `bridge/sessionchat/installer`, `pyproject.toml`, `docs/INSTALL.md`
  or `README.md`; the documentation of both entry points, including the `*>`
  redirection caveat, is task 08.
- No commit, per instruction. The task card status is untouched for the review.