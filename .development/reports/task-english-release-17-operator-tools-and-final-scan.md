# Report: task english-release-17 (operator tools and the scan that keeps it English)

Branch: task/english-release-17-operator-tools-and-final-scan (worktree D:/AI/AgentsChat-wt/task-17).
Nothing committed. The new files were marked with `git add -N` (intent to add, no content staged)
because the scan reads `git ls-files` and would otherwise not see them; the orchestrator's own
`git add` replaces that.

## What changed

- `bridge/register_account.py`: `--lang en|ru`, English by default. New catalogue
  `bridge/register_messages/en.json` and `ru.json` (11 keys each). Docstring translated to
  English, inline Russian comments removed (AGENTS.md rule 7).
- `bridge/agentschat` (sh launcher): its two Russian comment lines translated to English.
- `install.ps1`, `install.sh`: the Russian usage header (comment-based help of `install.ps1`,
  one comment line of `install.sh`) translated to English. Nothing else in them changed.
- New scan: `bridge/tests/cyrillic_scan.py` (the machinery), `bridge/tests/test_cyrillic_scan.py`
  (the allowlist and the tests, 49 tests).
- New `bridge/tests/test_register_account.py` (28 tests).

## Decisions and reasons

1. register_account.py uses a catalogue, not an inline table. The card allows both. The deciding
   point is the scan: a Russian table inline in a `.py` file is a Cyrillic string literal in
   runtime Python, which is exactly what the second check forbids, so an inline table would have
   needed a carve-out in the scan. The wrappers can keep inline tables only because they are `.ps1`
   and `.sh` (file-level allowlist, no literal check). A catalogue also gets the whole
   `CatalogueContract` for free (same keys, same placeholders, no Cyrillic and only ASCII in
   `en.json`, sorted keys, no BOM). The cost is that the script imports `sessionchat.i18n`; that
   works wherever the script runs from, because Python puts the script's directory (`bridge/`)
   first on `sys.path` (a test runs it from another directory with no `PYTHONPATH`). The catalogue
   sits next to the script, not inside the `sessionchat` package, so `pyproject.toml`
   package-data is untouched (the script is not shipped in the wheel).
2. Language is chosen with a probe parser (`parse_known_args`, `allow_abbrev=False`) before the
   real parser is built, so `--help` itself is in the chosen language. The real parser also
   declares `--lang`, so it shows in `--help` and is accepted anywhere in the arguments. An
   invalid value is refused by argparse (exit 2). argparse's own messages ("the following arguments
   are required", `-h` text) stay English as they always were.
3. Russian output is character for character the old output. Method: before any edit I ran the
   `HEAD` script against a local stub server (modes: answer at once, two-step, unexpected step 1,
   no session, step 2 refusal, SSL error via https to a plain-http port, missing arguments,
   `--help`) and saved stdout, stderr and exit code. After the change `--lang ru` gives identical
   results in all eight cases except two that differ only by the new option: the usage line gains
   `[--lang {en,ru}]` and `--help` gains the `--lang` line. The English output of the same cases was
   read through by eye. `test_register_account.py` pins both languages as literals.
4. The YAML block is data: `user_id`, `access_token`, `device_id` lines and the printed JSON are the
   same in both languages (tested). Only the heading line above them is translated.
5. The `register()` function got a `lang` keyword (default English) instead of raising, to keep
   the structure of the script. Nobody else imports it.
6. The scan has two checks and separate policies:
   - File level: every tracked file holding Cyrillic must be covered by the allowlist.
   - Literal level: every tracked `.py`, `.js`, `.mjs`, `.cjs` outside the non-runtime trees
     (`bridge/tests/`, `demo/`, `tools/`, `docs/`, `.development/`) must have no Cyrillic outside
     comments, whether or not the file is allowlisted. Python: `ast` string constants other than
     docstrings (f-string text included), plus `tokenize` NAME tokens (a Russian identifier is not a
     comment either). A file that does not parse is reported, not skipped. JavaScript: a Python
     port of the lexer from the plugin test (task 12), which keeps strings, templates (including
     `${}`) and regular expressions and drops comments. One improvement over the original: a
     dropped block comment leaves its newlines, so reported line numbers are exact; an unterminated
     block comment ends the scan instead of looping.
   - Docstrings are treated like comments (documentation, not messages). A second string statement
     in a function is not a docstring and is checked.
7. The allowlist lives in `test_cyrillic_scan.py` as a plain tuple of `Allowed(path, reason)`; a
   path ending in `/` is a prefix, anything else is an exact file. Hygiene tests keep it honest:
   every entry has a reason, covers at least one tracked file, and an exact-file entry must still
   hold Cyrillic (so the entry has to be dropped when a file is translated, e.g. when the plugin's
   comments go). Further tests: `kit/en/` and `kit/common/` (except the plugin) can never be
   allowlisted, `kit/ru/` is, `register_account.py` is not.
8. Git unavailable (unpacked sdist, no `git` binary, a directory that is not a work tree, a
   directory inside someone else's work tree, an empty index): `tracked_files` raises
   `GitUnavailable` and the repository tests are skipped with the reason
   ("the scan needs git ls-files: ..."), via `SkipTest` in `setUpClass`. The top-level check
   (`git rev-parse --show-toplevel` must equal the repository root) stops an unpacked tree inside
   another repository from scanning the wrong files. `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`
   are removed from the environment of the git call.
9. Launcher and wrapper headers: translated, not deleted. They are the only documentation of those
   entry points (the launcher comment explains why paths come from the script's location;
   `install.ps1`'s block is what `Get-Help` shows), and the card names "the launcher comment" as in
   scope. AGENTS.md rule 7 would arguably prefer deletion for the launcher; I kept the information.

## The allowlist, with reasons

| Entry | Reason |
|---|---|
| `.development/` | planning cards, reports and bug reports for contributors; not shipped |
| `docs/` | guides; the Russian ones stay as the second language, the English ones quote Russian output; classified by the gate (task 20) |
| `README.ru.md` | the Russian README, the second language |
| `README.md` | the link to the Russian README and Russian sample prompts and bot answers quoted as data (4 lines) |
| `.gitignore`, `.gitattributes`, `bridge/requirements.txt` | contributor files; Russian comments are out of scope of the story |
| `demo/` | the demo project and its Russian brief; classified by the gate |
| `tools/` | contributor tooling; classified by the gate |
| `bridge/tests/` | tests assert the Russian text printed under room language ru and use Russian fixtures |
| `bridge/sessionchat/broker_messages/ru.json`, `client_messages/ru.json`, `installer/messages/ru.json`, `bridge/register_messages/ru.json` | the Russian catalogues |
| `bridge/sessionchat/kit/ru/` | the Russian variant of the kit |
| `bridge/sessionchat/__init__.py`, `broker.py`, `client.py`, `protocol.py` | Russian comments and docstrings only (the literal check proves it) |
| `bridge/sessionchat/kit/common/opencode/plugins/agentschat.js` | Russian comments only; strings, templates and regexes are scanned |
| `install.ps1`, `install.sh`, `start.ps1`, `start.sh`, `stop.ps1`, `stop.sh` | the Russian message table of the wrapper, printed under room language ru; pinned by `test_entry_points.py` and `test_launch_scripts.py` |

Every tracked file with Cyrillic at the time of writing is covered; the scan found nothing else.
`CHANGELOG.md` does not exist in the tree.

## Found and fixed in runtime files

- `register_account.py`: 10 Russian literals in code plus a Russian docstring and comments. Now
  English, with `ru` in the catalogue.
- `bridge/agentschat`: 2 Russian comment lines.
- `install.ps1`, `install.sh`: the Russian usage header.
- Scan of tracked `.py`/`.js` runtime files: no Cyrillic string literal anywhere else (broker,
  client, protocol, `__init__`, plugin have Russian comments and docstrings only).

## Edits to existing tests

None. The new tests are new files. No existing expectation was touched.

## Checks (from D:/AI/AgentsChat-wt/task-17/bridge, in order)

1. `python.exe -m unittest discover -s tests -t .`: Ran 1718 tests (1641 baseline + 77 new), OK,
   2 skipped. No flaky test seen.
2. `node --test tests/plugin/agentschat.test.mjs` (alone): 28 tests, 28 pass.
3. `ruff.exe check`: All checks passed.
4. `ruff.exe format --check`: 69 files already formatted.

Mutation check of the scan on the real files: copying `client.py` and the plugin into a temporary
tree and appending a Russian string / a Russian template literal is reported at the right lines;
the unmodified real files give no finding. No live checks were made. No process was killed.

## Noticed, not touched

- `docs/INSTALL.md` (Russian) and `docs/INSTALL.en.md` show `register_account.py` without `--lang`.
  The output is now English by default; the Russian guide may want `--lang ru` in its commands.
  Documents are out of scope here.
- Broker log lines still embed Russian room-notice text when the room language is ru
  (the suite prints e.g. `session helium connected (сессия helium)`). Logs are meant to be English
  in every configuration (story). It is a log line, not a message to a human or an agent, and the
  scan does not see it because the text comes from the `ru` catalogue; a look at what the broker
  logs from catalogued sentences may be worthwhile.
- `winstart.ps1` mentioned in report 16 is not in the tree.
- Plugin and the four `sessionchat/*.py` files keep their Russian comments by design (story:
  comments are out of scope); when they are translated or deleted, the hygiene test fails on the
  stale allowlist entry, which is the intended reminder.
- Wrapper tables (`install.*`, `start.*`, `stop.*`) are allowlisted per file, so the scan cannot
  tell a Russian sentence in the table from one added elsewhere in the same script; the wrapper
  tests (`test_launch_scripts.py` checks "Cyrillic only inside the Russian table") cover that.
- The scan skips non-UTF-8 files by reporting them as a finding, which would also catch a
  cp1251 file; there is none today.
- `kit/en/` (tasks 14 and 15) is not in this worktree; the scan covers it generically (any
  Cyrillic there fails) and the boundary tests forbid allowlisting it. It will be exercised for
  real when that branch is merged.
