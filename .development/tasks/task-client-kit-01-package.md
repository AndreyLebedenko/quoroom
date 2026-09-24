# Task client-kit-01: Installable package

**Status:** Not started.
**Story:** `.development/tasks/story-client-kit.md`

## Summary

Turn `bridge/` into an installable Python package so `agentschat` can live on
PATH outside the Quoroom repository.

## Context you need

- `bridge/pyproject.toml` holds only ruff settings today.
- `bridge/requirements.txt`: matrix-nio, PyYAML, aiohttp (broker), requests
  (client).
- `bridge/sessionchat/client.py` has `main()`; it imports `requests` and
  `sessionchat.protocol` only. `protocol.py` is stdlib-only.
- Tests: `unittest`, from `bridge/`:
  `.venv/Scripts/python.exe -m unittest discover -s tests -t .`
- AGENTS.md, Core 7: no explanatory comments; a rule becomes a test.
  Exception (a): pinned versions may carry a "why" comment.

## Boundary

- `bridge/pyproject.toml` and a new test module. Do not touch client.py,
  broker.py, the skills, the plugin or docs.
- Keep `bridge/requirements.txt` and `requirements-dev.txt` as they are: the
  start scripts and INSTALL.md use them for the broker venv.
- Keep `bridge/agentschat` and `bridge/agentschat.cmd`.

## Requirements

- `[project]`: name `quoroom`, `requires-python = ">=3.10"`, a version,
  `dependencies = ["requests>=2.31.0"]`.
- `[project.optional-dependencies] broker = [matrix-nio, PyYAML, aiohttp]`
  with the same lower bounds as `requirements.txt`.
- `[project.scripts] agentschat = "sessionchat.client:main"`.
- setuptools build backend; package discovery limited to `sessionchat`
  (not `tests`); package data configured so that non-Python files under
  `sessionchat/kit/` ship once task 02 adds them.
- Existing ruff settings stay.

## Acceptance criteria

- [ ] A test asserts the `agentschat` script entry in `pyproject.toml`
      resolves to a callable (`tomllib`).
- [ ] A test asserts the base dependencies are exactly the client's needs:
      importing `sessionchat.client` in a fresh interpreter loads none of
      `nio`, `yaml`, `aiohttp`.
- [ ] A test asserts every broker dependency in `requirements.txt` appears in
      the `broker` extra, so the two lists cannot drift apart silently.
- [ ] `uv build` (or `pip wheel --no-deps`) produces a wheel containing
      `sessionchat/client.py` and no `tests/`; checked by hand, reported.
- [ ] Full suite green; `ruff check` and `ruff format --check` clean.
