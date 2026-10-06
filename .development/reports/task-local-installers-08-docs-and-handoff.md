# Task local-installers-08: Documentation and live handoff

Status: implemented, not committed, waiting for review. Branch
`task/local-installers-08-docs-and-handoff` from `feat/local-installers`
(d9ba9c4, which carries task 07 as 971c737 merged as e6b66dd). No design stage
for this task. Two review rounds; this file describes the second round's state.

## Round 2: what the review returned and what changed

B1. The scope claim is now exact, in `README.md`, `docs/VERIFICATION.md` and in
this report: the installer has automated tests on both platforms and
functional runs by an agent in a disposable `ubuntu:24.04` container with its
own `docker:dind` engine; nothing of the installer is verified live; both live
scenarios are pending. "Проверено на Windows" appears nowhere. The bridge's own
Windows verification stays where it was, pointing at
`docs/SESSION_BRIDGE.md`.

B2. `README.md` no longer says both `--remove` and `--purge` require
confirmation. A plain removal asks nothing; only `--purge` lists its targets and
waits for the word.

B3. Ctrl+C does not give code `4`, and the docs now say so: a refusal, an empty
line and end of input give `4`; Ctrl+C changes nothing either (read from the
code: the confirmation is asked before any step runs) but ends with the
interpreter's code and a traceback. Bugreport
`.development/bugreports/installer-ctrl-c-at-purge-prompt.md` records it, with
the reason `KeyboardInterrupt` is not caught by `main.py` and the note that the
fix belongs to the core.

B4. `docs/INSTALL.md` 3.4 now says that a purge on a hand-built machine still
stops the broker and takes the stack down, because `--purge` implies `--remove`.
Code `0` there means "no targets, stand stopped", and `start.ps1` brings it
back.

B5. `docs/ARCHITECTURE.md` now states that `state` and `session` are never
written to a record - they are found kinds - and names both finds: the broker's
own files (only next to a recorded `continuwuity.toml`) and the participant's
`~/.agentschat/*.json` with a `token` key. The record kinds are listed without
the two found ones.

B6. The Ubuntu trust command is `sudo env CAROOT="$(mkcert -CAROOT)" mkcert
-install`, run from the user's shell: in a root shell the substitution returns
root's own CAROOT, which is the failure the comment warns about. That is the
form the installer prints.

B7. `continuwuity.toml.example` no longer says the token is used for all three
accounts - the first account uses the server's own; its cross-references now
say 1.5 and 5.4, and `docs/INSTALL.md` points the room at 1.4 and the config
file at 5.4.

B8. The Windows handoff is rewritten around what the code actually does on the
owner's machine: step 1 expects code `3` at "Закрыть регистрацию" because
`allow_registration` is open there, then the toml fix and a rerun; step 2 is the
repeat; step 3 is the name prompt, reachable with no `--admin-user`, and no
password follows because the account exists; step 4 is a separate step that
calls the project's own secret boundary by hand - the command comes from
`boundaries.py` and was run here with piped input: `getpass` never consumes the
piped line (it waits for the console), so the human runs it in a live console
and sees that nothing is typed; step 7 now removes, repeats the removal and
reinstalls, and expects the hand-installed `quoroom` package to stay with the
reason in the report; step 8 drops `server-accounts.json` from the expectation
because the hand-built machine has none; step 9 ends with `start.ps1` up.

B9. The Linux handoff is reordered and complete: stop the Windows stack, confirm
443 is free with `Get-NetTCPConnection -State Listen` (the lab's guard reads
English `netstat` states, and the note moved here), `./run.sh up
--publish-443` from Git Bash, then hosts, then the first installer run - which
issues the certificate - and only then `CAROOT=... mkcert -install` via
`exec-root`, because the reverse order makes root create the CA in the lab's
CAROOT. The room is created by the human in Element over the published 443, not
by `room-helper.py`. The exchange is done without `claude` and `opencode`:
`agentschat login --agent claude-code` with an explicit `AGENTSCHAT_URL`, then
`agentschat wait`, while the human writes and answers in Element, plus a
one-off `agentschat say`. The reinstall passes `--admin-user labadmin`. Purge is
done one role at a time - server first, with the participant's `~/.agentschat`
and `agentschat status` shown to survive, then the participant, then a repeat.

B10. `test_the_report_names_the_restart_before_the_chatlogin_step` now asserts
on the last line of the report - the one that carries `/chatlogin` - instead of
searching the whole output, where `agentschat install`'s own mid-run summary
answered first. A second test pins that the restart line names only the chosen
CLI. Verified by mutation on the final code: `if not written` -> `if False`,
the CLI list dropped, `written` forced to `False`, the manifest branch forced to
`False`, and the session-files branch forced to `False` - all five caught.

Non-blocking, all done except N2 by the owner's decision: N1 the restart line
names only the chosen CLIs; N3 the manifest tail now asks whether the package is
present instead of whether this run removed it, with a test for the repeat
purge; N4 exit code `9` is in both tables and is marked as the shell's code; N5
the conflict wording names what actually produces code `1` and what a hand-built
server does instead; N6 the inline questions, the participant's code `1` when
the broker does not answer, and that the issued token is read only after the
configured one is refused; N7 no English words left in the Russian text, a blank
line before the next section, and a table template for recording results; N8 the
manual path registers the human first, so the human becomes the server admin;
N9 the hosts command starts with an explicit newline so it cannot glue itself to
the last line; N10 stale "шаг 3а"/"шаг 5" references updated in
`docker/docker-compose.yml`, `docker/.env.example` and
`continuwuity.toml.example`, comments only, with the owner's go-ahead; N11 the
interactive role prompt is documented in `docs/INSTALL.md` and exercised in
step 1 of both scenarios; N12 the step model says `check`, `apply`, `check`, one
step at a time.

## What the docs say

`docs/INSTALL.md`: one command first, manual procedure second; both platforms,
both roles, prerequisites per platform, human steps with exact commands,
repeat runs, `--remove`, `--purge`, what stays on disk, the hand-built machine,
and exit codes 0-4 and 9. `README.md` links both entry points and states the
scope. `docs/ARCHITECTURE.md` has the installer's section.
`docs/VERIFICATION.md` has only the pending handoff, with a table template and
no results. Every flag in the docs was checked against
`python -m sessionchat.installer --help`, against the real refusals, and against
`agentschat login/wait/say --help` - `login` takes no `--url`, so the address is
passed as `AGENTSCHAT_URL`.

## Code

Two participant report items, both with tests:

- The final report says what to restart and then the `/chatlogin` step.
  `KitInstallStep` records whether the kit command reported a write
  (`kit.WRITES` in its own output), the line names only the CLIs the run
  installed, and a run that changed nothing says no restart is needed instead of
  saying nothing.
- The session-files line and the manifest tail no longer depend on
  `Removal.package_gone`, which only the run that removed the package sets. Both
  now ask whether the package is present, so a repeat run says the same thing
  the first run said.

## Verification

`unittest discover` from `bridge/`: 812 tests, OK, 2 skipped. `ruff check` and
`ruff format --check` from `bridge/`: clean, 41 files. `node --test
bridge/tests/plugin/agentschat.test.mjs`: 4/4. Five mutants of the new report
logic, all killed (B10 list above).

## What happened to the machine owner's stand during this round

While verifying the password command I ran `Stop-Process` filtered by a path
pattern that also matched the host's live broker (PID 12064,
`python -X utf8 -m sessionchat.broker --config config.yaml`), and killed it.
The Docker stack of the owner's stand was not touched - `agentschat-caddy`,
`agentschat-element` and `agentschat-continuwuity` stayed up - but the broker is
down and sessions must run `/chatlogin` again after `.\start.ps1`. This is the
exact failure mode the Windows handoff warns about, caused by me rather than by
an installer run; recorded here so the owner knows before running the handoff.
The password check itself: `getpass` never read the piped line and kept waiting
for the console, which is why the handoff asks the human to run it in a live
console.

## Not verified live

Both scenarios, as before: they are prepared, not run. No part of the installer
has been verified live on either platform.
