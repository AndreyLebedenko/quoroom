# Bug report: verify-copy.sh checks a plugin path that the kit no longer has

**Detected at:** 72015e80afc8abfd907fc85d3bbf8e383a6eed23
**Status:** reported, not fixed, fix deferred.

## Symptom

`tools/linux-container/verify-copy.sh` proves that `crlf_to_lf` did its job by
grepping one file git hands over as `w/crlf`. The file it names is

    bridge/sessionchat/kit/opencode/plugins/agentschat.js

and that path does not exist any more. The OpenCode plugin is at
`bridge/sessionchat/kit/common/opencode/plugins/agentschat.js` since the kit
started shipping a variant per language.

The consequence is a false negative, not an error the tester sees: `grep -q` on a
missing file exits non-zero, the script is under `set -eu`, and the check sits in
an `if` condition, so the failure is swallowed and the reassuring line

    the file that git hands over as w/crlf has no CR at all

is printed after all. The check passes without looking at anything. The
`exit 1` in the "a CR remained" branch is unreachable for the same reason: grep
cannot find a CR in a file it cannot open.

## Suspected cause

The path was written when the kit had one plugin location and was not updated
when task `english-release-13` moved the shared plugin under `kit/common/`. The
lab is checked by functional runs and by no automated test, so nothing failed
when the path went stale.

## Temporary decision

Leave the path as it is, translate the prose around it, and report it. The card
in progress (`task-english-release-21`) states that behaviour does not change:
same commands, same options, same exit codes. Repointing the file makes the CR
check start working again, which is a behaviour change of the lab and belongs to
a card of its own. Changing it here would also mean the review of a translation
card silently repairs a verification.

## Future considerations

- A follow-up card should repoint the grep at
  `bridge/sessionchat/kit/common/opencode/plugins/agentschat.js` and make the
  missing file an error rather than a pass: `[ -f "$file" ]` before the grep, or
  `grep -q ... "$file" || [ $? -eq 2 ]` style handling. A check that cannot fail
  is worse than no check, because the operator reads it as coverage.
- While there: the same script asserts four task files exist by name
  (`install.sh`, `install.ps1`, `tools/linux-container/run.sh`,
  `tools/linux-container/room-helper.py`). Those paths are still correct today,
  so the pattern is right there; only the CR check lost its subject.
- Nothing in the lab is covered by `unittest` or CI, by the decision recorded in
  the lab README, so a stale path in a scenario is only found by a human run.

## Boundaries

- No change to `run.sh`, `verify-copy.sh` or any other lab behaviour in the
  translation card.
- No change to the kit layout.
