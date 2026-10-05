# Task english-release-18: docs/INSTALL.md in English

**Status:** Completed.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-11 (the English output of the whole
participant install, client lines included).
**Estimate:** 3 hours. At 616 lines the Russian document is near the limit; if
the translation is not done in three hours, split at the middle section
boundary and say so in the report.

## Summary

An English main document for installation, translated from the Russian
`docs/INSTALL.md`. No code. The Russian document stays and the two are kept in
step.

## Why

`README.md` is English and the main one, and it links to `docs/INSTALL.md` for
everything past the first command. A reader who follows that link lands in
Russian. The installer and, after tasks 01-17, the whole runtime path are English by
default; the document that describes them should follow.

## Context you need

- AGENTS.md: rule 9 (ASCII punctuation in English text), the communication
  protocol (`README.md` is English and main; `README.ru.md`, `docs/` and the
  skills are Russian and read at runtime), rule 4 on documentation references
  (stable filename identity), rule 2 on keeping the two READMEs in step.
- `docs/INSTALL.md` as it stands after task installer-bilingual: it documents
  `--lang en|ru` and the accepted limitation about the Russian block printed by
  `agentschat install` and `agentschat login`.
- The installer's English strings (`bridge/sessionchat/installer/messages/en.json`):
  a quoted installer line in the translation must be the English line the
  installer prints, not a retranslation of the Russian one.
- Open question 1 of this card decides the file layout; the repository's
  convention for English main documents is the one in the READMEs.

## Boundary

- The new English document, the links that point to it (`README.md`,
  `README.ru.md`), and `docs/INSTALL.md` only to add a pointer to the English
  document and keep the two in step.
- Out of scope: any change to code, scripts or catalogues; translating the
  other documents in `docs/`; the manual-install section beyond a faithful
  translation.

## Requirements

- Same structure and section numbering as the Russian document, so that a
  reference such as "section 1.4" means the same in both.
- ASCII punctuation, UTF-8, English commands and identifiers unchanged. Quoted
  installer output is the English text of the catalogue.
- Facts are translated, not re-verified and not rewritten: where the Russian
  document says something was or was not verified, the translation says the
  same, and nothing is strengthened.
- `README.md` links to the English document; `README.ru.md` keeps linking to
  the Russian one; each document names its counterpart.
- The document says that the room language is chosen once in
  `bridge/config.yaml` (`language: en|ru`), that the kit is installed in that
  language, and that changing it later means editing the key and re-running
  `agentschat install` (see tasks 02 and 13).
- The result line of `agentschat login` / `say` / `ask` (task 08) is not
  documented here; it belongs to the integration guide (task 19).

## Acceptance criteria

- [ ] Every section of the Russian document has an English counterpart with the
      same number and heading meaning.
- [ ] Every command in the English document is byte-identical to the Russian
      one, apart from comments.
- [ ] Quoted installer lines match `en.json`.
- [ ] No non-ASCII punctuation in the English document.
- [ ] Both READMEs link to the right document and to each other's counterpart.
- [ ] No code or script changed; the full suite is untouched.

## Open questions (answer before implementation)

1. File layout: `docs/INSTALL.md` becomes English and the Russian moves to
   `docs/INSTALL.ru.md`, or the English is added as `docs/INSTALL.en.md` and
   the Russian stays where it is. Moving the Russian file breaks the existing
   links in `docs/`, `README.ru.md` and the closed cards; adding a new file
   breaks none. Recommended: add the new file and leave the Russian in place
   until the whole of `docs/` has an owner for translation.

## Owner decision and notes (orchestrator, 2026-10-05)

- Open question 1 is answered: the English guide is a NEW file,
  `docs/INSTALL.en.md`; `docs/INSTALL.md` stays Russian. `ARCHITECTURE.en.md`
  (task 19) already links to `INSTALL.en.md`, and the README bullet for it sits
  next to the one task 19 edited: expect to merge that hunk.
- Task 11 note: the kit language follows the installer's `--lang`, not the room
  language (see the note in task 13). Say so in the participant section, with the
  fix (`agentschat install --lang <room language>`).
- Task 05 note: the broker's "ready" log line quoted in the Russian guide near
  section 5 is now English in every configuration; quote the English line in the
  English guide and fix the Russian guide in step.
