# Task client-kit-04: Docs and manual handoff

**Status:** Completed (2026-09-24); manual handoff prepared, live run pending.
**Story:** `.development/tasks/story-client-kit.md`
**Depends on:** task 03.

## Summary

Make every document describe the shipped layout, and prepare the live check
the human runs in a foreign repository.

## Requirements

- `docs/INSTALL.md`: a step «Подключить чат в любом репозитории»:
  `uv tool install --editable <Quoroom>\bridge`, then `agentschat install`,
  restart sessions; updating = `git pull` + `agentschat install`; removal =
  `agentschat uninstall` + `uv tool uninstall quoroom`. Fallback without uv:
  `pipx install --editable`. Replace the old «скилл в `.claude/skills/`»
  passage and `bridge\agentschat.cmd status` with `agentschat status`.
- `bridge/config.example.yaml` (~line 51) names `.opencode/plugins/agentschat.js`.
- `README.md`: structure section and wherever `.claude/`, `.opencode/` are
  named as the skills' home.
- `docs/SESSION_BRIDGE.md`: a section on the decision — kit installed per
  user, why (per-machine dependencies, one contract in one version), who runs
  the installer and when, what breaks without re-running it after an update
  (installed skills describe the old CLI). Update the passages naming the old
  skill and plugin paths and the `node --test` command.
- `AGENTS.md`: Testing 2 (new plugin test path), Tooling 4 (skill locations
  are `bridge/sessionchat/kit/...`; agreement is functional, not byte-exact).
- `.development/tasks/task-v1.0.0-07-clients-and-docs.md` and the story
  v1.0.0 card: new paths; replace "byte-identical" with functional agreement.
- Manual handoff text in the task report (not in VERIFICATION.md until run):
  install, open Claude Code and OpenCode in a repository with no Quoroom
  files, `/chatlogin`, exchange messages both ways, `agentschat uninstall`
  and confirm both CLIs no longer offer the skill.

## Boundary

Documentation only. `legacy/` and closed task cards untouched.

## Acceptance criteria

- [ ] `rg` finds no reference to the old skill, command or plugin paths
      outside `legacy/`, closed cards and historical live-check entries
      (historical entries keep describing what was true then).
- [ ] Manual handoff prepared.
