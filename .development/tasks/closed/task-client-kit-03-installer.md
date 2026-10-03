# Task client-kit-03: Installer

**Status:** Completed (2026-09-24).
**Story:** `.development/tasks/story-client-kit.md`
**Depends on:** task 02.

## Summary

`agentschat install` lays the kit into the user directories of Claude Code
and OpenCode; `agentschat uninstall` takes back exactly what it laid.

## Context you need

- Kit layout from task 02: `sessionchat/kit/<cli>/...` mirrors the target
  directory of that CLI.
- Default targets: Claude Code `~/.claude`, OpenCode `~/.config/opencode`
  (same on Windows; both exist on the author's machine).
- The client already owns `~/.agentschat/` (tokens).
- AGENTS.md, Core 2 and 7: SRP; no explanatory comments.

## Boundary

- A new module (e.g. `sessionchat/kit.py`) owns the logic; `client.py` only
  wires the two subcommands. No other client change.
- Tests never touch the real home directory: every target is injectable.

## Requirements

- `agentschat install [--claude] [--opencode] [--claude-dir D]
  [--opencode-dir D] [--force]`. With neither `--claude` nor `--opencode`,
  both are installed.
- A manifest `~/.agentschat/kit.json` (location injectable) records, per
  installed file: absolute target path, sha256 of what was written, and target
  CLI. Recording the package version is not required.
- Install copies each kit file to `<target>/<relative path>`, creating
  directories. For an existing target file:
  - listed in the manifest -> overwritten (that is the update path);
  - not listed and identical content -> adopted into the manifest;
  - not listed and different -> refused, the file named, nothing written for
    any file; `--force` overwrites.
- `agentschat uninstall [--claude] [--opencode]` removes files listed in the
  manifest, then removes directories it leaves empty up to (not including)
  the target root, then updates the manifest. A listed file the user edited
  since install (hash mismatch) is still removed only with `--force`;
  otherwise it is named and kept.
- Install is idempotent: running it twice leaves the same files and manifest.
- Output: one line per file (installed / updated / unchanged / kept / removed),
  then a short Russian summary telling the human to restart open sessions.

## Acceptance criteria

- [ ] Each rule above has its own test against temporary directories.
- [ ] A test proves install then uninstall leaves the target tree exactly as
      before (including a pre-existing unrelated file in the same directory).
- [ ] A test proves a refused install writes nothing at all.
- [ ] Full suite green; ruff clean.

## Implementation notes

- Uninstall has no directory flags and the manifest stores no root, so files
  installed under a custom `--claude-dir` / `--opencode-dir` are removed by
  their absolute path, but emptied directories are pruned only under the
  default roots.
- A listed file edited by the user is overwritten by the next install (the
  update path). Per the story's givens, edits to installed copies are the
  user's responsibility; uninstall still keeps them without `--force`.
- Files dropped from a later kit are not cleaned by install; uninstall removes
  them.
