# Task english-release-13: the kit ships a variant per language

Status: implemented, not committed, waiting for review. Branch
`task/english-release-13-kit-language-layout` from `55835ca`. No commit, no
merge: the orchestrator takes it after acceptance.

## What changed

The kit in the package is now split by language:

```
kit/common/opencode/plugins/agentschat.js
kit/ru/claude/skills/chatlogin/SKILL.md
kit/ru/opencode/command/chatlogin.md
kit/ru/opencode/skills/chatlogin/SKILL.md
```

`kit/en/` **does not exist yet** - git cannot hold an empty directory, and the
English skills are tasks 14 and 15. So today there is one variant, `ru`, plus
the shared plugin. `agentschat install --lang en` therefore falls back to `ru`
and says so; that fallback is temporary and lives in one small block (below).

`install --lang` picks the variant. Destination paths and manifest keys do not
mention the language, so switching language is the ordinary update path and a
manifest written by the previous layout is read by the new one.

## Decisions and reasons

1. **`install` and `uninstall` return a `Report`, not a list of steps.** The
   install has to tell the caller which code to report, and the only honest way
   to carry that is the document itself. Both commands return the same type
   because both have documents, and the client then does one thing with it.
   `uninstall` always reports `none`: the removal reads the manifest, it chooses
   no variant.
2. **`ok` no longer means `code == "none"`.** It means "the command did its
   job", so the codes that count as a refusal are named once, in `REFUSALS`.
   Task 10/11 wrote `ok` as `code == "none"` because there were exactly two
   codes; the third code this card introduces is not a refusal - the kit *is* on
   disk - and collapsing it into `ok: false` would have failed every English
   participant install between this card and task 15. `Report.read` checks the
   same rule the writer uses.
3. **The fallback and its code are one small block.** `COMMON`,
   `FALLBACK_VARIANT`, `VARIANT_MISSING`, `REFUSALS` and `variant_of` sit
   together in `kit.py`; the tests that pin the temporary behaviour are
   `TemporaryRussianOnlyVariantTests` in `tests/test_kit.py` and
   `TemporaryVariantFallbackTests` in `tests/test_kit_installer.py`. Task 15
   deletes those and the English directory appears.
4. **`kit_files` merges `common/` and the variant, sorted by destination path.**
   The plugin is one file every language shares, so it is read from `common`
   and appended to whatever the variant holds. Sorting by the relative path
   keeps the reported order identical to the pre-move order (the manifest
   already sorted by path), which is why `test_a_first_install_reports_every_
   file_as_installed` still holds unchanged.
5. **The human is told about a substitution on stderr.** In `--json` mode stdout
   carries only the document, so the notice goes to stderr in both modes. The
   installer does not echo it: during tasks 13-15 a human running
   `install.sh --role participant --lang en` gets the Russian skills without
   seeing this line. That gap closes itself in task 15, when the English variant
   exists and there is nothing to announce. Recorded rather than worked around.
6. **The agreement test compares languages within a CLI, and pins the by-design
   difference.** AGENTS.md Tooling note 4 says the two `chatlogin` skills differ
   by design - OpenCode has no background listener, the plugin holds the
   connection - so "the two CLIs mention the same commands" is false by design
   (`wait` is in the Claude skill only). What the test asserts instead:
   - all languages of one CLI mention exactly the same commands and flags;
   - every language and every CLI offers the four commands AGENTS.md names as
     the shared contract: `login`, `say`, `ask`, `status`;
   - `wait` is in the Claude skill and absent from the OpenCode one, so the
     difference is pinned rather than accidental.

   With one language present the first check compares one item to itself. That
   is why `TemporaryRussianOnlyVariantTests.test_only_the_russian_variant_ships`
   states the temporary state outright: when task 14 adds `en`, that test fails
   and the comparison becomes real.

   The extraction rule, fixed in the test: drop the lines that open a fenced
   block, take the subcommand as the token right after the word `agentschat`,
   and take every `--flag` token from the rest of the text. Mechanical, and the
   same for every language and both CLIs.

## Moved files (byte for byte)

Digests are sha256 of the files as they were at `55835ca`, before the move, and
they are the values the test carries:

| From | To | sha256 |
|------|----|--------|
| `kit/opencode/plugins/agentschat.js` | `kit/common/opencode/plugins/agentschat.js` | `e7174ac13507160eaab5e67765b8eb3e26c7dfef19502b81835e9cf8c9b3b323` |
| `kit/claude/skills/chatlogin/SKILL.md` | `kit/ru/claude/skills/chatlogin/SKILL.md` | `b1636a875c799a8330ffc6bb723acd092e73ff4bf9e369f2131c49998e3ac2d9` |
| `kit/opencode/command/chatlogin.md` | `kit/ru/opencode/command/chatlogin.md` | `565d7bf44ee097c599fa640c97147218bc9f3b049bd279eb3a825bda5885673b` |
| `kit/opencode/skills/chatlogin/SKILL.md` | `kit/ru/opencode/skills/chatlogin/SKILL.md` | `cacf11d43d4ca71c86678b113167a758adc935040feb50b57d1cfb39b5a18849` |

All four moved with `git mv`, and git records them as renames.

## Codes and keys

- Codes: `kit.VARIANT_MISSING` = `kit_variant_missing`, and `kit.REFUSALS` =
  {`conflict`} - the set that makes a document `ok: false`. Nothing else.
- Key: `kit.variant_missing` in `client_messages/{en,ru}.json`, placeholders
  `{language}` and `{fallback}` in both. English: "AGENTSCHAT: there is no
  Quoroom kit variant for {language} yet, so the {fallback} one was laid down.
  Re-run agentschat install --lang {language} once it exists."
- No other catalogue key changed.

## What a human sees

- **Fallback (`--lang en` today).** The kit lands, the document says
  `code: kit_variant_missing` with `ok: true`, and stderr carries the `AGENTSCHAT:`
  line above. A human running the client directly sees it. A human running the
  participant installer does not, because the installer quotes neither the
  document nor the client's stderr in its report - see decision 5.
- **Changing the language.** `agentschat install --lang ru` after an `--lang en`
  run is an ordinary update: the files listed in the manifest are rewritten
  through the update path, so a hand-edited file is still kept (or conflicts)
  exactly as before. Nothing extra to clean up and no language in the manifest.
- **A bare `agentschat install`** picks the remembered room language, then `en`,
  which today means the Russian variant plus the notice.

## Edits to existing tests

Paths and constructions only; no expectation text was changed.

1. `tests/test_broker_url.py`, `PLUGIN_SOURCE`: the plugin moved to
   `kit/common/opencode/plugins/agentschat.js`. The test that reads the plugin's
   fallback URL out of the source needed no other change.
2. `tests/plugin/agentschat.test.mjs`, two occurrences of the plugin path
   (`../../sessionchat/kit/opencode/plugins/agentschat.js` ->
   `.../kit/common/opencode/plugins/agentschat.js`). The file is loaded, not
   parsed for layout, so nothing else moved.
3. `tests/test_kit.py`, `EXPECTED_KIT_FILES`: the four paths now carry their
   `common/` or `ru/` prefix. `BASE_DIGESTS` is new and holds the values above.
4. `tests/test_kit_installer.py`:
   - `KitSandbox.expected` and `KitFilesTests` pass the resolved variant to
     `kit.kit_files(cli, variant)` (new signature);
   - `KitSandbox.install` / `.uninstall` return the `Report`, so nine call sites
     that consumed steps now read `.steps` (`steps = self.install().steps`,
     `self.uninstall().steps`, and one `assertEqual(..., ())` for the empty
     removal);
   - `test_kit_files_are_read_from_whatever_kit_source_is_given` passes an
     explicit variant directory;
   - `ReportTests.document` gained a `lang=RUSSIAN` parameter, because those
     tests compare whole documents and the default language now reports the
     substitution;
   - `test_the_document_does_not_depend_on_the_language` became
     `test_the_steps_of_the_document_do_not_depend_on_the_language`: the steps,
     the command and `ok` must match across languages, while the `code` is
     exactly where the substitution is reported. The old assertion (identical
     documents) became false the moment a language could report a substitution,
     and the new one is the part that must stay language-independent.
5. `bridge/pyproject.toml`: **no change needed** - `kit/**/*` already matches
   `kit/common/opencode/plugins/agentschat.js` and every `kit/ru/...` file. The
   new `KitFilesAreShippedTests` in `tests/test_packaging.py` proves it by
   shipping check rather than by reading the pattern, so a future layout that
   `**/*` stops covering would fail.

## Tests added

`tests/test_kit.py`: the moved bytes against the digests above; the plugin is
the only file under `common/`; every variant directory holds the same relative
paths for both CLIs; the agreement test and the two temporary-state tests.

`tests/test_kit_installer.py`: `VariantChoiceTests` (a language with a variant
reports `none`; both languages land at the same paths with the same bytes; the
manifest mentions no language; a manifest from the previous layout is read and
every file is re-installed over it; a second install over the same variant
changes nothing) and `TemporaryVariantFallbackTests` (the kit still lands, the
fallback lays down exactly the existing variant, the human is told, the document
carries the code with `ok: true`, and a language with a variant says nothing).

`tests/test_packaging.py`: every kit file of every variant is matched by a
package-data entry, and the scan finds the files of the new layout.

## Check results

| Check | Result |
|-------|--------|
| `.venv/Scripts/python.exe -m unittest discover -s tests -t .` | 1620 tests, OK, 2 skipped (baseline 1598) |
| `node --test tests/plugin/agentschat.test.mjs` | 28 tests, 28 pass |
| `.venv/Scripts/ruff.exe check` | All checks passed |
| `.venv/Scripts/ruff.exe format --check` | 66 files already formatted |

No live check was run. Nothing was written outside the temporary homes the tests
make.

## Documents

- `docs/INSTALL.md` section 5.10: a Russian paragraph naming the layout, that
  `--lang` picks the variant, that paths and the manifest do not depend on the
  language, and that `--lang en` currently lays down Russian and says so.
- `docs/SESSION_BRIDGE.md`, in the kit section: the architectural decision (one
  variant per language, one shared plugin, language-free paths and manifest,
  who installs with which language), what breaks without it, and why the two
  skills differ in flags while agreeing in content.

## Noted, not touched

1. **The installer does not surface the substitution** (decision 5). A human
   installing an English participant gets Russian skills with no word about it
   until task 15 removes the fallback.
2. **`agentschat install --lang` still cannot see the room language**, because
   the installer's kit step runs before `check_broker`. Unchanged on purpose
   here; the orchestrator's note for task 11 stands.
3. **`opencode/command/chatlogin.md` has no agreement test.** It is a thin
   wrapper that names `--agent` and `--label` and defers to the skill, so its
   command set cannot equal a skill's. If tasks 14/15 give it real content, the
   agreement test should cover it as a third file of the OpenCode variant.
4. **The manifest format is untouched**, as the card requires: entries are still
   path, sha256 and cli. Nothing about the variant is recorded there, so a later
   task that wants to know which language is installed must add it deliberately.
5. **`kit.py` gained no Cyrillic** (it had none since task 11) and the Russian
   files moved without a byte changed; the digests above are the proof and a test
   holds them.