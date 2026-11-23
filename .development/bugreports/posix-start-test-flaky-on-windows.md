# test_a_fresh_broker_is_started_and_the_progress_is_told is flaky on Windows

**Detected:** 2026-11-23, commit 1d18032 plus the uncommitted task-tray-02
tree (branch feat/tray-launcher), by the opencode reviewer.
**Status:** Open.

## Symptoms

`StartPosixTests.test_a_fresh_broker_is_started_and_the_progress_is_told`
(start.sh, bridge/tests/test_launch_scripts.py) fails with
`PermissionError [WinError 32]` while removing its temporary directory. It
fails in a full `unittest discover` run roughly every other time, and passes
when run alone. The reviewer reproduced it on an untouched tree in two
separate reviews (task-tray-01 and task-tray-02). The lead's full runs on the
same day passed (1825 and 1969 tests).

## Suspected current cause

The reviewer's reading: a background `sleep` started by the fake broker
under `sh` still holds the temporary directory as its working directory when
the test's cleanup runs `rmtree`. Not confirmed.

## Temporary decision

Not fixed in the tray story: it does not touch start.sh or the POSIX tests,
and the failure is in cleanup, not in the behaviour under test. A full run
with only this error is treated as green for tray tasks.

## Future considerations and boundaries

Make the fake broker's background process end (or be killed) before cleanup,
or run it with a working directory outside the temporary tree. Confirm by
looping the full suite. Do not weaken the assertion of the test itself.
