# Report: task-local-installers-05-participant-role (round 6)

**Branch:** `task/local-installers-05-participant-role` (from `feat/local-installers`)
**Base commit:** 4047d6b
**Status:** review round 6 fixed, implemented and verified, not committed.

Every row of the verification tables was produced by running the code as it
stands now, after the last edit. Rounds 3 to 5 are summarised at the end; this
round is the one to read for the current shape of the removal report.

## Round 5 items, all in this commit

**B1. Paths are printed under the reason that left them, one item at a time.**
`removal_lines` built the block as every reason followed by every path, so with
more than one leftover the Claude file sat under the package line. `_left_lines`
now interleaves: reason, then its own paths. Live on `--remove --claude` with a
hand-edited Claude file:

```
Убрано не всё, осталось в системе:
    набор для opencode не снимался: его не называл ключ запуска
    файлы набора для claude, изменённые вручную, uninstall оставил
        /home/lab/.claude/skills/chatlogin/SKILL.md
    пакет quoroom оставлен: им пользуется набор для opencode
Файлы сессий в .agentschat оставлены: вернуться в комнату можно новым входом.
Поставить обратно: install.sh --role participant
```

Tests: the path line directly follows the Claude reason and does not follow the
package line; a second test reads the leftover block and finds the path there.
Three mutants die - paths printed after every reason, the old two-list layout,
and reason-plus-paths joined into one line.

**The purge line is now a cross-reference.** It was repeating the removal
reasons; the second copy added nothing and, in a full purge, ended with "когда
записей не останется, agentschat uninstall удалит его сам" a few lines after the
warning that no `agentschat` is left to run it. One line instead, with the tail
chosen by the same `package_gone` fact as the rest:

```
kit.json оставлен по причинам выше: удалите его вместе с этими файлами.
```

and, while the package is installed:

```
kit.json оставлен по причинам выше: когда записей не останется, agentschat uninstall удалит его сам.
```

Tests: the exact line in both states, the reason line appears above it, and the
reason text appears exactly once in a purge run - the mutant that prints it
again dies. A manifest with no records keeps its own line, tested directly
against `purge_lines`, since no installer run can produce that state.

**The session-files line depends on the package too.** With the package gone,
"вернуться в комнату можно новым входом" is not true - `agentschat login` is
gone with it. Live after a full `--remove` with a hand-edited file:

```
Файлы сессий в .agentschat оставлены: после повторной установки сессия вернётся в комнату через /chatlogin.
```

While the package is installed the old sentence stays; both are tested.

**The weak test is rewritten.** `test_kept_files_are_named_in_the_missing_agentschat_warning`
asserted a path against the whole stdout, where `agentschat`'s own
"оставлен (изменён вручную) <path>" line above already contains it, so it passed
whatever the report did. It is now `test_kept_files_are_named_in_the_report_under_their_reason`
and reads the leftover block only. The B1 inverse test now covers the case the
review named - a narrowed removal where the package is kept - and the
unrecorded-package case stays as a second inverse.

## Decisions worth knowing

- **Where the paths go, and where they do not.** Each item prints its own paths
  under its own reason. The missing-`agentschat` warning deliberately does not
  repeat them: the review confirmed that, and the block above already names
  every file.
- **One source per fact.** The purge line points at the removal block instead of
  restating it, and both `package_gone` checks - the session-files tail and the
  manifest tail - read the same flag the warning uses. A full purge therefore
  says three consistent things about the missing binary: the files call it, the
  manifest goes with them, and the session returns through `/chatlogin` after a
  reinstall.
- **A CLI outside this run's flags is listed without its paths.** Its files are
  untouched user files, the package line below says who still needs them, and
  `agentschat`'s own output above names them. Round 5, unchanged.
- Rounds 3 to 5, unchanged: a file missing from the manifest is not an edit; the
  CLI question is asked once and cached on the step.

## Automated verification, run from `bridge/`

- `.venv/Scripts/python.exe -m unittest discover -s tests -t .` - Ran 527 tests,
  OK, 1 skipped (`pwsh` absent).
- `node --test tests/plugin/agentschat.test.mjs` - tests 4, pass 4, fail 0.
- `.venv/Scripts/ruff.exe check` - All checks passed.
- `.venv/Scripts/ruff.exe format --check` - 37 files already formatted.

### Mutation check

Fifteen mutants on the code of rounds 4 to 6, all caught by
`tests.test_installer_participant`:

| Mutant | Result |
|---|---|
| paths printed after every reason | killed |
| the old two-list layout | killed |
| reason and paths joined into one line | killed |
| purge repeats the removal reasons | killed |
| purge sends the manifest to a missing `agentschat` | killed |
| the session line ignores the removed package | killed |
| the missing-`agentschat` warning dropped | killed |
| the warning without the `package_gone` gate | killed |
| kept files not named under their reason | killed |
| `uninstalled` never set | killed |
| `package_gone` never set | killed |
| `asked` is every CLI regardless of flags | killed |
| record ignored when both tools report | killed |
| wrong-shape manifest treated as empty | killed |
| round-3 nested `printf` quoting | killed |

## Functional flow in the task 04 lab

Environment: `run.sh up` from a clean volume, Ubuntu 24.04 on `docker:dind`,
`pipx 1.4.3`, no `uv`, HOME `/home/lab`. A stub answering `/status` with HTTP
200 ran inside the machine. The two flows the review named, plus one full
`--remove` without purge, because that is the only run that prints the new
session-files sentence.

| Step | Observed |
| --- | --- |
| clean machine, install of both CLIs, hand edit appended to the Claude kit file | exit 0; the edit is in the file |
| `--remove --claude` | exit 0; "пакет quoroom оставлен: им пользуется набор для opencode" on stderr; block lists the untouched OpenCode kit, then the kept Claude file with its path directly under it, then the package; no missing-`agentschat` warning; both kit files still on disk; "Файлы сессий в .agentschat оставлены: вернуться в комнату можно новым входом." |
| two session tokens and `notes.txt` planted, then a full `--remove --purge` | exit 0; edited Claude file kept, three others deleted; package removed; block lists the kept file with its path; "Файлы набора вызывают agentschat, которого больше нет: удалите их или поставьте участника снова."; "kit.json оставлен по причинам выше: удалите его вместе с этими файлами."; no `agentschat uninstall` tail; no "Файлы сессий ... оставлены" line; both token files deleted, `notes.txt` and `kit.json` left; `~/.local/bin` empty; `~/.quoroom` gone |
| clean machine, install, hand edit, full `--remove` | exit 0; the same block and warning as the purge run, then "Файлы сессий в .agentschat оставлены: после повторной установки сессия вернётся в комнату через /chatlogin." and "Поставить обратно: install.sh --role participant" |

The host's live stack was not touched: `agentschat-caddy`, `agentschat-element`
and `agentschat-continuwuity` stayed up; `docker volume ls` 14 -> 14 and
`docker network ls` 7 -> 7 against the snapshot taken before `run.sh up`; no
`quoroom-linux-lab` container, volume or network remains after `run.sh down`.

## What is not verified here

- The real broker: the lab used a stub answering `/status` with HTTP 200.
- The `uv` path: no `uv` in the lab. The tests model it, including the
  bullet-prefixed listing lines.
- Windows: unit tests with the `windows` platform only, including
  `setx AGENTSCHAT_URL`.
- "Both tools report the package": the lab has pipx only.
- A `kit.json` with no records is tested against `purge_lines`, not through a run:
  no installer run can produce that state.

## Rounds 3 to 5 in one paragraph each

Round 3 fixed the printed address command (quote the address, then quote the
whole `printf` argument; four tests run it through a real `sh`), narrowed the
rule that keeps a package to "a CLI this run did not name", made the report name
the kept files, printed the removal summary before the purge lines, and turned a
wrong-shaped `kit.json` into a named reason instead of `KeyError`. Round 4 added
the record's precedence test, moved `posix_path` and the `sh` lookup into
`tests/installer_fakes.py`, and made the report stop claiming a kept package that
was already gone. Round 5 put back, in narrowed form, the sentence that kept kit
files call an `agentschat` that is no longer installed, made the purge line state
the real reason `kit.json` survives, and put the leftovers one per line.

## Moved by the reviewer, not actioned here

- `UsageError` raised inside a step exits 1 rather than 2 - core, later.
- The wording of the restart line comes from `agentschat`'s own summary mid-run -
  task 08.
- `--purge` with a CLI flag deletes every agent's session file - task 07/08; it
  is recorded in that task's card.
