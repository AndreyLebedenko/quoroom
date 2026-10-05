# Task install-doc-english: docs/INSTALL.md in English

**Status:** Planned.
**Depends on:** task installer-bilingual (the English installer output that the
document describes).

## Summary

An English main document for installation, translated from the Russian
`docs/INSTALL.md`. No code. The Russian document stays and the two are kept in
step.

## Why

`README.md` is English and the main one, and it links to `docs/INSTALL.md` for
everything past the first command. A reader who follows that link lands in
Russian. Task installer-bilingual makes the installer itself English by
default; the document that describes it should follow.

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
- The document states which parts of the installer's output are still Russian
  at the time of writing (the client block, if task client-bilingual has not
  landed).

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
