# Task english-release-10: install and uninstall report actions as codes

Status: implemented, not committed, waiting for review. Branch
`task/english-release-10-kit-machine-contract` from `b01415a`. No commit, no
merge, no push: the orchestrator takes it after acceptance.

## What the boundary now is

`agentschat install` and `agentschat uninstall` print, under `--json`, one JSON
document on stdout and nothing else:

```
{"command": "install", "ok": true, "code": "none", "steps": [{"action": "installed", "cli": "claude", "target": "..."}]}
```

The participant installer asks for exactly that document, and every decision it
used to take from the client's Russian words now comes from the document:

- `KitInstallStep.written` (whether files were written) was
  `any(action.value in spoken for action in kit.WRITES)`; it is now
  `kit.Report.wrote`, which compares the ids in `steps` against `kit.WRITES`.
- `kit_failure` (whether the install was refused for foreign files) was
  `if CONFLICT in detail`, where `CONFLICT` was the first clause of the
  `KitConflict` sentence; it is now `report.code == kit.CODE_CONFLICT`, and the
  detail it reports is the list of targets the document blames.

Without `--json` the human sentences are byte-for-byte what they were. No
Russian sentence was translated in this task.

## Design decisions taken, and why

1. **The recommended shape, unchanged.** `{"command", "ok", "code", "steps":
   [{"action", "cli", "target"}]}`, as the card's design item 1 spells it out.
   `ok` is derived from `code` rather than passed separately, so a document can
   never claim `ok: true` together with `code: "conflict"`.

2. **A dedicated exit code, `REFUSED = 5` (card item 2).** `client.FAILURE = 1`
   stays the generic failure. `5` is above the installer's own outcome codes
   (`0`..`4` in `installer/main.py`), so a transcript never shows one meaning
   for one number across the two programs. That relation is an invariant, so it
   is a test (`ExitCodeTests`) rather than a comment.

3. **`Action` values are language-independent ids** (card item 3): `installed`,
   `updated`, `overwritten`, `unchanged`, `conflict`, `removed`, `kept`,
   `gone`. The Russian display word moved to `kit.DISPLAY_RU`, a temporary table
   that `Step.line()` reads; task 11 deletes it and takes the words to the
   catalogue. `StepDisplayTests` asserts the table covers every action, so a new
   action cannot be added without its word.

4. **The installer decides by the document, not by the exit code.** The client
   prints the conflict document on stdout and exits `REFUSED`; the installer
   reads the code in the document. One authority, and the exit code cannot lie
   about the contents. `KitReportTests` runs the conflict with the client
   exiting `1` and gets the same conflict, which pins the choice.

5. **`KitConflict` carries the refused steps instead of the refused paths.** The
   document has to name the file it blames, and the client cannot learn that
   from the paths alone (the step knows its `cli`). `KitConflict.steps` holds
   exactly the conflicting steps - not the whole plan - because a refused install
   wrote nothing, and a step labelled `installed` in that document would be a
   lie. `targets` stays as a derived property, so `test_kit_installer.py`'s
   existing assertion on it is untouched.

6. **`--json` goes last in the argv** (`install --claude --opencode --json`).
   Argparse does not care about the position. It matters here because
   `assertIn(line, self.machine.log)` on a list is an exact match: appending the
   flag keeps every such assertion a substring of a real command instead of
   turning twelve of them into rewrites.

7. **The installer stopped echoing the client.** `_spoken()` printed whatever the
   client said into the installer's own report. With `--json` there is nothing
   human left to echo, and echoing was in any case incompatible with the
   existing rule that the installer prints no Russian under `--lang en`: the
   client's sentences are Russian until task 11. Nothing the human loses -
   the installer's report already names the restart, the hand-edited files, the
   broker, PATH and `/chatlogin`.

8. **A client that answers in prose is a plain failure, not a guess.** If
   `Report.read` cannot make a document out of stdout, `KitInstallStep` raises
   the existing generic `participant.kit_failed` with whatever the client did
   print. Silently believing "nothing was written" would be the one answer that
   misleads the human; refusing is loud and points at the client's output.

9. **The uninstall step does not read the document.** It passes `--json` so the
   client says nothing human, and its decision is still the exit code - which is
   not prose. Requiring a document there would add a failure mode and no
   information.

## Codes and keys introduced

Codes (machine-readable, in `kit.py`; the installer compares them, never their
prose):

| Code | Meaning |
|------|---------|
| `kit.COMMAND_INSTALL` = `install` | the command the document belongs to |
| `kit.COMMAND_UNINSTALL` = `uninstall` | the same, for the removal |
| `kit.CODE_NONE` = `none` | the command did what it was asked |
| `kit.CODE_CONFLICT` = `conflict` | the install refused foreign files |
| action id `installed` / `updated` / `overwritten` / `unchanged` / `removed` / `kept` / `gone` | what happened to one file |
| `client.FAILURE` = `1` | the client's generic failure, as before |
| `client.REFUSED` = `5` | the client's dedicated refusal code |

No catalogue key was added, removed or reworded. `participant.kit_conflict` and
`participant.kit_failed` are unchanged; only the string that fills their
`detail` placeholder changed source (the document's targets instead of the
client's sentence). `installer/messages/en.json` and `ru.json` are untouched.

One new Russian string exists, `client.JSON_HELP` = "отчёт кодом, без
предложений", the `--help` line of the new flag. It is new text, not a
translation; task 11 moves it to the catalogue with the rest of the client's
sentences.

## Edits to existing tests

Allowed by the card: the fake client in `test_installer_participant.py` is the
input of those tests, and the contract it speaks changed.

1. **`tests/test_installer_participant.py`, class `Machine`** (the fake
   `agentschat`). `install_kit` / `uninstall_kit` build the steps they already
   computed and return `kit.Report(...).as_json()` instead of Russian sentences;
   the conflict case writes a foreign file and returns a document with
   `code: "conflict"` plus the step that blames it. `clis_for` ignores `--json`
   instead of reading it as a CLI name. The fake now shares the format with the
   client, so a change of the format cannot pass silently.
2. **`Machine.__init__`** gained `kit_conflict_code`, `kit_answers` and
   `kit_claims_no_writes`. They let a test say what the client answers: its own
   words, nothing at all, or a report that claims no writes.
3. **`tests/test_installer_participant.py`, the argv assertions.** Nineteen
   lines that name the exact command the installer runs gained
   ` {participant.JSON_FLAG}`: eighteen `assertIn` / `assertNotIn` over
   `self.machine.log`, and the `self.machine.log.index(...)` in
   `test_the_kit_is_removed_before_the_package`. Three more in
   `test_installer_participant_languages.py`. Reason: the installer passes one
   more flag. `assertIn` on a list is an exact match, so the flag had to be
   named rather than left to a substring; the same reason applies to the two
   `assertNotIn` lines that would otherwise have gone vacuous. Nothing else in
   those assertions moved.
4. **`tests/test_installer_participant.py`,
   `test_a_repeat_install_with_nothing_changed_asks_for_no_restart`.** It
   asserted `"менять нечего"`, which is the *client's* sentence, reaching the
   installer through `_spoken`. It now asserts the installer's own sentence
   `"Набор на месте и не менялся"` (`participant.restart_unchanged`), which is
   the same statement from the catalogue and is what the test is about. No other
   expectation in that file changed.
5. **`tests/test_kit_installer.py`.** `AgentschatCommandTests` lost its
   `setUp` / `run_agentschat` / `dir_flags` to a new base class `AgentschatCase`,
   reused by the new `ReportTests`. The bodies of the existing tests are
   unchanged.
6. **`tests/test_installer_participant_languages.py`,
   `StableIdentityTests`.** `test_the_conflict_marker_is_taken_from_the_message_
   the_client_raises` asserted that the installer's marker is a prefix of the
   client's sentence. That is the dependency this card removes, so it is
   replaced by `test_the_participant_module_holds_no_russian_to_recognise_the_
   client_by`: the module must contain no Cyrillic at all, which subsumes both
   the action words and the refusal sentence. (The whole `installer/` package is
   already Cyrillic-free, so the invariant holds there too.)
7. **`tests/test_installer_participant_languages.py`, `KitFailureTests`.** The
   two tests that told a conflict apart by the client's text are replaced by
   three: the code in the document names the conflict in both languages, any
   other failure stays a plain failure, and a refusal spelled out by the client
   is a plain failure in both languages. Both language keys are asserted
   unchanged.

## Tests added

`tests/test_kit_installer.py`:

- documents for a first install (the whole document, key by key), a no-op
  install, an update, a conflict, a forced overwrite, an uninstall with a
  hand-edited file kept and the rest removed;
- the document is the only thing on stdout, and it holds no Cyrillic;
- a refusal without the flag still names the file and `--force`;
- `REFUSED` is not one of the installer's codes and is not `FAILURE`;
- every action has a display word.

`tests/test_installer_participant.py`, class `KitReportTests`:

- a conflict is recognised from the code the client reports, and names the file
  the report blames;
- the same conflict with the client exiting `1` instead of `REFUSED`;
- a refusal spelled out by the client is *not* read as a conflict;
- a client that answers with nothing is not believed to have written;
- the restart hint follows the report, not the files on disk (the fake writes
  the files and reports every action as `unchanged`);
- both commands are asked for their report by the flag;
- the client's own words are not echoed into the installer's report.

## Check results

| Check | Result |
|-------|--------|
| `.venv/Scripts/python.exe -m unittest discover -s tests -t .` | 1105 tests, OK, 2 skipped (baseline 1082) |
| `node --test tests/plugin/agentschat.test.mjs` | 4 tests, 4 pass |
| `.venv/Scripts/ruff.exe check` | All checks passed |
| `.venv/Scripts/ruff.exe format --check` | 47 files already formatted |

Nothing live was run: Docker, Element and a real session are the human's. The
manual handoff that this task adds for the human is a single `agentschat install
--json` on a throwaway `--claude-dir` / `--opencode-dir`, checking that stdout
is one JSON line and nothing else, and that a run over a foreign file exits
`5` with `"code": "conflict"`.

## Noted, not touched

1. `installer/participant.py` still reads the *listing* of `uv tool list` /
   `pipx list` (`tool_reports_package`, `PACKAGE in listed_names(result.stdout)`).
   That is prose from a third-party tool, not from `agentschat`, so it is out of
   this card's boundary - but it is the same mistake, and a later card should
   take it. `uv tool list --show-version-specifiers` or an explicit
   `uv tool dir` probe would be the machine-readable way.
2. `kit/install_summary`, `uninstall_summary` and `restart_hint` are still
   Russian literals in code. Card item 3 says task 11 moves them.
3. The client's other commands (`login`, `logout`, `status`, `say`, `wait`,
   `inbox`, `ask`) still have no machine-readable result; tasks 08 and 09.
4. `docs/INSTALL.md` section 4 documents the installer's exit codes only; the
   client's `--json` and its code `5` are not described there yet. Section 5.10
   still describes `agentschat install` as printing a line per file, which is
   true without the flag. Both belong to task 18 (the English install guide), and
   `docs/SESSION_BRIDGE.md` says nothing about the prose dependency, so nothing
   there went stale.
5. `Report.read` treats a malformed document and a document with an unknown
   action the same way: no document, plain failure. A distinct code for "the
   client's contract is broken" would be nicer than the client's own output as
   the detail, but it is not needed while there is one consumer.
6. The client and the installer are now two processes that must agree on the
   shape of the document, and the only thing holding them together is that both
   import `kit.py` from the same package version. The installer resolves the
   binary through `uv`/`pipx`, so an old client with a new installer (or the
   reverse) reports a plain failure with argparse's own complaint in the detail.
   That is loud, which is the intent; pinning the client's minimum version
   belongs to task 20.