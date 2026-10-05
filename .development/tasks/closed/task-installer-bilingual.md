# Task installer-bilingual: English by default, Russian on request

**Status:** Completed.
**Blocks:** the v1.0.0-rc.2 tag (owner decision: bilingual installer before
the release).
**Depends on:** story local-installers (completed).

## Summary

Every message the installer shows a human - step names, prompts, refusals,
reports, usage errors, the purge confirmation - exists in English and in
Russian, from a message catalogue kept in resource files. English is the
default. `--lang ru` switches to Russian. Behaviour, exit codes, and the
machine-read words (`PURGE`, flag names, role names) do not change.

## Why

README.md is now English and the main one. A first-time reader runs
`install.ps1` and gets Russian, and nothing in the command line says how to
change that. The Russian text is currently written into about 310 lines of the
installer package and about 10 lines of the two wrappers, so it cannot be
swapped without moving it out first.

## Context you need

- AGENTS.md: rule 9 (ASCII punctuation in English text; Russian is data and
  keeps normal typography), rule 7 (no comments), locality contract (no
  secrets in messages: `Secrets.scrub` still applies to every rendered line),
  Testing protocol, 0.4 (stop when an architectural choice has trade-offs).
- Where the text lives today, by Cyrillic-bearing line count:
  `server.py` ~190, `participant.py` ~75, `steps.py` ~16, `options.py` ~10,
  `roles.py` 5, `boundaries.py`, `confirmation.py`, `main.py` 3 each,
  `secrets.py` 1; `install.ps1` 6, `install.sh` 4.
- Text reaches the human through: `Run.say`, `Run.warn`, `Run.warn_once`,
  `NeedsHuman(...)`, `UsageError(...)`, `Failure.render`, `HumanStep.instruction`,
  the `Step.name` dataclass defaults, `State` and `Outcome` enum values,
  `Confirmation.ask`, `Left` items in `report.py`, the argparse `help` and
  `description`, and module constants (`RESUME`, `NO_ROLES`,
  `PASSWORD_MISMATCH`, `DEFAULT_CONSEQUENCE`, `PREPARE`, `REPORT`).
- Many messages are assembled from fragments (the session-files line and the
  restart instruction in `participant.py`, the consequence line in the purge
  confirmation). Fragments do not translate: each sentence becomes one
  catalogue entry with named placeholders, and the choice between variants
  stays in code.
- Step names are also identity: `Run.completed`, `warn_once` keys, and the
  failure report use them. Identity must not depend on the language.

## Design to settle before coding (AGENTS.md 0.4)

The implementer states the chosen option and the reason in the task report.
Recommended option first.

1. **Where the language lives.** Recommended: in `Boundaries` (as `lang`),
   injected like every other outside fact, and read by one renderer
   `messages.text(lang, key, **params)`; no module-level global. Alternative:
   a module global set once in `main` - smaller diff, but tests that run two
   languages in one process share state.
2. **Step names.** Recommended: a step keeps a stable key and its display name
   is rendered from the catalogue at the moment of printing. Module-level
   constants and enum values that carry text become keys or are rendered at
   use.
3. **Catalogue format.** Recommended: one JSON file per language under
   `bridge/sessionchat/installer/messages/` (`en.json`, `ru.json`), flat keys,
   `str.format` templates, loaded with `importlib.resources`, and listed in
   `[tool.setuptools.package-data]` in `bridge/pyproject.toml`. Alternative:
   two Python dict modules (no packaging change, but not "resource files").

## Boundary

- `bridge/sessionchat/installer/**`, `install.ps1`, `install.sh`,
  `bridge/pyproject.toml` (package-data only), the installer tests,
  `docs/INSTALL.md`, `README.md`, `README.ru.md`, `CHANGELOG.md`, and
  `docs/VERIFICATION.md` (the pending scenario text only).
- Out of scope: runtime strings of the broker, the `agentschat` client and the
  kit skills (`bridge/sessionchat/broker.py`, `client.py`, `kit/**`); the
  Russian documents in `docs/`. See the first open question.

## Requirements

- `--lang en|ru`, default `en`. Any other value is a usage error (exit 2) whose
  text is in English. The flag works before the role is known, applies to
  `--help` (description and every `help=`), and is accepted by both wrappers.
- The wrappers' own messages (the ones printed before Python starts) exist in
  both languages and follow `--lang`; the wrappers scan their arguments for it
  and pass it on unchanged.
- Every user-visible installer string moves to the catalogue. No Cyrillic and
  no English sentence remains in installer code outside the catalogue and the
  Russian test fixtures, except identifiers, flag names, `PURGE`, and the
  words of external tools' own output.
- English text follows AGENTS.md rule 9 (ASCII punctuation). Russian text keeps
  normal Russian typography and is, character for character, what the
  installer prints today.
- The two catalogues have the same keys, and each key has the same set of
  placeholders in both. A missing key in the requested language is a test
  failure, not a silent fallback at run time.
- Rendering goes through `Secrets.scrub` exactly as now; no catalogue text or
  placeholder path bypasses it.
- Exit codes, the purge confirmation word, ownership records, and step
  identity do not depend on the language. A record written in one language is
  read in the other.

## Slices (in this order; each ends with the full suite green)

1. **Mechanism and the small modules.** Catalogue loader, renderer,
   `Boundaries.lang` (or the chosen carrier), `--lang` parsing, the
   completeness and placeholder-parity tests, then `steps.py`, `options.py`,
   `roles.py`, `confirmation.py`, `main.py`, `boundaries.py`, `secrets.py`,
   `report.py`.
2. **`participant.py`** - including the report and restart wording
   (sentence-level entries, variants chosen in code).
3. **`server.py`** - the largest module; the same rules.
4. **Wrappers and docs.** `install.ps1`, `install.sh`, `INSTALL.md` (the flag,
   the default, an example), README files, CHANGELOG, VERIFICATION.

If slice 3 turns out larger than a day, split it into its own card and say so
in the report (AGENTS.md 0.3).

## Tests

- Every existing installer test keeps asserting the Russian text unchanged: it
  runs with `lang="ru"`. Nothing in an existing expectation is edited to make
  it pass; a changed Russian string is a defect.
- New: with no flag, a full participant install, a full server install, a
  removal, a purge with confirmation, a usage error and a failure report
  print no Cyrillic at all, stdout and stderr both.
- New: `--lang ru` and `--lang en` run the same scenario and end with the same
  exit code and the same set of completed step keys.
- New: `--lang xx` gives exit 2 and an English message.
- New: the catalogue tests from Requirements (same keys, same placeholders; no
  Cyrillic in `en.json`; ASCII-only punctuation in `en.json`).
- New: a record written under one language is read under the other (purge
  confirmation lists the same targets).
- `test_entry_points.py`: both wrappers print their own refusals in English by
  default and in Russian with `--lang ru`.

## Acceptance criteria

- [ ] `.\install.ps1 --role participant` on a clean machine prints English only
      from the first line to the report; `--lang ru` prints what it printed
      before this task.
- [ ] No installer string outside the catalogue (check by a test that scans
      the package for Cyrillic outside `messages/` and the allowed fixtures).
- [ ] Catalogue parity tests pass; adding a key to one language alone fails
      the suite.
- [ ] All existing installer tests pass unchanged under `lang="ru"`.
- [ ] `docs/VERIFICATION.md` pending Linux scenario says which language its
      expected lines are in (`--lang ru` in the commands, or English
      expectations); the recorded Windows run is not edited.
- [ ] `docs/INSTALL.md` documents `--lang`; both READMEs mention it.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green,
      run one after another from `bridge/`.
- [ ] The report lists the three design choices and why.

## Open questions (answer before implementation)

1. `agentschat install` and `agentschat login` print Russian (client and kit,
   out of scope here). A participant install therefore shows a Russian block in
   the middle of an English run. Options: (a) accept it and say so in INSTALL.md
   until a follow-up card moves the client strings; (b) make the same card
   cover the client's install and uninstall messages. Recommended: (a), and
   open the follow-up card now so the gap has an owner.
2. An environment variable (`QUOROOM_LANG`) as an alternative to the flag?
   Recommended: no, the flag only; one way to do it.
3. Should the English `docs/INSTALL.md` be a separate card? Recommended: yes,
   it is a translation task with no code in it.
