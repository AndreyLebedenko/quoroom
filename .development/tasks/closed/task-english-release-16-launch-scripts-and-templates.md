# Task english-release-16: Launch scripts and configuration templates

**Status:** Completed.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-02 (the `language` key).
**Estimate:** 3 hours.

## Summary

The scripts a person runs every day (`start.ps1`, `start.sh`, `stop.ps1`,
`stop.sh`) print their messages in the room language, and the configuration
templates a stranger copies (`docker/.env.example`,
`docker/continuwuity/continuwuity.toml.example`, `docker/caddy/Caddyfile`,
`docker/docker-compose.yml`) carry English comments.

## Why

These are the first files a new user meets after the installer. `start.ps1` and
`start.sh` print their progress and refusals ("Docker is not found", "no
config"), about 70 Cyrillic lines between the four, and the templates explain
every setting in Russian comments.

## Context you need

- The four scripts: the user-visible `echo` / `Say` lines and the
  comment-based help of the PowerShell ones (`.SYNOPSIS`-style text that
  `Get-Help` prints).
- `bridge/config.yaml`'s `language` key (task 02): the scripts read it with a
  plain line match, so they work before the broker exists.
- The wrappers `install.ps1` and `install.sh` already show the pattern: two
  message tables, `--lang` scanned from the arguments, English default.
- The templates' comments describe settings; the installer copies the files and
  must keep copying them (`installer/server.py` renders the toml and the env
  file from these examples), so a comment change must not break its parsing.

## Design to settle (AGENTS.md 0.4)

1. **Where the scripts learn the language.** Recommended: `--lang` if given,
   otherwise `language:` from `bridge/config.yaml` if the file exists, otherwise
   English. State what the scripts do for a malformed value (English).

## Boundary

- The four scripts, the four template files, tests that drive the scripts
  (extend `bridge/tests/test_entry_points.py` or a sibling in the same style),
  `docs/INSTALL.md` pointer.
- `.gitignore`, `.gitattributes`, `bridge/requirements.txt` comments are not in
  scope (contributor-facing; listed as non-gating in the story).

## Requirements

- Russian messages are what the scripts print now, character for character; the
  English counterparts follow AGENTS.md rule 9.
- Exit codes and behaviour unchanged.
- Template comments become English in the example files; the Russian wording is
  dropped (the Russian explanation lives in `docs/INSTALL.md`, which stays).
- The server installer's tests still read the templates unchanged in meaning.

## Tests

- The scripts under `--lang en`, `--lang ru`, and a config with each value, in
  the existing fake-PATH style; no Cyrillic in the English runs.
- A parse test that the installer still extracts the same keys from each
  template.

## Acceptance criteria

- [ ] No Cyrillic in the scripts' English output, nor in the English templates.
- [ ] The `ru` output is unchanged.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
