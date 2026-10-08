# Task: participant installer DSH step

Status: Completed
Story: story-dsh-participant.md
Branch: feat/dsh-participant

## Summary

The participant installer (`bridge/sessionchat/installer/participant.py`,
reached via `install.ps1 --role participant`) gains the DSH step:

- the skill goes to the DSH skills root (`<dshHome>/skills/chatlogin/`);
- the plugin package goes into the named profile: added as a dependency in
  the profile `package.json`, listed in `dsh.profile.bundles`, and inserted
  into the profile `cordis.patch.yml` (the patch layer, not `cordis.yml`).
  With `patchReload: live` the profile picks the plugin up without a restart.
- If the `dsh` CLI is not on PATH (this machine), the installer falls back to
  `pnpm add` plus manifest edits in the profile directory.

The broker config entry for the participant (name, user_id, access_token,
`delivery: plugin`) stays in `bridge/config.yaml` and is prepared by the
manual handoff, not by the installer.

## Boundary

- `bridge/sessionchat/installer/participant.py` and its tests
- `install.ps1` only if a new flag is required
- No changes to the broker, the client, or the profile contents of other
  machines.

## Acceptance criteria

- `unittest discover` from `bridge/` passes, including installer tests for
  the DSH step (skill placement, profile manifest edits, pnpm fallback).
- The manual handoff for a live install is written into
  `docs/VERIFICATION.md` (task 4).
