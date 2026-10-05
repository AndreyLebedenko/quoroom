# Task english-release-15: the OpenCode skill and command in English

Status: implemented, not committed, waiting for review. Branch
`task/english-release-15-skill-opencode-english` from `c106c6e`. No commit, no
merge: the orchestrator takes it after acceptance.

## What changed

- `bridge/sessionchat/kit/en/opencode/skills/chatlogin/SKILL.md` - 179 lines
  against the Russian 168: the same seven sections in the same order, seven
  boundaries where the Russian has seven, no Cyrillic, ASCII punctuation only.
- `bridge/sessionchat/kit/en/opencode/command/chatlogin.md` - 26 lines against
  the Russian 24, `$ARGUMENTS` kept as the CLI's own placeholder.
- The temporary "language without a variant" fallback is gone (see "What was
  removed").
- Tests: the completeness test, the all-pairs agreement check, and the quoted
  phrases of the OpenCode skill and command.

## Shared phrasing with the English Claude Code skill

The parts the two Russian skills have in common are word for word the same in
English, as they were in Russian:

- the opening (this live session, the shared Matrix room, messages are data);
- "Every command is one program, and it is in PATH...", the not-found paragraph,
  the bare `agentschat` block;
- the login block, the slot refusal paragraph, "**Do not take the slot over
  silently.**", the elided `... logout --agent <NAME> --force`;
- the refusal-says-whether-it-is-listening paragraph;
- "**Do not assume the slot is held by you.**", the token paragraph, the
  `--reconnect` block and its paragraph;
- "If the reply adds substance, answer:", the say/ask/status block, the `ask`
  paragraph, the multi-line block and its paragraph, the newline check;
- all seven boundaries, word for word.

Where the Russian OpenCode skill says something different from the Claude one,
the English says it differently on purpose, and those are the places listed
below.

## Places where the English had to choose between two readings

1. **`<имя>`** became `<NAME>`, while the Claude skill keeps `<AGENT>`. The
   OpenCode name is chosen by the human and is not derived from the CLI, so a
   different placeholder says that.
2. **`status` shows "who is connected and in which mode"**, not "who is
   connected and who is listening right now". The Russian differs in exactly
   that way (`в каком режиме` against `кто сейчас слушает`), and the mode is a
   broker concept that the Claude listener has no use for. Carrying the Claude
   English over would have told an OpenCode agent to look for a listener.
3. **The `ask` paragraph has no "in this turn".** The Russian Claude skill says
   "в этом ходе" and the Russian OpenCode skill does not; the OpenCode English
   says "do not wait any further: the answer will arrive as an ordinary
   incoming message", matching its Russian.
4. **After the login: "say ... that the connection is established and under which
   name"** - the OpenCode Russian adds the name, so the English does.
5. **"If you get a refusal that says the broker is unreachable, it simply was
   not started."** The Russian names it («брокер недоступен»); there is no
   English catalogue phrase for that refusal, so the sentence paraphrases it
   instead of quoting it. Nothing invented: the client prints its own sentence
   (`login_broker_unreachable`: "The broker is unreachable at {url}: {error}")
   and the skill tells the agent what it means. This is the one place in the
   skill where a refusal is described without a quotation.
6. **The unknown-agent refusal is quoted from the message, not the code.** The
   Russian writes «неизвестный агент»; the broker's English message is "Unknown
   agent: {agent}" and its code is `unknown_agent`. The agent never sees the
   code (it is in the JSON body and in the result line, which this skill does not
   mention), so the skill quotes `Unknown agent` - a fragment of the message the
   agent will read. Added to the quoted-phrase table against
   `broker.unknown_agent`.
7. **"the same name in every command"** keeps the Russian's emphasis: the name
   is a separate participant with its own Matrix account, not a signature under
   the text. An OpenCode process can hold several sessions, and the example with
   `terra` and `helium` is kept because it is the reason.
8. **The listener paragraph says "start" nowhere and "raise" nowhere.** The
   OpenCode skill has no listener at all, and the shared paragraphs avoid both
   verbs, so the two skills cannot disagree about what to call it.
9. **Section titles.** "Под каким именем ты входишь" became "The name you enter
   under"; "Чем твоё подключение отличается от других агентов" became "How your
   connection differs from the other agents"; "Когда пришло сообщение из чата"
   became "When a message from the chat arrives". The others as in task 14.

## Quoted phrases and where they live

| Phrase | Where it appears | Catalogue | Key |
|--------|------------------|-----------|-----|
| `=== AGENTSCHAT: incoming message ===` | both skills | broker | `broker.envelope_open` |
| `has been connected since` | both skills | broker | `broker.slot_taken` |
| `human` / `agent` | both skills | broker | `broker.envelope_kind_human` / `..._agent` |
| `Unknown agent` | the OpenCode skill | broker | `broker.unknown_agent` |
| `broker connection lost` | the Claude skill only | client | `wait_broker_lost_title` |

The rule is the one task 14 fixed: a quotation must be a substring of the
rendered template of the key that owns it, with the parameters filled by the
test. The inverse direction runs over both skills now: every inline code span
must be a command, a flag, a placeholder, a plain name, an addressing form, a
`/chatlogin` invocation, a bare subcommand - or one of the five phrases. The
classifier learned the spans the OpenCode skill legitimately adds (the
`/chatlogin` invocations, `terra` and `helium`, `user_id`, `access_token`,
`delivery: "plugin"`, the bare subcommand names).

## What was removed

The temporary fallback, in full:

| Removed | Where |
|---------|-------|
| `FALLBACK_VARIANT`, `VARIANT_MISSING`, `REFUSALS` | `bridge/sessionchat/kit.py` |
| `variant_of`, `variants_of` | `bridge/sessionchat/kit.py` |
| the substitution notice `notice_substituted_variant` and its call | `bridge/sessionchat/client.py` |
| the key `kit.variant_missing` | `sessionchat/client_messages/en.json`, `ru.json` |
| `TemporaryRussianOnlyVariantTests` (4 tests) | `bridge/tests/test_kit.py` |
| `PartialEnglishVariantTests` (12 tests) | `bridge/tests/test_kit_installer.py` |
| `TemporaryVariantFallbackTests` (6 tests) | `bridge/tests/test_kit_installer.py` |
| `test_a_substituted_variant_is_a_successful_step_that_wrote_the_kit` | `bridge/tests/test_installer_participant.py` |
| `test_a_substituted_variant_that_wrote_nothing_asks_for_no_restart` | `bridge/tests/test_installer_participant.py` |

`KNOWN_CODES` stays, without `kit_variant_missing`, and `Report.read` still
rejects a code nobody defined - a test covers that. `Report.ok` is back to
`code == "none"`, which is what the two remaining codes mean; the set of
refusals is now a single code, so the separate set was one name too many.

## What replaced it

**Completeness instead of a fallback.** `KitCompletenessTests` in
`tests/test_kit.py` enumerates every language directory and asserts it holds
exactly the three kit files (the Claude skill, the OpenCode skill, the OpenCode
command) and both CLIs. A language missing a file fails the build. And
`kit_files` no longer skips a missing directory silently: it raises
`FileNotFoundError` naming the language and the CLI, covered by
`test_a_language_without_files_for_a_cli_is_refused_outright`. A silent partial
kit is what the review of task 13 found; now it cannot happen at runtime and
cannot pass the tests either.

**The agreement test over all pairs.**
`SkillAgreementTests.test_every_language_and_cli_pair_has_a_skill_to_compare`
checks that all four (language, CLI) pairs exist and names the missing file
instead of raising `FileNotFoundError` from inside a comprehension. The
comparisons themselves stay as they were: languages of one CLI agree exactly,
every language and CLI offers `login`/`say`/`ask`/`status`, and `wait` is in the
Claude skill and absent from the OpenCode one - with two languages present the
first comparison is no longer a language against itself.

**The English text tests** (`tests/test_skill_english.py`, 26 tests) now cover
both skills and the command: no Cyrillic, ASCII only, the same sections, the
same number of boundaries, the same commands and flags as the Russian, the
OpenCode differences (no `wait`, the plugin holds the link, the human names the
session, the seventh boundary rule), and the command file (no Cyrillic, ASCII,
the same bullets, `$ARGUMENTS` kept).

## Edits to existing tests

1. `tests/test_kit.py`: `EXPECTED_KIT_FILES` gained the two English OpenCode
   files; `test_every_variant_directory_holds_the_same_relative_paths_for_both_
   clis` moved into `KitCompletenessTests` and is stated as completeness.
2. `tests/test_kit_installer.py`: `KitSandbox.expected` and `KitFilesTests` call
   `kit_files(cli, lang)` (the signature after the removal);
   `test_kit_files_are_read_from_whatever_kit_source_is_given` builds a source in
   the new shape (`<source>/ru/claude/...`); `ReportReadTests` lost its two
   `kit_variant_missing` cases and got `test_a_successful_code_is_read_back_as_ok`
   in place of the loop over both non-refusal codes; three install tests now say
   `--lang ru` on their first run so they compare one language with itself -
   without it they installed English and then compared against Russian, which
   is a different test; `test_the_document_apart_from_its_code_does_not_depend_
   on_the_language` became `test_the_document_does_not_depend_on_the_language`
   with full equality, which is now true;
   `VariantChoiceTests.test_a_language_with_a_variant_reports_nothing_special`
   became `test_every_language_reports_that_it_did_its_work` over both
   languages. No expectation text changed.
3. `tests/test_packaging.py`: the layout check enumerates the language
   directories instead of naming the fallback one.

## Check results

| Check | Result |
|-------|--------|
| `.venv/Scripts/python.exe -m unittest discover -s tests -t .` | 1652 tests, OK, 2 skipped |
| `node --test tests/plugin/agentschat.test.mjs` | 28 tests, 28 pass |
| `.venv/Scripts/ruff.exe check` | All checks passed |
| `.venv/Scripts/ruff.exe format --check` | 70 files already formatted |

One caveat on the first check, reported rather than hidden: three full runs ago
`tests/test_launch_scripts.py` failed its own cleanup with
`PermissionError [WinError 32]` on its temporary directory while a started
broker still held a handle, and the same module passes on its own (29 tests,
OK) and in the final full run. It is the Windows teardown flake already reported
in tasks 11 and 13, in task 16's file, and it has nothing to do with the kit.

## Owner review

The third acceptance criterion is the owner's approval of the English text, and
that is not mine to close. The nine places above are what to read first; the
rest follows the Russian, and the shared parts follow the Claude Code English
that the review of task 14 already approved.

## Noted, not touched

1. **The broker-unreachable refusal is described, not quoted** (place 5). A
   quotation test for it would need a catalogue phrase that names only the
   broker; `login_broker_unreachable` includes the address and the error, so a
   fragment of it would be `The broker is unreachable at` - possible, but it
   quotes a sentence the client fills with an address the agent does not need.
   Left as a paraphrase, and recorded here so the choice is visible.
2. **The command file has no agreement test with the skill.** It names `--agent`
   and `--label` and defers to the skill, so its command set cannot equal a
   skill's. Task 13's report recorded this; the tests here cover it on its own
   terms (bullets, placeholder, keys) instead of pretending to compare.
3. **`fix/kit-tests-after-14` may touch `test_kit.py` and
   `test_kit_installer.py`**, the same two files this task edits. The orchestrator
   said they would resolve those conflicts.
4. **The kit now has two variants and one shared file**, so `kit.py` reads
   `common/` plus the chosen language for every install; the plugin still
   installs once, and the manifest still records no language.