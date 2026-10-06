# Task client-bilingual: English by default in the agentschat client

**Status:** Rejected. Superseded by story-english-release.md: the work is split
into tasks english-release-07 to 11 and 13, and the card's open questions are
settled there (one language per room, set in `config.yaml`; machine-readable
contracts between components).
**Depends on:** task installer-bilingual (the catalogue mechanism and the
`--lang` convention are reused, not redesigned).

## Summary

The messages that `agentschat install`, `agentschat uninstall` and
`agentschat login` print for a human exist in English and in Russian, from a
language-aware catalogue. English is the default and Russian is chosen
explicitly. The Russian block that today appears inside an English participant
install disappears.

## Why

Task installer-bilingual makes the installer English by default, but its
participant role calls `agentschat install` (and later `agentschat login`), and
those print Russian from the client and the kit. A participant install
therefore shows a Russian block in the middle of an English run. That gap was
accepted for the rc.2 release and recorded in `docs/INSTALL.md` and
`CHANGELOG.md`; this card gives it an owner.

## Context you need

- Task `.development/tasks/task-installer-bilingual.md`: the catalogue format
  (one JSON file per language, flat keys, `str.format` templates, loaded with
  `importlib.resources`), the language carrier, and the parity tests. Reuse the
  loader and the renderer; do not build a second mechanism.
- AGENTS.md: rule 9 (ASCII punctuation in English text; Russian is data and
  keeps normal typography), rule 7 (no comments), locality contract (no token
  in any message), 0.4 (stop when an architectural choice has trade-offs).
- Where the human-visible text lives, by Cyrillic-bearing line count:
  `bridge/sessionchat/client.py` ~99, `bridge/sessionchat/kit.py` ~18.
  The install and uninstall paths are `do_install`, `do_uninstall`,
  `kit.install_summary`, `kit.uninstall_summary`, `kit.restart_hint`,
  `Step.line` and `KitConflict`.
- The kit files themselves (`bridge/sessionchat/kit/**`: the `chatlogin`
  skills, the OpenCode command, the OpenCode plugin) are instructions read by
  agents, not output for a human, and some of them carry runtime strings the
  plugin sends to a session. They are a separate decision (see Open questions).

## Design to settle before coding (AGENTS.md 0.4)

State the choice and the reason in the task report.

1. **How the client learns the language.** A `--lang en|ru` flag on the
   subcommands the installer calls, passed through by the installer from its own
   `--lang`, versus a shared environment variable. The installer card rejected a
   variable ("one way to do it"); the default expectation is the flag, with the
   installer forwarding its own value to the client so one run speaks one
   language.
2. **Where the catalogue lives.** Reuse the installer's `messages/` loader from
   a shared location, or give the client its own resource directory with the
   same format. A client that imports from the installer package inverts the
   dependency (the client is installed on its own); prefer a small shared
   module over an import from `installer/`.
3. **Step identity.** `Step.line` and the manifest stay language-independent:
   a manifest written in one language is read in the other.

## Boundary

- `bridge/sessionchat/client.py`, `bridge/sessionchat/kit.py`, the catalogue
  files and loader for them, `bridge/pyproject.toml` (package-data only), the
  participant role of the installer (only to forward `--lang`), their tests,
  `docs/INSTALL.md`, `README.md`, `README.ru.md`, `CHANGELOG.md`.
- Out of scope: broker runtime strings, the contents of `bridge/sessionchat/kit/**`
  (see Open questions), `docs/` other than the install notes named above.

## Requirements

- Every string `agentschat install`, `uninstall` and `login` print for a human
  moves to the catalogue, with an English and a Russian text. English follows
  AGENTS.md rule 9; Russian is, character for character, what the client prints
  today.
- English is the default. `--lang ru` switches. An unknown value is a usage
  error with an English text and exit code 2, the same as in the installer.
- The installer's participant role forwards its own language to the client, so
  `.\install.ps1 --role participant` prints English only from the first line to
  the report, and `--lang ru` prints Russian only.
- The two catalogues have the same keys and the same placeholders per key; a
  missing key is a test failure, not a silent fallback.
- Exit codes, the manifest (`kit.json`), file targets and the `--force`
  semantics do not depend on the language.
- Rendering goes through the same scrubbing of secrets as the installer; no
  message contains a token.

## Tests

- Existing client and kit tests keep asserting the Russian text unchanged: they
  run in Russian. No existing expectation is edited.
- New: with no flag, `agentschat install`, `uninstall` and `login` print no
  Cyrillic at all, stdout and stderr both.
- New: catalogue parity (same keys, same placeholders; no Cyrillic in the
  English file; ASCII-only punctuation in the English file).
- New: a manifest written in one language is read and removed in the other.
- New: the installer's participant role, run in English, prints no Cyrillic
  from the first line to the report.

## Acceptance criteria

- [ ] A full participant install in English prints no Cyrillic.
- [ ] `--lang ru` on the installer prints what the installer and the client
      printed before this task, in Russian.
- [ ] No human-visible string in `client.py` and `kit.py` outside the
      catalogue (checked by a test that scans both files for Cyrillic).
- [ ] Catalogue parity tests pass; adding a key to one language alone fails the
      suite.
- [ ] The limitation about the Russian block is removed from `docs/INSTALL.md`
      and `CHANGELOG.md`.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green,
      run one after another from `bridge/`.
- [ ] The report lists the design choices and why.

## Open questions (answer before implementation)

1. The kit skills, the OpenCode command and the OpenCode plugin
   (`bridge/sessionchat/kit/**`) are in Russian. Are they translated in this
   card, kept Russian as agent-facing text, or installed per language? This
   changes the size of the card; recommended: keep them out and decide in a
   separate card once the human-facing output is done.
2. `agentschat login` and the other subcommands (`say`, `ask`, `wait`,
   `status`) also print Russian. Recommended: cover the whole client in this
   card, since the language flag has to exist on every subcommand anyway.
