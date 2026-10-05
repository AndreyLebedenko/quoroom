# Task english-release-11: the sentences of install and uninstall

Status: implemented, not committed, waiting for review. Branch
`task/english-release-11-kit-install-messages` from `c88f482`. No commit, no
merge: the orchestrator takes it after acceptance.

## What changed

The kit's human sentences left the source. `kit.py` now renders them from the
client catalogue (`sessionchat/client_messages`) for a language the caller names,
`install` / `uninstall` take `--lang en|ru`, and the participant installer passes
its own `--lang` to the client. Russian is character for character what it was;
English is new. No Russian sentence was translated anywhere else, and no
Russian sentence was reworded.

`kit.py` holds no Cyrillic literal at all now: the temporary `DISPLAY_RU` table
from task 10 is gone, along with the Russian `KitConflict` sentence, both
summaries and the restart hint.

## Decisions and reasons

1. **`kit.py` renders, `client.py` decides the language.** `client.py` resolves
   `ROOM_LANGUAGE.current(STORE)` once per command and hands it down:
   `kit.install(..., lang=lang)`, `kit.Step.line(lang)`,
   `kit.install_summary(steps, lang)`. `lang` is a required argument everywhere -
   no default - so no caller can get Russian by accident. `kit.py` owns a
   `CATALOGUE = Catalogue("sessionchat", "client_messages")` because the action
   words belong to `Step.line`, which lives there.

   Why not the other way round (kit.py returns facts, `client.py` renders):
   task 08 is editing `client.py` in a parallel worktree right now, and the
   card keeps `kit.py`'s sentence functions. Keeping the diff out of the file
   another agent owns is worth more here than the extra indirection.

2. **Which language the installer passes: its own.** The card recommends the
   room language when known, otherwise the installer's `--lang`, and this task
   implements the second half only. The first half is unreachable today, and the
   reason is the step order: `install_kit` runs *before* `check_broker`, so at
   the moment the client is called the installer has not spoken to the broker in
   this run and holds no room language. Reading `/status` earlier would mean
   either reordering the steps (the kit would stop installing when the broker is
   down - worse) or teaching `boundaries.Probe` to carry the language (outside
   this card's boundary). Recorded under "noted, not touched".

   **Where the two differ, and what the human sees.** They differ whenever the
   room's language is not the installer's: `install.sh --lang en` on a Russian
   room, or the reverse. In that case the run speaks the installer's language
   throughout, including the answer it asks the client for. The human sees one
   language per run and nothing mixed. The room keeps its own language for the
   agent sessions, which learn it from the broker on their next command.

   **Where the forwarded flag is visible.** On the happy path, nowhere: since
   task 10 the installer asks for `--json`, prints only its own sentences, and
   the document is the same in both languages (proved by
   `test_the_document_does_not_depend_on_the_language`). It is visible on a
   failure that is not a conflict. `participant.kit_failure` puts
   `result.stderr or result.stdout` - the client's own words - into the
   installer's failure report as the `detail` of `participant.kit_failed`. The
   installer does not parse those words (the decision was made from the document
   or the exit code); it quotes them, and a human reads them. So a Russian client
   failure quoted in an English run is exactly what the forwarded `--lang` now
   prevents.

3. **The per-file lines do not come back.** As the orchestrator decided. The
   installer's report shows no per-file lines and no client text, and the test
   that proves it stays:
   `test_the_clients_own_words_are_not_echoed_into_the_installers_report` and
   `..._do_not_reach_a_removal_report_either` in `test_installer_participant.py`.
   With the fake now printing unrelated words on stderr in both happy paths,
   those two tests are no longer tautologies: the words exist, and they reach
   neither stream.

4. **The help is rendered before the flag is known.** `--lang` selects the
   language of what the command prints, not of its own help text: the parser is
   built before parsing, so the help comes from the language already known
   (explicit `--lang` of an earlier run is impossible, the broker's answer is not
   in this run, so it is the remembered value or `en`). Making the help follow
   `--lang` would need a hand-rolled pre-scan of `argv` next to argparse's own
   parsing; the project already does that in `installer/options.language_of`, but
   duplicating it in the client is a trap for no human-visible gain: nobody reads
   `--help` from inside an installer run, and a direct run gets the right
   language from the remembered value. Tests pin both halves: the English help by
   default, the Russian help when the store remembers `ru`.

5. **`REFUSED = 5` is still only the machine path.** `refuse()` prints the human
   sentence and exits `FAILURE` without `--json`, and the coded document with
   exit `5` with it. Not changed here: it is task 10's contract and its test
   asserts it. A human who trips over a foreign file still gets the historical
   exit code.

## Keys added (`sessionchat/client_messages`, both languages, sorted)

| Key | Placeholders | ru |
|-----|--------------|----|
| `kit.action.conflict` | - | `занят чужим файлом` |
| `kit.action.gone` | - | `уже нет` |
| `kit.action.installed` | - | `установлен` |
| `kit.action.kept` | - | `оставлен (изменён вручную)` |
| `kit.action.overwritten` | - | `перезаписан` |
| `kit.action.removed` | - | `удалён` |
| `kit.action.unchanged` | - | `без изменений` |
| `kit.action.updated` | - | `обновлён` |
| `kit.cli_names` | `{first} {second}` | `{first} и {second}` |
| `kit.conflict` | `{files}` | the old `KitConflict` sentence, unchanged |
| `kit.help_claude_only` | - | `только Claude Code` |
| `kit.help_dir` | `{default}` | `вместо {default}` |
| `kit.help_force_install` | - | `перезаписать чужие файлы` |
| `kit.help_force_uninstall` | - | `удалить и изменённые вручную файлы` |
| `kit.help_install` | - | `разложить набор Quoroom в каталоги Claude Code и OpenCode` |
| `kit.help_json` | - | `отчёт кодом, без предложений` |
| `kit.help_lang` | - | `язык ответа: en или ru` |
| `kit.help_opencode_only` | - | `только OpenCode` |
| `kit.help_uninstall` | - | `убрать установленный набор Quoroom` |
| `kit.install_done` | - | `AGENTSCHAT: набор Quoroom установлен.` |
| `kit.install_unchanged` | - | `AGENTSCHAT: набор Quoroom уже на месте, менять нечего.` |
| `kit.restart_hint` | `{names}` | `Перезапустите открытые сессии {names}: запущенные изменений не увидят.` |
| `kit.step_line` | `{action} {target}` | `{action}  {target}` |
| `kit.uninstall_done` | - | `AGENTSCHAT: удаление набора Quoroom закончено.` |
| `kit.uninstall_kept` | - | `Файлы, изменённые вручную, оставлены. Удалить и их: agentschat uninstall --force` |
| `kit.uninstall_nothing` | - | `AGENTSCHAT: установленного набора Quoroom нет, удалять нечего.` |

`kit.help_dir` is used by both `--claude-dir` and `--opencode-dir`; the English
`kit.help_lang` is `language of the answer: en or ru`. Codes introduced: none -
task 10's `none` / `conflict` and the action ids are unchanged.

No installer key changed. `participant.kit_conflict_files` and
`participant.kit_conflict_force` stay where task 10 put them: the installer
renders its own sentence about the refusal, the client renders its own.

## Edits to existing tests

1. **`tests/test_kit_installer.py`, `KitSandbox.install` / `.uninstall`** take
   `lang=RUSSIAN` and pass it on: `kit.install` / `kit.uninstall` gained a
   required keyword-only `lang`. No expectation changed; the default keeps every
   Russian assertion in the file as it was.
2. **`tests/test_kit_installer.py`, six call sites** now pass the language:
   `kit.uninstall(..., lang=RUSSIAN)`, `Step(...).line(RUSSIAN)` in
   `test_each_step_prints_as_its_russian_label_then_the_target_path` and in
   `test_a_user_edited_file_is_kept_named_and_left_in_the_manifest`, and the five
   summary assertions in `ReportTextTests`. Same reason, same text.
3. **`tests/test_kit_installer.py`, `StepDisplayTests`** is deleted. It asserted
   that the temporary table covered every action; the table is gone and
   `StepLineTests.test_every_action_of_a_step_has_a_word_in_both_languages` says
   the same about the catalogue.
4. **`tests/test_kit_installer.py`, `AgentschatCase.setUp`** patches a fresh
   `client.ROOM_LANGUAGE` per test (the pattern task 07 established) so the
   remembered file of the machine cannot leak in. Five tests in
   `AgentschatCommandTests` and one in `ReportTests` now pass `--lang ru`
   explicitly, because `ROOM_LANGUAGE` resolves to `en` in an empty store: they
   assert Russian output, and saying so in the call is more honest than a preset
   the test never mentions. Expectations unchanged.
5. **`tests/test_kit_installer.py`, the argv assertions of the fake installer**
   (23 lines in `test_installer_participant.py`, 3 in
   `test_installer_participant_languages.py`) gained `--lang ru`, because the
   installer now passes its language: `install --lang ru --claude --opencode
   --json`. `assertIn` over a list is an exact match, so the flag had to be
   named. One of them, `test_the_answer_both_is_accepted_in_english`, runs under
   `lang="en"` and now expects `--lang en`.
6. **`tests/test_installer_participant.py` and
   `test_installer_participant_languages.py`**, the two `kit.KitConflict([...])`
   constructions in the fakes, pass the language the fake speaks: `KitConflict`
   takes it.
7. **`tests/test_installer_participant_languages.py`**:
   `ParticipantLanguageCase.own_words` became `everything` and returns the whole
   output, and `RecordingMachine` - which existed only to remember the client's
   lines so the Cyrillic tests could skip them - is deleted. Since task 10
   nothing of the client's reaches the installer, so skipping was hiding nothing
   and weakening the claim. Every "prints no Russian" assertion in
   `EnglishOutputTests` and the 26-scenario table now reads everything the
   installer printed. `test_the_installers_own_words_are_english_in_every_scenario`
   is renamed `test_everything_the_installer_prints_is_english_in_every_scenario`.
8. **`tests/test_installer_language_end_to_end.py`**: the same exclusion is gone
   from `BothRolesWithoutTheFlagTests.assert_no_russian`, which now reads both
   streams whole; `RecordingMachine` is replaced by the plain `Machine`; the
   server `Machine` is imported under its own name because `SharedMachine` still
   extends it.
9. **`tests/test_client_language.py`**, the fake catalogue in `setUp` is now the
   real client catalogue with `failure_line` and `probe` overridden. Reason:
   `main()` builds the whole parser before parsing, so it asks the catalogue for
   every help string of `install` / `uninstall`; a two-key fake made two
   precedence tests raise `KeyError`. The keys under test still differ per
   language, which is what those tests are about.

No Russian expectation was changed anywhere.

## Tests added

`tests/test_kit_installer.py`:

- `StepLineTests`: a table over all eight actions in both languages, the step
  line, the install summary with and without changes, the empty removal, the kept
  file, the conflict sentence (reason, file, `--force`, in both languages), and a
  check that no English conflict or help string carries Cyrillic;
- the Russian summary and the Russian action words are pinned to the exact
  strings, so "identical to today" is a test, not a promise;
- `HelpTests`: `--lang`, `--json` and the language sentence in the help of both
  commands, both commands described in the main help, the Russian help under a
  remembered `ru`, and an unknown language refused with exit `2` before anything
  is written;
- `RealClientTests`: the real `python -m sessionchat.client` in a subprocess with
  `HOME`/`USERPROFILE` pointed at a temporary home - an English install and an
  English removal write and take the kit back with no Cyrillic on stdout or
  stderr, every file line is English, a refused English install explains itself
  in English and exits non-zero, and with `--json` the same refusal is the
  conflict code with an empty stderr;
- `test_the_document_does_not_depend_on_the_language`: the same install in `ru`
  and in `en` produces byte-identical documents.

`tests/test_installer_participant_languages.py`: two tests that the client is
asked to answer in the run's language, including a Russian run against an
English-defaulted harness.

## Check results

| Check | Result |
|-------|--------|
| `.venv/Scripts/python.exe -m unittest discover -s tests -t .` | 1453 tests, OK, 2 skipped (baseline 1428) |
| `node --test tests/plugin/agentschat.test.mjs` | 4 tests, 4 pass |
| `.venv/Scripts/ruff.exe check` | All checks passed |
| `.venv/Scripts/ruff.exe format --check` | 60 files already formatted |

No live check was run. Nothing outside a temporary home was written: the
subprocess tests redirect `HOME` and `USERPROFILE`, and `AgentschatCase` patches
`client.STORE` and `kit.DEFAULT_ROOTS`, as task 10 did.

## Noted, not touched

1. **A pre-existing flaky test, outside this task.**
   `tests/test_broker_say_status.py`,
   `StatusAsTheClientPrintsItTests.test_the_client_prints_the_rendered_lines_one_per_agent`
   renders the status line twice and compares them, and the line carries a
   wall-clock time (`подключена HH:MM:SS`). It fails whenever the two renders
   straddle a second: 1 failure in 10 runs on this tree, unrelated to install,
   the kit or the language. It belongs to task 04's code. Left alone per AGENTS.md
   0.5; the owner may want it recorded as a bug report.
2. **A Windows teardown race**, seen once during a full run and not reproduced in
   eight: `tests/test_launch_scripts.py` cleanup raised `PermissionError
   [WinError 32]` on its temporary directory. Passes on rerun; task 16's file.
3. **The room language is still not available at the kit step** (decision 2). To
   close it, `boundaries.Probe` would have to carry the language of `/status`,
   or the kit step would have to learn it another way.
4. **`client.py`'s other subcommands still have Russian help and messages.**
   `agentschat --help` is therefore a mix until tasks 08 and 09 land. This task
   did not touch them.
5. **`agentschat --help` still prints the old `-h` line** (`show this help
   message and exit`), which argparse writes itself. Task 09 owns the help of
   every subcommand.
6. **The documented exit codes of `install --json` are unchanged**: `0` done, `1`
   a failure with the client's own words, `5` a refused install. `docs/INSTALL.md`
   section 4 documents the installer's codes and did not mention the client's, so
   nothing there went stale; the client's `--json` and its code `5` are still
   undocumented for a human, which belongs to task 18.
7. **`docs/INSTALL.md` section 5.10** describes `agentschat install` as printing a
   line per file. That is still true without `--json`; the section does not
   mention `--lang`. Left for task 18 together with the rest of the guide.

## Review round 1

No blocking findings; the reviewer checked the Russian output against the old
one over 23 scenarios and it matched byte for byte. Four small changes, all of
them in.

1. **`kit.uninstall` no longer takes `lang`.** It was accepted and never used -
   the language is needed by `uninstall_summary` and `Step.line`, which the
   caller renders, not by the removal itself. Removed from `kit.uninstall`,
   from `client.do_uninstall`, and from the two test helpers that passed it
   (`KitSandbox.uninstall`, `test_a_listed_file_outside_its_root_is_removed_but_
   no_directory_is`). `kit.install` keeps `lang`, because `apply_install` raises
   `KitConflict`, which renders its sentence.
2. **`client_messages/{en,ru}.json` end with a newline again.** The `write` that
   created them dropped it, unlike every other catalogue in the repository.
3. **`tests/test_kit_installer.py`.**
   - `test_the_remembered_language_decides_the_help` repeated the first check of
     its neighbour; the neighbour was renamed to
     `test_the_russian_help_says_what_the_client_always_said` and kept the four
     Russian assertions, the duplicate is gone.
   - Two test names said "confusal"; both now say "refusal".
   - The real-client checks asserted only `CYRILLIC.search`, while the card asks
     for ASCII punctuation. The three English runs of `RealClientTests` now
     assert `stdout.isascii()` and `stderr.isascii()`, which is the stronger
     claim and subsumes the old one.
4. **The report was wrong about the forwarded flag.** It said the flag changes
   nothing a human sees. It does: on a client failure that is not a conflict,
   `participant.kit_failure` quotes `result.stderr or result.stdout` into the
   installer's report, and those words are now in the run's language. The
   decision point above is corrected: the flag is invisible on the happy path and
   visible in the quoted failure detail. A human reads that text; the installer
   never parses it - the outcome came from the document or the exit code before
   the words were looked at.

### Check results after the review

| Check | Result |
|-------|--------|
| `.venv/Scripts/python.exe -m unittest discover -s tests -t .` | 1453 tests, OK, 2 skipped |
| `node --test tests/plugin/agentschat.test.mjs` | 4 tests, 4 pass |
| `.venv/Scripts/ruff.exe check` | All checks passed |
| `.venv/Scripts/ruff.exe format --check` | 60 files already formatted |

### Edits to existing tests in this round

Three call sites lost the `lang` argument that item 1 removed
(`KitSandbox.uninstall` and one direct `kit.uninstall` call); one duplicate test
was deleted; two test names were corrected; three English assertions moved from
"Cyrillic-free" to "ASCII". No expectation text changed.