# Task english-release-01: One catalogue loader for installer, broker and client

**Status:** Planned.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task installer-bilingual (completed).
**Estimate:** 2 hours.

## Summary

The catalogue loader and renderer live in
`bridge/sessionchat/installer/catalogue.py` and are tied to the installer's
`messages/` directory. Move the generic part to a module the broker and the
client can import without importing the installer, and keep the installer's
output byte-identical.

## Why

The client is installed on its own (`uv tool install`) and the broker runs on
the stand; neither may import `sessionchat.installer`. Three components need
the same mechanism - lookup, `str.format`, missing-key failure, parity tests -
and building it three times is how the three drift.

## Context you need

- `bridge/sessionchat/installer/catalogue.py`: `catalogue(lang)`, `has`, `text`,
  `step_label`, `LANGUAGES`, `DEFAULT_LANGUAGE`, loaded through
  `importlib.resources`, cached.
- `bridge/tests/test_installer_messages.py`: the parity, placeholder, ASCII and
  no-Cyrillic tests that every catalogue must satisfy.
- `bridge/pyproject.toml`: `[tool.setuptools.package-data]`.

## Design to settle (AGENTS.md 0.4)

State the choice and the reason in the report.

1. **Shape of the shared module.** Recommended: a small `Catalogue(package,
   directory)` object exposing `text(lang, key, **params)` and `has`;
   `LANGUAGES` and `DEFAULT_LANGUAGE` stay module constants in one place. The
   installer keeps `step_label` on top of it.
2. **Where it lives.** Recommended: `bridge/sessionchat/i18n.py`, with no imports
   from `installer/`, `broker.py` or `client.py`.
3. **Where each component's JSON lives.** Recommended: next to the component
   (`installer/messages/`, `broker_messages/`, `client_messages/`), each its own
   `package-data` entry; one catalogue per component, no merged file.

## Boundary

- `bridge/sessionchat/i18n.py` (new), `installer/catalogue.py` (becomes a thin
  user of it), `bridge/pyproject.toml` (package-data), tests.
- A reusable test helper (a mixin or functions) that asserts key parity,
  placeholder parity, ASCII-only and Cyrillic-free `en.json`, sorted keys, for
  any catalogue. The installer's existing catalogue tests call it; tasks 03-11
  use it for their catalogues.
- No new message and no change to any printed text.

## Requirements

- The installer's catalogue tests keep passing; the same assertions now run
  through the shared helper.
- A catalogue directory or a language file that does not exist fails loudly at
  load time, not at first use.
- The renderer still raises on an unknown key or a missing placeholder.
- Importing `sessionchat.i18n` does not import `sessionchat.installer`.

## Tests

- A test that the module imports cleanly with `sessionchat.installer` made
  unimportable.
- A fake catalogue directory exercising: key parity failure, placeholder
  mismatch failure, a Cyrillic value in `en.json`, an unsorted file.
- All existing installer tests unchanged.

## Acceptance criteria

- [ ] The installer prints exactly what it printed before (the whole installer
      suite passes unchanged).
- [ ] `i18n` has no dependency on `installer/`, `broker.py`, `client.py`.
- [ ] A catalogue test helper exists and the installer uses it.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
