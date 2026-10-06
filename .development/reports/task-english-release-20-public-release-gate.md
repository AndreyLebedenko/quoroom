# Report: task english-release-20 (the gate before the repository is opened)

Branch: task/english-release-20-public-release-gate (worktree D:/AI/AgentsChat-wt/task-20), from story/english-release 72015e8. Nothing committed. No code, script, catalogue or test changed.

## What changed

- `README.md` and `README.ru.md`, kept in step:
  - a new "Language" / "Язык" section: one language per room, `language: en|ru`, English default, strict values, who writes the key, the kit language rule, a pointer to the "Room language" section of the install guide;
  - a new "Documentation language" / "Язык документов" section: which documents have an English and a Russian version, which exist in Russian only, and that Russian is the author's working language and not a missing translation;
  - the stale note "the detailed documentation in docs/ is written in Russian" at the top of `README.md` is replaced (three guides now have English versions);
  - the layout bullets for `docs/SESSION_BRIDGE.md` and `docs/VERIFICATION.md` say "(in Russian)".
- `CHANGELOG.md`: a new `## Unreleased` section above `v1.0.0-rc.2` (Added, Changed, Upgrade notes, Fixed, Known limitations). The rc.2 section is untouched.
- `docs/VERIFICATION.md`: appended at the very end (Russian, like the file) one handoff section, two empty record tables. The only diff against earlier text is the file's last line gaining a trailing newline (the file had none).

## Russian-only documents, checked by a Cyrillic scan over docs/

- `docs/SESSION_BRIDGE.md` and `docs/VERIFICATION.md`: Russian.
- `docs/COORDINATION_PLAN.md`: six lines of Cyrillic, all in the cancellation notice at the top; the plan itself is English. The card lists it among the Russian documents; the README says what is true (notice in Russian, plan in English). Change it back if you want it listed plainly as Russian.
- `docs/INSTALL.md`, `ARCHITECTURE.md`, `AGENTS_INTEGRATION.md` are the Russian twins of the three `.en.md` guides. `AGENTS_INTEGRATION.en.md` has three lines with Cyrillic (two commands with Russian prompts and one quoted bridge message, from report 19).
- `demo/` and `tools/linux-container/` still hold Cyrillic in this tree. The README does not say anything about their language, so it cannot contradict task 21.

## Owner decision recorded (2026-10-06)

`demo/battleship/` and `tools/linux-container/` are translated into English. That work is task english-release-21, done by someone else in parallel; this task did not touch either directory and the README makes no claim about them. Note for the merge: `bridge/tests/test_cyrillic_scan.py` still has allowlist entries for `demo/` and `tools/` whose reasons say "classified by the release gate, task 20". When task 21 lands, those entries (and the `docs/` reason text) are stale or fail the hygiene tests ("covers no tracked file" / "holds no Cyrillic"). That is a test edit, outside this card.

## CHANGELOG: how each claim was checked

Every statement was taken from the code or a report and checked against the code at 72015e8:
- `language` strict `en|ru`, absent means `en`, refusal at start: `room_language()` in `broker.py`; new config writes it from the installer's `--lang`, existing file untouched: `new_config()` in `installer/server.py` and report 02.
- error body `{code, message, params}`, `/status` JSON only with state codes, envelope `kind` `human|agent` and `rendered`: reports 03, 04, 06 and `handle_status`.
- `AGENTSCHAT-RESULT` on login, logout, status, say, ask: reports 08, 09; `install --json` document and exit code 5: `REFUSED = 5` in `client.py`, report 10 (only `install` refuses; uninstall does not).
- client remembers the language in `~/.agentschat/language`: `client_language.py`.
- kit per language `en`/`ru` plus `common/`, English skills and command: the files exist under `bridge/sessionchat/kit/`; `--lang` on `install`/`uninstall`: `agentschat install --help`.
- `start`/`stop` and `register_account.py` take `--lang`: reports 16, 17; PowerShell scripts lost `[CmdletBinding()]`: report 16.
- scan test: `bridge/tests/test_cyrillic_scan.py`.
- logs English, store errors coded: report 05, report 12.
- upgrade notes: report 02 / the task card note (config without `language` means `en`); the old plugin matched Russian phrases (report 12, story text) so it does not bind a session on English output (reasoned from those, not run); the kit-language rule from report 11 and `docs/INSTALL.en.md`.

Version heading: the convention is `## v<version>` and rc.2 has no git tag (only `v1.0.0-rc.1` exists; `pyproject.toml` says 1.0.0rc2), so I did not pick a number. The section is headed `Unreleased` and says the number is the owner's decision.

## The manual handoff in docs/VERIFICATION.md

Written to AGENTS.md rule 2: who runs it and when (the owner, once, on the release candidate, on a clean machine), what breaks without it (no stranger's end-to-end path is observed, and the owner does not open the repository), verified findings kept apart from recommendations.

- Findings (run by me, no Docker, no broker, no session): `agentschat --help` and subcommand help in English on a clean profile and in Russian with `~/.agentschat/language` = `ru`; installer module `--help` in both languages and `--lang fr` giving exit code 2 and an English text; a say without a login refuses in English with a `not_logged_in` result line on a clean profile.
- Steps: preparation (clean-state checks, transcript, Cyrillic regex), English run E1-E6 (installers without `--lang`; deleting the `language` line and restarting to test the "key unset" case, because the server installer writes `language: en` itself; sixteen terminal commands with a table of what to look for; the depth-limit notice via `max_depth: 1`; real Claude Code and OpenCode sessions, skill files, plugin and broker logs; purge), Russian run R1-R2 (both installs with `--lang ru`, reference table, optional baseline commit 7feb147), the pass criteria, where to write, and where defects go.
- Two empty record tables (English, Russian). The run result is not recorded by me.
- Commands come from `docs/INSTALL.en.md` and the real CLI help. The commands of the handoff were not executed (they need the stack); only the help and the clean-profile refusals above were.

## Checks (from D:/AI/AgentsChat-wt/task-20/bridge, in order, system venv of the main tree)

1. `unittest discover -s tests -t .`: Ran 1730 tests, OK, 2 skipped.
2. `node --test tests/plugin/agentschat.test.mjs`: 28 pass, 0 fail. No process killed.
3. `ruff check`: all checks passed.
4. `ruff format --check`: 73 files already formatted.
5. Files: `README.md` and `CHANGELOG.md` contain no non-ASCII character except the one Russian link line in `README.md` (the allowlisted one). All four edited files keep CRLF line endings; `git diff --check` is clean.

## Incident

My first help check ran `python -m sessionchat.client` with a fake HOME but without `AGENTSCHAT_URL`, so `status`, `say` and `login --agent claude-code` reached the live broker on 127.0.0.1:8770 (the main tree's stand). Effect: `status` is read-only; `login` was refused because the slot is held by the orchestrator's live session; `say` refused locally (no credentials). No registration, token or file was created or changed. After that I only ran commands that cannot reach a broker. The live broker is an older build (its `status` answered plain text, which my newer client reported as `unexpected_answer`).

## Open questions and things I could not verify

1. Russian room, clean participant machine: the client starts in English until it has had one JSON answer from the broker (the language file does not exist and `install` does not write it). So the first Russian-room commands (`agentschat --help`, a `say` refused for no login) print English, where before the story they always printed Russian. This follows task 07's design ("explicit flag > broker's answer > remembered file > en"), but it conflicts in letter with the story criterion "with `language: ru` the same run prints what it printed before". The handoff makes it an observation (R1), not a pass condition. Decide whether to accept it, or whether `agentschat install --lang ru` should remember `ru` in the language file.
2. `docs/VERIFICATION.md` is not chronological: the new section sits after the cancelled "Проверка моста" section because the card says "appended". Move it up if you prefer.
3. README says the depth limit is "6 by default", which is true of the code (`protocol.MAX_DEPTH`), but `bridge/config.example.yaml` sets `max_depth: 20`, so an installed stand has 20. Not changed (outside the card); the handoff tells the human to set `max_depth: 1` temporarily.
4. Nothing live was run: every expected string in the handoff comes from the catalogues and the reports, not from a run. The expected English `login` sentences are described by mode, not quoted, for that reason.
5. The reports for tasks 01-19 were read for facts, not re-audited; where a report and the code could be compared (language, codes, exit code 5, `/status`, notices, envelope keys), they agreed.

## What remains for the human

The clean-machine English run and the Russian run from `docs/VERIFICATION.md`, recorded in the two tables at its end; defects found go to `.development/bugreports/`. The owner opens the repository only after the English run is recorded as passing. Also needed before that: merge task 21 and re-run the four checks on the release commit (the card's last acceptance line).

## Review round 1

All 14 findings were checked against the code and applied; none declined. Docs only.

docs/VERIFICATION.md (handoff):
1. Clean machine is now a VM or a separate computer only; the profile option is gone; one sentence says not to run it on a machine with a live stand (Docker Desktop, fixed names, port 8770, hosts, mkcert, `stop.ps1` lookup are machine-wide) because the E6 purge deletes the stand volumes.
2. `ask --timeout 5`: the row now says the no-answer text appears after one long poll, about 50 s (`WAIT_SECONDS = 50.0` in `protocol.py`; `do_ask` loops on `poll_once`), and that the text prints `5.0s` (`args.timeout` is a float).
3. New "After E1" step: check `agentschat --help`; if not found, `uv tool update-shell` (pipx: `pipx ensurepath`), new terminal; `Stop-Transcript` in the old window, in the new one redefine the console encoding, `$AgentsChat`, `$Cyr`, `cd`, and `Start-Transcript -Append` into the same file. R1 got the same step (the R1 block is split in two). The "if not found, open a new terminal" sentence in E3 became a pointer to this step.
4. Verified in `participant.py` (`broker_tokens` globs only token `*.json`): participant purge leaves `language` and `opencode-plugin.log`. E6 now lists `~/.agentschat` after the purge (recorded as a finding, not a defect) and then deletes the whole directory (`Remove-Item -Recurse -Force`, the machine is a throwaway). The Russian preparation now expects all `Test-Path` to be `False` again and says the plugin log of the Russian run is a new one.
5. The Russian comment left the E2 command block (prose between two blocks). The pass rule also excuses pasted Russian comments.
6. E3 now has `install --help`, `uninstall --help`, `install --json` (set already installed: ok, code `none`, `unchanged`, exit 0) and the conflict case on a throwaway directory (`--claude-dir $Foreign`, foreign `SKILL.md`): `--json` gives `conflict` and exit 5, without `--json` the English refusal and exit 1. I ran this case on a temporary profile first: exit 5, exit 1, nothing written to the target, the same after removing the foreign file gives `installed` and exit 0. On the real machine the conflict case writes nothing, so it cannot touch `kit.json`. Table rows added; R2 says the same commands apply.
7. "Установлено до прогона" now has only what was run (help in both languages, installer module `--help` and `--lang fr`, clean-profile refusal, the install conflict run). New section "Выведено из кода, не запускалось" holds the inference about help language, the kit language rule, the kit contents and the purge scope. The intro reference was updated.
Also fixed on the way: the `$Cyr` regex in the file had literal Cyrillic characters in the range (the tool had expanded my `Ѐ-ӿ`); it is now the escaped `'[Ѐ-ӿ]'` in both places.

CHANGELOG.md:
8. Exit code 5 is stated only under `--json`; without it `install` exits 1 (`refuse()` calls `fail()`; verified by the run above). `--json`, `--lang` on install/uninstall are marked as already in rc.2; only exit code 5 and the kit variants are presented as new.
9. `register_account.py` follows only its own `--lang` (verified: it never reads `config.yaml`); `start` / `stop` fall back to the config key.
10. Upgrade notes gained (a) update the client package first: wording is exact to the code - `PackageStep.check` treats a `quoroom` package that `uv` or `pipx` already lists as done and only warns that it may point to another copy or may not be editable; it does not check editability and does not reinstall (the review text said "not editable"; the code is broader). (b) `~/.agentschat/language` exists only after the first JSON answer from the broker and is not written by `install`, so on an existing Russian-room machine `--help` and a refused `say` are English until the first contact. The "client remembers the language" entry in Added is qualified the same way. No recommendation made; it stays an owner question.
11. Known limitations now say "comments in several Python and JavaScript files".

README.md / README.ru.md:
12. Depth limit: 20 in the installed `config.yaml`, 6 if the key is absent; both files. This closes open question 3 above.
13. The em dash in the new Russian paragraph (README.ru.md).
14. Language section in both files: broker answers, notices, agent messages and commands follow the room language, except the kit, which follows the installer's `--lang`.

Checks after the round, from the worktree `bridge/`, in order: unittest 1730 tests OK (2 skipped); `node --test` 28 pass, 0 fail; `ruff check` passed; `ruff format --check` 73 files formatted; `git diff --check` clean. The four edited files keep CRLF.
