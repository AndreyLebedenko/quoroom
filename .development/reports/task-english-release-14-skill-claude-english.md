# Task english-release-14: the Claude Code chatlogin skill in English

Status: implemented, not committed, waiting for review, and **not green on this
branch** - see "The suite is red here, and why". Branch
`task/english-release-14-skill-claude-english`. No commit, no merge: the
orchestrator takes it after acceptance.

## What changed

One new file: `bridge/sessionchat/kit/en/claude/skills/chatlogin/SKILL.md`,
159 lines against the Russian 149 - the same seven sections in the same order,
the same rules, the same commands and flags, ASCII punctuation only, imperative
mood addressed to the agent. No other file was touched, apart from one constant
in `tests/test_kit.py` and the new `tests/test_skill_english.py`.

## Places where the English had to choose between two readings

These are the places a translation could have changed behaviour. Each is a
choice, not a slip.

1. **"Подтверждать приём не нужно"** - "there is no need to", not "do not".
   The Russian forbids nothing; it says an acknowledgement is unnecessary. The
   project rule says a soft Russian "не нужно" becomes "there is no need to", and
   the envelope says exactly that in English
   (`broker.envelope_acknowledgement_not_needed`: "There is no need to
   acknowledge receipt: the sender sees their own message in the room."). The
   skill now uses the envelope's own wording, so the instruction the agent reads
   in the skill and the line it reads in the envelope are the same sentence.
2. **"Не перехватывай молча"** - "Do not take the slot over silently." A hard
   prohibition in the Russian, kept hard. The temptation was "avoid taking over
   without saying so", which reads as advice; rejected.
3. **"Не делай вывод, что слот занят тобой же"** - "Do not assume the slot is
   held by you." "Вывод" is a conclusion, "assume" is an assumption; the broker's
   own refusal uses "Do not assume the slot is held by you"
   (`broker.slot_taken_not_yours`), so the skill and the refusal now share the
   wording. The Russian skill paraphrases that sentence and does not quote it;
   the English therefore does not quote it either - the same words, used as
   instruction rather than presented as a quotation.
4. **What identifies the slot refusal.** The Russian skill says «Если получен
   отказ «уже подключён»» - it quotes a phrase that no longer exists in the
   broker. The English names the refusal by the wording that does exist:
   "a refusal saying that the agent `has been connected since`", a fragment of
   `broker.slot_taken` ("Agent {agent} has been connected since {registered}
   ({label}, {state_word})."). A fragment, not the whole sentence, because the
   agent does not know the parameters. The refusal code `slot_taken` exists in
   the JSON body and in the `AGENTSCHAT-RESULT` line, and the Russian skill never
   mentions that line, so the English does not either.
5. **"связь с брокером потеряна"** - "broker connection lost", the client's own
   title `wait_broker_lost_title`. Quoted exactly, as the Russian quotes its
   line.
6. **"тип: человек или агент"** - the envelope prints `(human)` and `(agent)`,
   from `broker.envelope_kind_human` / `broker.envelope_kind_agent`. The skill
   quotes the two words, because those are what the agent sees in the
   `From:` line.
7. **"НЕ жди её завершения"** (about the background command) - "do NOT wait for
   it to finish", with the capital NOT kept. The client's own sentence
   (`login_listener_start`: "... and do not wait for it to finish") is softer, but
   this is a skill instruction to a model, and the Russian capitalises НЕ to
   carry the emphasis. Keeping the capital is the closer match.
8. **"Подтверждать приём не нужно: отправитель видит своё сообщение"** - the
   Russian gives the reason in the same breath. The English keeps the reason,
   because it is the reason an agent can check for itself.
9. **"На первой живой проверке трио агента"** - "On the first live check three
   agents". The Russian says "три агента"; the number and the fact stay, nothing
   is added about what to do instead beyond what the Russian already says.
10. **Section titles.** "Подключение" / "Отключение" became "Connecting" /
    "Disconnecting"; "Границы" became "Boundaries" (AGENTS.md uses the same
    word); "Где это лежит" became "Where this lives". No title was merged or
    split.

## Where the English is silent, because the Russian is

- The `AGENTSCHAT-RESULT` line (task 08) is not mentioned anywhere.
- No new advice, no new example, no new command. The English introduces
  nothing the Russian does not have.
- The boundaries section has the same six rules, in the same order, with the
  same force: a test counts them on both sides.

## Quoted phrases and where they live

| Phrase in the skill | Catalogue | Key |
|---------------------|-----------|-----|
| `=== AGENTSCHAT: incoming message ===` | broker | `broker.envelope_open` |
| `has been connected since` | broker | `broker.slot_taken` |
| `human` | broker | `broker.envelope_kind_human` |
| `agent` | broker | `broker.envelope_kind_agent` |
| `broker connection lost` | client | `wait_broker_lost_title` |

The envelope's first line is quoted exactly, so that one is checked for
equality with the rendered template; the rest are substrings. The envelope is
assembled from several keys, and the skill quotes only fragments that each
belong to one key - the words `(human)` and `(agent)` come from the kind keys
that the `From:` line interpolates - so key-per-fragment is the honest rule
rather than pinning the whole assembled envelope.

The test also runs the other way: every inline code span in the skill must be a
command, a flag, a placeholder, a plain name (`agentschat`, `claude-code`,
`opencode`, `inbox`, `ask`, `status`, `config.yaml`,
`run_in_background: true`), an addressing form (`@name`, `@room`,
`@human ...`) - or one of the five quoted phrases. A new quotation without a
catalogue entry therefore fails the test, and a Russian phrase pasted into the
English fails it too (checked: the Russian line is not a substring of the
English key).

## Tests

`tests/test_skill_english.py`, 11 tests:

- no Cyrillic; ASCII punctuation only (`[\x20-\x7e\n]` fullmatch); the
  frontmatter declares `name` and `description`;
- the same number of `##` sections as the Russian skill, and the same number of
  rules in the boundaries section;
- the commands and flags mentioned in the English skill are exactly those in
  the Russian one, and the four shared commands plus `wait` are present;
- the quoted phrases, both directions, as described above.

`tests/test_kit.py`: `EXPECTED_KIT_FILES` gained
`en/claude/skills/chatlogin/SKILL.md`. That is the content of the file set, not a
statement about variant choice; the same line is the one the per-CLI variant
work will touch, so it may show up as a trivial merge.

I did **not** add a language-pair agreement test to `tests/test_kit.py`: the
English skill is compared against the Russian one in `test_skill_english.py`,
scoped to the pair, and the layout-wide sweep is the shared test that the
per-CLI variant work owns.

## The suite is red here, and why

Adding `kit/en/claude/...` makes `kit/en/` exist, and the variant choice on this
branch is still "does the directory `kit/<lang>` exist" (task 13's code). So an
`--lang en` install now finds a directory, takes it as the whole variant, and
lays down the Claude skill with **no** OpenCode skill and no command, and
reports no substitution. That is the defect the review found, and the fix
(per-CLI choice, with `kit_variant_missing` for a CLI without a variant) is
being done by another executor in `kit.py` and `tests/test_kit.py`. I left both
alone as instructed.

Exactly 14 checks are red because of it, and all 14 are in files that fix
touches:

| Check | Why the per-CLI fix clears it |
|-------|-------------------------------|
| `test_kit.SkillAgreementTests.*` (3) | reads `<lang>/opencode/skills/...`, which `en` does not have yet |
| `test_kit.KitContentsTests.test_every_variant_directory_holds_the_same_relative_paths_for_both_clis` | asserts every variant has both CLIs; per-CLI choice makes that legal |
| `test_kit.TemporaryRussianOnlyVariantTests.*` (2) | pins the state that this task ends |
| `test_kit_installer.ReportTests.test_a_repeat_install_reports_every_file_as_unchanged` | mixes an `en` install with an `ru` one; with the fallback both write the same files |
| `test_kit_installer.ReportTests.test_the_steps_of_the_document_do_not_depend_on_the_language` | same cause: the `en` steps were missing the OpenCode files |
| `test_kit_installer.TemporaryVariantFallbackTests.*` (4) | `variant_of("en")` returns `none` while the directory exists |
| `test_kit_installer.VariantChoiceTests.test_the_variant_files_land_at_the_same_paths_every_language_uses` | the `en` install wrote only the Claude file |
| `test_kit_installer.VariantChoiceTests.test_a_manifest_of_the_previous_layout_is_read_by_the_new_one` | the `en` install rewrote only one manifest entry |

`tests/test_skill_english.py` and `tests/test_packaging.py` are green on this
branch, and `node --test` is green.

## Check results

| Check | Result |
|-------|--------|
| `.venv/Scripts/python.exe -m unittest discover -s tests -t .` | 1631 tests, 10 failures + 4 errors, 2 skipped - all 14 listed above |
| `node --test tests/plugin/agentschat.test.mjs` | 28 tests, 28 pass |
| `.venv/Scripts/ruff.exe check` | All checks passed |
| `.venv/Scripts/ruff.exe format --check` | 68 files already formatted |

## Owner review

The card's third acceptance criterion is the owner's approval of the English
text, and that is **not** mine to close. The ten places above are the ones to
read first; the rest is a one-to-one rendering of the Russian.

## Noted, not touched

1. **The OpenCode English skill and command** are task 15; until then an
   `--lang en` install gives an OpenCode user Russian files (with the per-CLI
   fix) and says so through `kit_variant_missing`.
2. **The OpenCode command file has no agreement test** - it names `--agent` and
   `--label` and defers to the skill, so its command set cannot equal a skill's.
   Task 13's report already recorded this; task 15 is the place to settle it.
3. **`kit_variant_missing` and the fallback** stay until task 15, as the
   orchestrator's note for task 14 requires.
4. **The quoted-phrase table is a list of five rows.** If a later card makes the
   envelope print anything else the agent must recognise, the table grows here
   rather than in the text.