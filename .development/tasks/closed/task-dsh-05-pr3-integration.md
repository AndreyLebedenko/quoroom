# Task: restore and repair the DSH participant PR

Status: Completed. The owner reviewed the changes and approved completion
of the prepared merge on 2026-10-16.
Story: story-dsh-participant.md
Branch: codex/dsh-pr3-integration

## Summary

Make PR #3 reviewable against master after the original DSH integration was
reverted. Restore the complete integration and its five follow-up commits,
then fix the three findings accepted by the owner on 2026-10-15.

## Current boundary

- Resolve the merge with master without losing unchanged DSH package files,
  the bundle patch, or the command runner's cwd argument.
- Replace task 01's automatic slot_taken retry with the explicit reconnect
  contract in SESSION_BRIDGE.md. Only `/chatlogin <name> --reconnect` may
  request reattachment; an ordinary login must preserve a live registration.
- Scope DSH removal to the requested CLI, home and profile. Keep the shared
  skill and client package while another installed profile needs them.
- Refresh an unedited DSH skill after a kit update or language change.
  Reuse kit digests in a separate installer manifest,
  `~/.quoroom/installer/dsh-kit.json`; never add DSH to kit.CLIS.
- Keep foreign and edited skills intact during installation. A legacy
  installation without a digest can be adopted only when its content equals
  the requested kit. Removal retains the story's existing deletion policy.
- Update the story, runtime instructions and manual handoff. Do not change
  the broker, client protocol, OpenCode plugin or live installation.

## Acceptance criteria

- Regression tests demonstrate refusal without implicit reconnect and
  successful explicit reconnect, including subsequent envelope delivery.
- Installer pipeline tests cover skill updates, language changes, edited
  files, repeated installation, selected removal and multiple profiles.
- A DSH-only operation leaves the other CLI kits unchanged; the shared
  package stays installed while a remaining DSH profile needs it.
- unittest, both plugin suites, Ruff check, Ruff format check and git diff
  check pass; the DSH live handoff is ready for the owner.
- Stop for human review before closing this card, committing or pushing.

## Verification (2026-10-15)

Prepared on PR head `5288ba56c025ea5ec02333a93b71faa9b8f7f110`, with
`0172d067498c32020b2908bcd16713c7bd0a2d28` as the pending master merge
parent. All nine merge conflicts are resolved. The unchanged DSH package
manifest, bundle patch, completed cards and the runner's cwd support are
restored too; resolving only conflicted files would have left them deleted.

Commands ran through the approval mechanism. Python checks used per-process
`PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`; no persistent environment or live
installation was changed.

- `python -m coverage run --branch --source=sessionchat.installer.participant
  --data-file=.tools/dsh-pr3-checks/.coverage -m unittest discover -s tests
  -t .` from bridge, using `.venv/Scripts/python.exe`: 1818 tests, one skipped,
  no errors or failures.
- Focused participant and language suites: 294 tests passed. The new tests
  reproduced implicit reconnect, unintended removal and stale skills before
  the code fixes; they cover language switching, edited and legacy skills,
  missing files, failed tools and profile/home isolation.
- `node --test tests/plugin/agentschat.test.mjs`: 28 passed.
- `node --test tests/plugin/dsh-agentschat.test.mjs`: 32 passed, including
  refusal with an existing token and explicit reconnect followed by delivery.
- `.venv/Scripts/ruff.exe check` and `format --check`: passed, 79 Python files.
- `git diff --check` and `git diff --cached --check`: passed.
- Coverage JSON has no missing statements or branches in either DSH class,
  `dsh_manifest_path`, `package_users`, or CLI selection. No changed Python
  statement or branch is missed. The entire pre-existing participant module
  is 99%, not 100%; remaining gaps are outside this change.

Logs and coverage reports are in the ignored
`bridge/.tools/dsh-pr3-checks/` directory. The live DSH scenario was not run;
scenario 3 in VERIFICATION.md specifies the owner-run checks, including
second-window refusal, deliberate reconnect and selected removal.

## Review approval (2026-10-16)

The owner approved the changes and requested completion of the prepared
merge. This card is closed with that merge commit. The story and live DSH
handoff remain open. No push or GitHub PR merge was requested.

The existing untracked `review-dsh-participant-pr-1.md` is unchanged and is
not included in this task.
