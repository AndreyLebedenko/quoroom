# Story english-release: orchestrator log

Kept by the orchestrator (claude-code) for the owner's final review. Branch
`story/english-release`; one branch per task merged with --no-ff.

## Items for the owner's final review

- English envelope text (task 06): `reports/task-english-release-06-envelope-language.md`.
  Weak form kept on purpose: "There is no need to acknowledge receipt" mirrors
  the Russian "Подтверждать приём не нужно".
- English skills (tasks 14, 15) - pending.
- Task 11: the participant installer no longer echoes the client's per-file
  lines (removed in task 10); the kit language follows the installer's `--lang`
  because `install_kit` runs before `check_broker`.
- Task 12: the plugin file still has Russian comments; the scan strips comments
  and bans Cyrillic in strings, templates and regexes (comments are out of scope
  for the story).
- Task 09: Russian `wait` frame titles stay Russian in `ru`; only the
  `=== AGENTSCHAT: ` prefix is the ASCII marker.
- Task 02: an existing `config.yaml` without `language` now means `en` (CHANGELOG
  upgrade note is in the task 20 card).

## Incidents and defects found on the way

- A task 06 executor ran `taskkill /IM node.exe` (killed 2 node processes on the
  machine, about 22:05); later briefs forbid it.
- Flaky test (task 04), found by repeating the suite: a connection-time second
  boundary race in `test_the_client_prints_the_rendered_lines_one_per_agent`;
  fixed on `fix/status-test-clock-race`, merged.
- One-off `PermissionError [WinError 32]` in a `test_launch_scripts` teardown
  (task 16), reported by glm once in about 10 runs, not reproduced. Open.
- Reviewer found in glm's task 10: `ensure_ascii=False` broke `--json` on a
  non-ASCII path under a narrow console codepage; fixed.
- `stop.sh`: the `shellcheck disable=SC2086` directive was removed by task 16
  (its own test forbids comments outside the header); shellcheck is not part of
  the project checks.

## Review rounds (independent reviewer on glm's code)

- Task 10: ASCII-only JSON, conflict explanation restored, `ok` verified on
  success, tests proving the installer ignores client prose. Fixed by glm.
- Task 11: unused `lang` parameter, JSON files without final newline, duplicate
  test, ASCII check on the real English client run. Fixed by glm.
- Task 13: digests were computed on CRLF working-tree bytes (LF checkouts would
  fail), kit variant was chosen per language instead of per CLI (silent partial
  kit while `kit/en` has only claude), agreement test matched prose, `ok` was a
  deny-list. Fixed on `fix/task-13-review-round-1` (subagent).
