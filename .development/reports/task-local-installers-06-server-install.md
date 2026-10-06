# Report: task-local-installers-06-server-install

**Branch:** `task/local-installers-06-server-install` (from `feat/local-installers`)
**Base commit:** 3e9d1c0
**Status:** review round 4: the last blocking item and the two cheap ones are
fixed and re-verified. Not committed.

Rounds 1 to 3 were returned; round 1 fixed six blocking items (B1-B6) and
thirteen non-blocking ones (N1-N13), round 2 fixed B2-B6 and its non-blocking
ones, round 3 fixed three more blocking items and the orchestrator's decision
about `config.yaml`, and round 4 fixes what round 3 found. Everything below was
produced by running the code as it stands now.

## Round 4

**A child must not read the caller's terminal.** `run_command` passed
`input=stdin` and, when no text was given, the child inherited the installer's
stdin. Nothing that runs here needs it: docker, mkcert, venv, pip and the start
scripts answer without stdin, and the broker the start script leaves behind is
better off with a closed one. A call without text now gives the child
`subprocess.DEVNULL`; a call with text still gets a pipe carrying exactly that
text. The function says so in its docstring, which is the one exception to the
no-comments rule: it is the contract of a shared function whose callers are
everywhere.

Tests: `subprocess.run` is inspected for the two modes (`DEVNULL` with no text,
`None` plus `input=` with text), and a child that reads stdin it was not given
returns promptly and reads `""`, with the assertion inside the temporary
directory. The old version of the last test claimed behaviour the code did not
have: it failed after 15 s in a terminal, passed under `/dev/null`, and its
marker assertion ran after the directory was already gone.

On Windows the mutant "the child's stdin is inherited again" survives the
end-to-end form of the test, because `patch("sys.stdin")` does not change the
handle a grandchild inherits there: both modes read `""` either way. The two
white-box tests kill it deterministically instead, and that is stated here
rather than papered over.

**The long-lived grandchild is now killed.** The child prints the grandchild's
PID, the test kills it (`taskkill /F` on Windows, `SIGKILL` elsewhere), waits
until the process list says it is gone and asserts it is. The grandchild also
gets `stdout=DEVNULL`, so it never inherits the log file handle. Nothing
outlives the test and the temporary directory is released, so no
`ignore_cleanup_errors` is needed any more.

**The helper closes its session.** `send` uses `with session() as http:` now, so
nothing is left open in the long-lived helper process; the test that records
calls through a fake session also asserts it was closed.

**The `-B` note.** The phantom syntax error did not recur once the stale
`__pycache__` was removed, so every check below runs with the documented
command and no `-B`. If it ever recurs, it is an environment problem to report,
not a reason to change the documented command.

## Verification

```
cd bridge
.venv/Scripts/python.exe -m unittest discover -s tests -t .              -> Ran 734 tests, OK (skipped=2)
.venv/Scripts/python.exe -m unittest tests.test_installer_server         -> Ran 193 tests, OK (skipped=1)
.venv/Scripts/python.exe -m unittest tests.test_installer_boundaries     -> Ran 21 tests, OK
.venv/Scripts/python.exe -m ruff check                                   -> All checks passed
.venv/Scripts/python.exe -m ruff format --check                          -> 40 files already formatted
node --test tests/plugin/agentschat.test.mjs                             -> 4 pass, 0 fail
```

The two skips are the machine: PowerShell 7 is not installed, and file mode
0600 cannot be checked on Windows.

### Mutation

Three mutants on the round-4 code, all caught:

| Mutant | Result |
| --- | --- |
| the child's stdin inherited again | killed |
| `input` no longer forwarded to the child | killed |
| the helper session left open | killed |

The lab was not run: nothing in this round touches a path that goes through it,
as agreed.

## What is not verified here

- **Windows.** `platform="windows"` is covered by unit tests only.
- **The no-echo password prompt** and **the interactive admin question**: both
  need a tty, which the lab has not.
- **Element in a browser**, and an existing server set up by hand beyond the
  unowned-TOML and unowned-config branches the fakes cover.
- **Server removal and purge** - task 07.

## Open items for the orchestrator

- `.development/bugreports/registration-token-first-account.md` still waits for
  task 08; `docker/continuwuity/continuwuity.toml.example` and `docs/INSTALL.md`
  step 3a stay untouched here (R3).
- `QUOROOM_ADMIN_PASSWORD` is inherited by every child process, the started
  broker included, for as long as the run lives: worth a line in task 08's docs.