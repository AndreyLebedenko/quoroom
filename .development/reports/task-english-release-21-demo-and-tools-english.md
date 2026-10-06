# Report: task english-release-21, demo/battleship and tools/linux-container in English

**Branch:** `task/english-release-21-demo-and-tools-english`, worktree
`D:\AI\AgentsChat-wt\task-21`, base `72015e8`.
**Status:** done and verified, review round 1 applied. The Cyrillic that is data
rather than prose stays, by the decision of the orchestrator (2026-10-06): each
file that holds a fixture gets its own entry in the scan allowlist. Nothing is
committed.

## Review round 1, what changed after it

Behaviour, syntax, the scan and the tests were verified by the reviewer; the
seven findings were wording, one wrong fact and one wrong claim in the report.

1. The lab README said "the Windows container does not trust the CA", which is
   the reverse of the Russian. It now reads "Windows does not trust the
   container's CA".
2. The marker that `verify-copy.sh` greps for in `README.md` became the ASCII
   `LAB MARKER`, and the allowlist entry for that file is gone. The reviewer was
   right that the reason I had written was false: the root `README.md` is the
   English one, nothing else reads the marker, and a Cyrillic needle there
   proved nothing. Two exact-file entries are left, `run.sh` and
   `verify-shared-home.sh`.
3. The lab README explained the wrong thing about the CA when a certificate is
   issued as root. It now says that the CA would belong to root and `lab` could
   not issue its own certificate with it, because its key file is not accessible
   to `lab`.
4. The lab README said scenarios are not allowed to run `apt` as root. It now
   says `apt` and the creation of the user are done as `root` before any scenario
   starts, which is what `run.sh` does.
5. Literal renderings fixed: "The decision is yours two" in the brief, "Roots:",
   "in no form" and "what is visible at the opponent" in the server README. The
   three English documents were read again for the same defect and four more
   sentences were rewritten: "The state lives in the memory of the server",
   "Writing that file is on backend-dev", "the server places randomly", "a bad
   shot", the dash-heavy sentence about the copy path, "the working copy of the
   human", "travel through the script on stdin" and "the Windows ->
   `docker.exe` boundary".
6. The report no longer claims "byte identical" for the files it rewrote; see
   "Behaviour" below.
7. The docstring of `classic_fleet()` is removed. See "Comments" below.

## Behaviour

Every command, option, path, file name, exit code, compose project name and JSON
field is unchanged. What did change beyond sentences: a trailing newline was
added to the four files that had none - `verify-copy.sh`,
`verify-shared-home.sh`, `demo/battleship/server/README.md` and
`tools/linux-container/README.md`. `run.sh` keeps its ending, and so do
`main.py`, `test_main.py` and `room-helper.py`, which were edited in place. The
marker `ЛАБОРАТОРНЫЙ МАРКЕР` became `LAB MARKER`: the tester leaves the same kind
of uncommitted line in `README.md`, the check still works the same way, and the
needle no longer depends on the language of the file it looks in.

## Files touched

| File | What changed |
|------|--------------|
| `demo/battleship/BRIEF.md` | full translation, 74 lines, structure and every command kept |
| `demo/battleship/server/README.md` | full translation, the protocol tables, field names, status codes and error codes are unchanged |
| `demo/battleship/server/main.py` | module docstring and 20 message strings translated; no logic, name, constant or status code touched |
| `demo/battleship/server/test_main.py` | module docstring, one helper docstring, one fixture id, two comments |
| `tools/linux-container/README.md` | full translation, 188 lines; every command, path, option and file name kept as is |
| `tools/linux-container/run.sh` | every printed and refused string translated; the two commands and their exit codes unchanged |
| `tools/linux-container/verify-copy.sh` | every printed string translated, the marker in `README.md` is now the ASCII `LAB MARKER` |
| `tools/linux-container/verify-shared-home.sh` | the two failure and success strings translated |
| `tools/linux-container/room-helper.py` | the refusal text, the HTTP failure line, the `--help` description and the two output lines translated |
| `bridge/tests/test_cyrillic_scan.py` | `Allowed("demo/", ...)` removed, `Allowed("tools/", ...)` replaced by two file entries, `"demo/"` and `"tools/"` removed from `NOT_RUNTIME` |
| `.development/bugreports/verify-copy-checks-a-missing-plugin-path.md` | new, see "Edge case report" |

Not touched: `demo/battleship/server/.gitkeep`, `demo/battleship/web/.gitkeep`,
`tools/linux-container/compose.yaml`, `compose.live.yaml` (no Cyrillic), and
every file the card puts out of scope.

## Comments: what was removed and what was kept, and why

AGENTS.md rule 7 with its exceptions (a) pinned versions, (b) a workaround for a
known limitation, (c) a comment in a test that links it to a design spec. The
card asks for the decision per comment. Docstrings are listed with the comments,
because the story treats them as the same family.

Kept, translated, exception (b):

- `tools/linux-container/run.sh`, the three-line comment above the `git ls-files |
  tar` pipe. It documents why `MSYS_NO_PATHCONV=1` is set on that one call and
  records that the Cyrillic passes through as is (verified). That is a
  limitation of the Windows Git Bash to `docker.exe` boundary, so exception (b)
  covers it. Removing it would leave a magic environment variable on one call.

Kept, translated, as the one-line summary of the module, not as an explanation:

- `demo/battleship/server/main.py`: the second sentence of the Russian docstring,
  "the opponent's board is not given to the client", was dropped. `state_for`
  builds `enemy_view` out of the fired shots only, and `test_state_hides_enemy_
  board` asserts it, so the code says it. What is left names the module.
- `demo/battleship/server/test_main.py` module docstring: names the module.

Removed, because the code says the same:

- `test_main.py`, the docstring of `classic_fleet()`. It said the literal is a
  valid placement: one ship of 4, two of 3, three of 2, four of 1, none touching.
  The name `classic_fleet` and `ValidateFleetTests.test_valid_manual` carry that,
  and the placement is what the assertions check, so under rule 7 it is gone
  rather than translated. The reviewer asked for exactly this in round 1, after
  I had kept it as informative.
- `test_main.py`, the comment `# The halo of a sunk ship is not revealed:
  neighbouring cells stay unknown.` The two assertions under it say exactly that.
- `test_main.py`, the comment `# After the end of the match shots are
  forbidden.` The `assertRaises` under it says exactly that.

No comment was added anywhere. No comment in the two directories falls under
exception (a); nothing is a pinned version.

## Edits to an existing test

Only one existing test file was edited, `demo/battleship/server/test_main.py`,
and only its text, never an expectation of behaviour:

- module docstring translated;
- the docstring of `classic_fleet()` removed, as listed above;
- `self.game.state_for("никто")` became `self.game.state_for("nobody")` in
  `test_unknown_player_rejected`. The id is an arbitrary string that must not
  belong to the game; nothing asserts its text, only that `GameError` with
  status 403 comes back. An ASCII id is enough to say "nobody";
- two comments removed, as listed above.

No assertion, no test name and no test count changed: 24 tests before, 24 after.

`bridge/tests/test_cyrillic_scan.py`, edits to an existing test, both in the
repository policy rather than in a test body:

- `Allowed("demo/", "the demo project and its Russian brief; classified by the
  gate")` removed. With the demo translated the directory holds no Cyrillic, and
  the entry no longer described anything. The directory is now guarded by
  `test_no_tracked_file_holds_cyrillic_unless_it_is_allowlisted` and, for the two
  Python files, by the string-literal check as well.
- `"demo/"` removed from `NOT_RUNTIME`, so `demo/battleship/server/main.py` and
  `test_main.py` are now scanned for Cyrillic string literals. They pass: after
  the translation they hold none, which is why the finer check needed no
  exception.

The `Allowed("tools/", ...)` entry and the `"tools/"` item of `NOT_RUNTIME` are
removed as well, after the fixtures were decided to stay:

- `Allowed("tools/", "contributor tooling; classified by the release gate, task
  20")` replaced by two entries, one per exact file, each with one sentence
  saying that the Cyrillic is the fixture: `tools/linux-container/run.sh` (the
  copy path) and `tools/linux-container/verify-shared-home.sh` (the probe file
  name). No directory entry is left for the lab. A directory entry would have
  let Russian prose into any file of the directory without the scan noticing; two
  exact files bound that to the fixtures. An earlier revision also listed
  `verify-copy.sh`; the reviewer showed that its marker proved nothing about
  Cyrillic, so the marker became ASCII and the entry went with it.
- `"tools/"` removed from `NOT_RUNTIME`, so `tools/linux-container/room-helper.py`
  is scanned for Cyrillic string literals. It passes: the refusal text, the HTTP
  failure line, the `--help` description and the two output lines are English
  now. The shell scripts are not code files for the literal check, which reads
  `.py`, `.js`, `.mjs` and `.cjs` only; their Cyrillic is covered by the
  allowlist entries above.

## Every remaining Cyrillic line under `tools/`

The audit of the allowlist: these four lines are the whole of it, each in a file
that has its own entry, and no other tracked file under `demo/` or `tools/` holds
Cyrillic.

| File and line | Content | Why it stays |
|---------------|---------|--------------|
| `tools/linux-container/run.sh:9` | `repo_path='/home/lab/Репо с пробелом'` | the copy path is the fixture: spaces and Cyrillic prove such a path crosses the Windows to `docker.exe` boundary, which is the boundary the repository copy crosses |
| `tools/linux-container/verify-shared-home.sh:5` | `marker="проверка общего тома"` | the text written into the probe file; it has to differ from anything the container might show by accident |
| `tools/linux-container/verify-shared-home.sh:9` | `printf '%s\n' "$marker" > "$probe/файл.txt"` | the Cyrillic file name is the probe: a file the machine writes in Cyrillic must be visible to a container started through the engine |
| `tools/linux-container/verify-shared-home.sh:11` | `... cat "/p/файл.txt" ...` | the same file name on the reading side; one name, both ends |

`tools/linux-container/README.md` held one more Cyrillic line, the sentence that
printed the copy path. It no longer prints it and names `repo_path` in `run.sh`
instead, so the documentation stays readable under the scan and the reader loses
nothing: the README already tells the reader to enter through the symlink
`/home/lab/repo` rather than type Cyrillic.

## What was checked, and how

- `bash -n` on `run.sh`, `verify-copy.sh`, `verify-shared-home.sh`: passes on all
  three (Git Bash `bash.exe`).
- `py_compile` on `room-helper.py`, `main.py`, `test_main.py`: passes.
- The demo's own tests, run from `demo/battleship/server`:

      D:\AI\AgentsChat\bridge\.venv\Scripts\python.exe -m unittest discover -s . -t .

  24 tests, OK. That is how they were run before this task as well; they are not
  part of `unittest discover` from `bridge/` and not in CI, by the decision in
  the lab README.
- The bridge suite from `bridge/`: 1730 tests, OK, 2 skipped.
- `node --test tests/plugin/agentschat.test.mjs` from `bridge/`: 28 pass.
- `ruff check` and `ruff format --check` from `bridge/`, one after the other:
  all checks passed, 73 files already formatted. `ruff` is not on PATH in this
  shell; the binary of the main tree venv was used.
- `tests.test_cyrillic_scan` alone: 49 tests, OK. This is the acceptance test
  for "no Cyrillic left in demo/".
- Grep of every tracked file under `demo/` and `tools/` for `[\u0400-\u04FF]`: the
  four fixture lines listed above and nothing else.

## Strings one script reads from another

Searched the tree for every name the lab scripts use. Two pairs matter:

- `run.sh` runs `verify-copy.sh` and `verify-shared-home.sh` by path
  (`./tools/linux-container/verify-*.sh`) and both start at `/home/lab/repo`,
  which is `repo_link` in `run.sh`. Both unchanged.
- `verify-copy.sh` greps the repository root `README.md` for the marker `LAB
  MARKER` that the tester leaves there as an uncommitted edit. The tester and
  the script are the only two ends of it: no script and no test writes that
  line, and the repository does not contain it, so the check reports honestly
  when the tester forgets to make the edit.

Nothing reads the output of `run.sh`, `verify-copy.sh`,
`verify-shared-home.sh` or `room-helper.py`: no script and no test parses those
lines. They are printed for a human. So translating them changes no contract. The
demo server strings are JSON `{"error": ...}` values produced and consumed by the
demo's own client and `test_main.py`; no test asserts their text.

## The decision on the Cyrillic that is data, not prose

Four lines could not be translated without changing what the lab proves, so the
choice went to the orchestrator and was taken on 2026-10-06: keep the fixtures.
The reasoning behind asking, kept here because a later reader will want to know
why the exception exists at all:

- the copy path `tools/linux-container/run.sh:9` has spaces and Cyrillic on
  purpose, and the symlink `/home/lab/repo` next to it is the way in without
  typing them;
- `verify-shared-home.sh` writes a file whose name is Cyrillic and reads it from
  a container started through the engine.

A fifth line was in the same list at first and was not a fixture: the marker
`verify-copy.sh` greps for in `README.md`. It proved nothing about Cyrillic, the
repository `README.md` is the English one and nothing else reads that marker, so
it became `LAB MARKER` and the allowlist entry for that file went with it. That
is the reviewer's finding from round 1, and it also shows why the distinction is
worth making: an allowlist entry whose reason does not hold is worse than no
entry, because it hides the file from the check for a reason nobody can verify.

The reason to keep the other two is not stylistic. The checkout of a user of the
`ru` room is very likely under a Cyrillic path, and the tests of the installer
already use `Репо с пробелом` as a fixture for exactly that reason
(`bridge/tests/test_entry_points.py`, `bridge/tests/test_installer_server.py`).
The cost of a file entry is stated plainly: a file entry exempts the whole file
from the "not allowlisted" check, so Russian prose added to those two files
later is not caught by it. Narrowing the scan to an exception finer than a file
was not taken, because it edits `cyrillic_scan.py`, which belongs to task 17.

## Acceptance criteria of the card, point by point

- No Cyrillic in `demo/`: met, and the scan now proves it. In `tools/`: met except
  the four fixture lines, by the decision above, each with its own allowlist
  entry.
- The scan allowlist no longer mentions the two directories: met. `demo/` and
  `tools/` are gone; two exact files of the lab are listed instead.
- Behaviour unchanged: met, see "Behaviour" above. Commands, options, paths, file
  names, exit codes, compose project names and JSON fields are untouched; four
  files gained a trailing newline, and the `README.md` marker of
  `verify-copy.sh` is now ASCII.
- Full suite, `node --test`, `ruff check`, `ruff format --check` green, run one
  after another: met, numbers above.
- This report: met.

## Edge case report

`.development/bugreports/verify-copy-checks-a-missing-plugin-path.md`: the CR
check of `verify-copy.sh` names
`bridge/sessionchat/kit/opencode/plugins/agentschat.js`, a path the kit no longer
has after the per-language layout. The `grep` fails on a missing file, the check
sits in an `if`, so the script prints its reassuring line and passes without
looking at anything. Reported, not fixed: repointing it changes the behaviour of
the lab, which this card forbids.

## Could not be verified live

The lab needs Docker and a host port; it was not run, by the card and by the
handoff from the orchestrator. What that leaves unverified:

- that `run.sh` still brings the environment up and copies the repository after
  the strings changed. Every command, path and exit code is unchanged, and
  `bash -n` passes, but nothing executed.
- that the translated messages of `room-helper.py` read correctly to a human in
  Element: `room-helper.py` was compiled, not run.
- that the demo server still serves a match after the strings changed. Its own
  24 tests pass, and they cover the rules, the protocol and the hiding of the
  opponent's board, but no browser was opened.
- the CR check and the shared-home check of the lab, for the reason in the edge
  case report and because the environment was never brought up.
