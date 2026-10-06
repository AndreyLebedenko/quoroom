# Report: task english-release-22, the participant installer teaches the client the room language

**Branch:** `task/english-release-22-install-remembers-language`, worktree
`D:\AI\AgentsChat-wt\task-22`, base `aa85ea4`. Review round 1 applied. Nothing is
committed.

## Review round 1, what changed after it

1. `LanguageStep.answer_of` catches `(OSError, ValueError)`, not `OSError` alone:
   `run_command` decodes the child's output as text, and a child that prints
   bytes the terminal encoding cannot decode raises `UnicodeDecodeError`, a
   `ValueError`. Without this the step runner would have failed the whole
   install over a cosmetic problem. The fake has a mode `undecodable` that raises
   it, and a test that the install still succeeds and the report says the language
   was not learned.
2. The step label no longer promises an outcome: it reads `Ask the broker for the
   room language` / `Спросить у брокера язык комнаты`. The runner was not touched;
   with this wording its `done.` line is true of what the step does, and the
   outcome is carried by the warning at the step and the line in the report, which
   are unchanged.
3. `tests/test_installer_boundaries.py` now proves the environment merge on a real
   process: a child prints `os.environ['AGENTSCHAT_URL']` and the test asserts the
   value the caller passed; a second child shows `PATH` still comes from the
   installer; a third shows the installer process own `os.environ` is untouched
   afterwards; a fourth shows that a call without `env` passes `env=None` to
   `subprocess.run`, that is, still inherits.
5. `learned_language` also requires `answer["command"] == "status"`, like the
   OpenCode plugin does, so a result line of another command cannot be read as
   this step's answer, and its parameter is annotated
   `subprocess.CompletedProcess[str]`. A test feeds a result line of `login`.
6. `tests/result_line.py` imports `MARK` from `sessionchat.client_result` instead
   of building it from `PREFIX`, so the test helper and the code under test share
   one definition of the marker.
8. The Russian sentence reads `Язык комнаты не удалось узнать у {url}: agentschat
   говорит по-английски, пока брокер не ответит на команду клиента.` and the
   English twin ends `... until the broker answers a command of the client.`: the
   old `его` / `its` could be read as the broker's command.
9. `docs/VERIFICATION.md`, R1: `без всякой обращения` is now `без всякого
   обращения`; the paragraph, the bullets and the record table agree that the
   Russian `--help` and the Russian refusal before any broker contact are
   expected, not observed; the heading and the two table rows use the Latin `R1`
   that the rest of the file uses. The intro paragraph of the scenario now names
   one observed thing (the kit language) instead of two.
10. Tests: the failure report is asserted in an English run as well as the default
    Russian one, and `Machine.__call__` in the fake takes `env` as an explicit
    keyword - passed on only to the `agentschat` calls - so a `uv` or `pipx` call
    with an environment raises `TypeError` as before, and any other unexpected
    keyword still raises `TypeError` at the call.
11. `docs/INSTALL.en.md` 3.3 and `docs/INSTALL.md` 3.3, "What stays in place": the
    client's own files are named there - `~/.agentschat/language` and
    `opencode-plugin.log`, with the command to forget the language by hand.
    Documentation only; purge still deletes the token files and nothing else.

## What was built

A new install step of the participant role, `learn_room_language`, after
`check_broker`. It runs `agentschat status` once, with the address the installer
itself probed passed to the child as `AGENTSCHAT_URL`, reads the client's
`AGENTSCHAT-RESULT` line, and lets the client write `~/.agentschat/language` the
way it always has. The `both` role gets it through the participant role. The step
never fails the install: a client that cannot run, that exits non-zero or that
reports a failure leaves the install successful, and the final report says that
the room language was not learned and what the person gets until it is.

## Keys added

Two, one sentence each, in both catalogues with identical placeholder sets:

| Key | en | ru |
|-----|----|----|
| `step.learn_room_language` | Ask the broker for the room language | Спросить у брокера язык комнаты |
| `participant.language_not_learned` | The room language was not learned from {url}: agentschat speaks English until the broker answers a command of the client. | Язык комнаты не удалось узнать у {url}: agentschat говорит по-английски, пока брокер не ответит на команду клиента. |

The second key is used twice, as `participant.set_url_permanently` and
`participant.path_missing` already are: once as a warning at the step, once in the
final report. One sentence, one meaning, two places where the human needs it.

## The decision the step makes, and what it refuses to decide

`learned_language()` in `participant.py` accepts an answer only when all four
hold: the child exited 0, the last `AGENTSCHAT-RESULT` line parses as a JSON
object, that object names the command `status` and says `ok` true, and its
`language` field is a language the client knows (`client_language.valid`).
Nothing else counts. Three tests pin that:

- a result line with the language and no table at all is enough;
- a printed sentence `Язык комнаты: ru` with no result line teaches the step
  nothing, and is not even relayed into the installer's own output;
- a result line of another command, carrying the language, teaches the step
  nothing.

The reader is `client_result.read`, added to the module that already writes the
line, so the prefix and the JSON shape have one definition for the writer and the
reader. It takes the last result line, like the OpenCode plugin does.

## The environment of the child

The card stops the task if `boundaries.run` cannot carry an environment for one
child, rather than the installer changing its own process environment. It now can:
`Runner` and `run_command` take `env: Mapping[str, str] | None`, and
`run_command` passes `None` (inherit, every existing call unchanged) or
`{**os.environ, **env}` for that one child. Nothing writes to `os.environ`, and
no later child sees the address.

Two decisions inside that:

- The address is passed even when it is the default
  `http://127.0.0.1:8770`. If it were inherited instead, a machine whose own
  environment carries a different `AGENTSCHAT_URL` would have the installer probe
  one broker and the client ask another, and the client would learn the wrong
  language. A test names that.
- Only `AGENTSCHAT_URL` is passed. The home is left to inheritance: the installer's
  `boundaries.home` is `Path.home()` in production, which is what the child
  computes too, so the file lands where the person's later commands read it.
  Setting `HOME` or `USERPROFILE` from `boundaries.home` would be a second source
  of truth for something that already agrees, and on Windows only one of the two
  variables would be the one the child reads. A test asserts that nothing else is
  added to the child's environment, so the choice is visible rather than implied.

## Idempotence

`check` is DONE when `~/.agentschat/language` already holds a valid language, so a
second install runs no child at all. A store that holds something that is not a
language (`fr`) is not taken for one: the child runs and the file is replaced by
the client. Tests cover both, plus the empty-store case in each language.

## The failure of the step

The step framework has one shape: `check`, then `apply`, then `check` again, and
a step still TODO after `apply` fails the whole run. A best-effort step therefore
cannot exist inside that protocol without either failing the install or reporting
itself as done. The choice made here is the second: `handled` is set before the
child runs, `apply` never raises, and the outcome is carried by a warning at the
step plus a line in the final report. The runner was not touched; instead the label
was chosen so that its `done.` line is true of what the step did - it asked the
broker - and the outcome, learned or not, is in the two sentences the step adds
itself. The alternative - a tolerant step in `steps.py` - would change the shared
runner for both roles and is not this card's business.

`learned` is set from the result line alone, not from a second look at the file.
The client writes the file from the same answer it reports, so a second check
would be a second source of truth for one fact; the case it would catch is a home
directory the client cannot write, where the client is broken anyway.

The child's own output is captured and dropped: the table of `status` is not
relayed into the installer's report, and a refusal sentence of the client is not
quoted inside an installer sentence, because the two speak different languages
when the room is Russian and the installer runs with `--lang en`. The installer's
own sentence names the address and what the person gets.

## Purge and removal: checked, no step owed

The card stops the task if the removal contract makes the new file owed a removal
step. It does not. `session_step()` is a `FoundStep` over `broker_tokens`, which
returns the `*.json` files that hold a token, and the language file is not one of
them; `kept_files()` lists it under `participant.kept_not_session` as
"left in place, not a session file", which is the pre-existing behaviour for any
non-token file in the store. The installer does not record the file either, so a
purge confirmation does not offer it and `uninstall` is untouched. No step was
added and no existing line changed.

## Tests added

`bridge/tests/test_installer_participant_room_language.py`, 24 tests:

- the language of the room ends up in the store after the install, in `en` and
  `ru`; the client is asked once; a second install asks nothing; a store that
  already holds a language is left alone; a store holding `fr` is not trusted;
- the address of the installer reaches the child, including the default, and
  nothing else is added to its environment;
- the result line is the decision: a bare result line is enough; printed words
  are not, and are not relayed; a result line of another command is not;
- a client that cannot run, whose output cannot be decoded, that exits non-zero,
  or that reports a failure leaves the install successful, remembers nothing, and
  makes the report name the address in Russian and in English; the report says
  nothing when the language was learned; the restart hint stays the last line;
- the step label and the sentence exist in both languages with the same
  placeholders, and the run prints the label.

`bridge/tests/test_client_result.py`, 5 tests: the last result line wins, output
without one has no answer, a broken JSON body and a JSON list have none, and a
word that merely begins like the prefix is not a result line.

Both redirect the home through `installer_fakes.boundaries` (`InstallerTestCase`
builds a temporary home); no test reads or writes the real home.

`bridge/tests/test_installer_boundaries.py`, four tests added to
`RunCommandTests` for the environment of a real child: it sees the variable the
caller added, it keeps the rest of the installer environment, the installer own
`os.environ` is unchanged afterwards, and a call without `env` still inherits.

## Edits to an existing test

Three files, no expectation of behaviour changed:

1. `bridge/tests/test_installer_participant.py`, class `Machine`: `__call__`
   takes `env` as an explicit keyword and passes it on to the `agentschat` calls
   only, so a `uv` or `pipx` call given an environment raises `TypeError` as
   before, and so does any other unexpected keyword; new constructor arguments
   `room_language` (default `en`) and `status_mode` (default `ok`); new
   `status()` method that answers like the real client does - it writes the
   language file through `client_language.remember` and prints the result line -
   with the modes `quiet` (no table), `words` (a sentence and no result line),
   `not-ok` (a result line with `ok` false and exit 0), `refuses` (exit 1 and
   `ok` false), `another-command` (a result line of `login` with the language),
   `missing` (`FileNotFoundError`) and `undecodable` (`UnicodeDecodeError`);
   the attribute `status_env` records the environment the child was given;
   `agentschat` routes `status` before the kit commands; imports
   `client_language`, `client_result`, `CompletedProcess` and the
   `STATUS_COMMAND` constant. Existing installs keep working because the default
   mode answers `ok`.
2. `bridge/tests/test_installer_language_end_to_end.py`, class `SharedMachine`:
   `__call__` takes `**kwargs` and forwards them, so the both-roles scenario can
   pass the address to the participant child.
3. `bridge/tests/result_line.py`: `MARK` is imported from
   `sessionchat.client_result` instead of built from `PREFIX`.

No existing test needed a changed assertion, a changed step list or a changed
expected output: the existing participant, participant-language and end-to-end
suites (201 + 69 + 40 tests) pass as they were, and the two suites that enumerate
the steps assert with `assertIn`, not with an exact list. The catalogue contract
test caught one thing during the work: the new `participant.language_not_learned`
key was first inserted out of alphabetical order in `en.json`; it was moved.

## Document lines changed

`CHANGELOG.md`

- "Added", the entry on `~/.agentschat/language`: the file is written by the
  client and only from a broker answer; the participant installer now runs
  `agentschat status` once right after confirming the broker, so on a freshly
  installed participant the file is there before the person runs anything; the
  fallback to English is unchanged.
- "Upgrade notes", the entry on the client's own language: the file exists after
  the participant installer has run on the machine; on an existing machine of a
  Russian room run the participant installer again; without that run the old
  behaviour stays.
- The "Added" entry on the machine contract, the "Upgrade notes" entry on the kit
  language and the "Fixed" entry were left alone: all three stay true. The kit is
  still laid down before the broker is asked, which is why its language is the
  installer's.

`docs/INSTALL.en.md`, section "Room language": one paragraph after the kit
paragraph, saying that the client's own language is not the installer's, that the
installer runs `agentschat status` once after confirming the broker, that the
client learns and writes `~/.agentschat/language`, and what happens when the step
cannot learn it.

`docs/INSTALL.md`, section "Язык комнаты": the same paragraph in Russian.

`docs/VERIFICATION.md`

- the handoff header: the candidate commit now also has task 22 merged;
- the paragraph that says which two things of the scenario are observed rather
  than expected: the first is now "the language of the client right after the
  participant install" instead of "before the first answer of the broker";
- "Выведено из кода, не запускалось", item 1: the client writes the file and only
  from a broker answer, the installer does not write it and asks the client once
  (`participant.py`, `LanguageStep`), so on a machine where the participant
  installer ran the file exists before the first command of the person;
- R1: the paragraph before the commands now expects `agentschat --help` to be
  Russian right after the install; the bullet list gains the step name
  `Спросить у брокера язык комнаты: готово.`, the catalogue key
  `participant.language_not_learned` and the file `~/.agentschat\language` with
  `ru` in it; the Russian `--help` and the Russian refusal of `agentschat say`
  before any broker contact are marked as expected, and only what actually came
  out is to be recorded; the bullet after `agentschat status` is unchanged;
- the record table of the Russian run: the row reads "R1. Язык клиента сразу после
  установки участника (`--help` и отказ)".

`docs/INSTALL.en.md` 3.3 and `docs/INSTALL.md` 3.3, "What stays in place": a new
bullet names the client's own files there, `~/.agentschat/language` and
`opencode-plugin.log`, says that only the session files with their tokens are
deleted, and gives the command to make the client forget the room language. This
is documentation of what the code already does; no behaviour changed with it.

The recorded results elsewhere in `docs/VERIFICATION.md` were not touched, and
neither were `docs/AGENTS_INTEGRATION.md` / `.en.md` ("Room language" there says
the client learns from broker answers and remembers, which is still exactly what
happens) or `docs/SESSION_BRIDGE.md` (Russian only, contributor document, out of
the story).

## Files touched

| File | Change |
|------|--------|
| `bridge/sessionchat/installer/participant.py` | `LanguageStep`, `learned_language`, `remembered_language`, the step in the install tuple, the report line, `URL_VARIABLE`, `STATUS_COMMAND`, `import subprocess` |
| `bridge/sessionchat/installer/boundaries.py` | `env` in `Runner` and `run_command` |
| `bridge/sessionchat/client_result.py` | `MARK` and `read` |
| `bridge/sessionchat/installer/messages/en.json`, `ru.json` | two keys each |
| `bridge/tests/test_installer_participant.py` | the fake executor, see above |
| `bridge/tests/test_installer_language_end_to_end.py` | the shared fake executor |
| `bridge/tests/test_installer_boundaries.py` | four tests for the environment of a real child |
| `bridge/tests/result_line.py` | `MARK` imported from the code under test |
| `bridge/tests/test_installer_participant_room_language.py` | new, 24 tests |
| `bridge/tests/test_client_result.py` | new, 5 tests |
| `CHANGELOG.md`, `docs/INSTALL.en.md`, `docs/INSTALL.md`, `docs/VERIFICATION.md` | see above |
| this report | new |

## Checks

Run from `bridge/`, one after another:

- `.venv/Scripts/python.exe -m unittest discover -s tests -t .` - 1763 tests, OK,
  2 skipped (1730 before this task, plus 33 new: 24 for the step, 5 for the
  reader, 4 for the boundary).
- `node --test tests/plugin/agentschat.test.mjs` - 28 pass.
- `python -m ruff check` - all checks passed.
- `python -m ruff format --check` - 75 files already formatted (74 before: the new
  test file).

The interpreter is the one of the main tree, `D:\AI\AgentsChat\bridge\.venv`,
because the worktree has no virtualenv of its own; `ruff` is not on PATH and was
run as `python -m ruff` with that interpreter, as the handoff asked.

## Could not be verified live

No Docker, no Element, no real CLI sessions, by the handoff. What that leaves
open, all of it for the human run recorded in `docs/VERIFICATION.md`:

- that the installed `agentschat status` really writes `~/.agentschat/language` on
  a real machine, and that the installer therefore makes `agentschat --help`
  Russian before any command of the person. The tests cover this with a fake
  client and a redirected home, never with the real binary.
- what the person sees when the step fails on a real machine, that is the warning
  and the report line in a terminal.
- the purge behaviour with a language file present: the reading above is from the
  code (`broker_tokens`, `kept_files`) and from tests that use other non-token
  files, not from a live purge.
