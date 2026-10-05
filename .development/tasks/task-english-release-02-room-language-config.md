# Task english-release-02: The room language in config.yaml

**Status:** Planned.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** task english-release-01.
**Estimate:** 3 hours.

## Summary

`bridge/config.yaml` gets a `language` key (`en` or `ru`, default `en`). The
broker reads and validates it at start and exposes it in its `/status` answer as
a machine-readable field. The server install writes it from the installer's own
`--lang`. `config.example.yaml` documents it.

## Why

One language per room is the owner's decision. Everything the broker says, and
everything clients and kits do to match it, has to start from one value with one
owner. A client must be able to read it over HTTP so that it is never
configured twice.

## Context you need

- `bridge/sessionchat/broker.py`: `Broker.__init__(cfg, ...)` reads the config;
  `handle_status`; `run()` / `main()`.
- `bridge/config.example.yaml`: its comments are Russian. They are documentation
  read by whoever copies the file, so they move to English with this task.
- `bridge/sessionchat/installer/server.py`: `ConfigStep` and `write_config`
  render `config.yaml` from the example.
- AGENTS.md locality contract: `config.yaml` is secret-bearing and gitignored;
  nothing here prints its contents.

## Boundary

- `broker.py` (config reading, `/status`), `config.example.yaml`,
  `installer/server.py` (ConfigStep writes `language`), tests, and the one line
  in `docs/INSTALL.md` that mentions the key (the English guide is task 18).
- No broker catalogue is used yet; task 03 starts that. This task only carries
  the value.

## Requirements

- `language` absent means `en`. A value other than `en` or `ru` stops the broker
  at start with a message that names the key and the allowed values. The message
  is English, because the language is not known yet; it is the one unconditional
  English operator message of the broker.
- `/status` answers with `"language": "<en|ru>"` next to what it returns now;
  the field is part of the documented broker contract.
- `ConfigStep` writes `language: <installer --lang>` into a new `config.yaml`
  and leaves the value of an existing file alone. A re-run never flips an
  existing room to another language.
- The ownership record and the idempotence of the server install are unchanged.

## Tests

- Broker: default, `en`, `ru`, an unknown value, a non-string value; `/status`
  reports the effective language.
- Installer: a fresh install writes the installer's language; an existing
  `config.yaml` keeps its own; both `--lang` values.
- Existing broker and installer tests unchanged.

## Acceptance criteria

- [ ] A broker started without the key reports `language: en`.
- [ ] A bad value is refused at start with an English message naming the key.
- [ ] `config.example.yaml` explains the key, in English, in the file.
- [ ] The server install honours an existing value and writes one otherwise.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
