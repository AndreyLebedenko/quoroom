# Task client-kit-02: Kit sources in the package

**Status:** Not started.
**Story:** `.development/tasks/story-client-kit.md`
**Depends on:** task 01.

## Summary

Move the files each CLI loads into package data, and make the skills call
`agentschat` from PATH instead of `bridge\agentschat.cmd` from the Quoroom
root.

## Context you need

- Current locations:
  - `.claude/skills/chatlogin/SKILL.md`
  - `.opencode/skills/chatlogin/SKILL.md`
  - `.opencode/command/chatlogin.md`
  - `.opencode/plugins/agentschat.js`
  - `.opencode/plugins/agentschat.test.mjs` (node test of the plugin)
- `.opencode/plugins/graphify.js` and `.opencode/opencode.json` are NOT ours;
  leave them.
- The plugin recognises a login by `/agentschat/i` plus `login` in the
  command text (`agentschat.js`, ~line 75). A bare `agentschat login ...`
  matches.
- The skills are Russian runtime text. Normal Russian typography applies;
  do not "fix" it (AGENTS.md, Core 9).

## Boundary

- Moves (`git mv`) and skill/command/test text only. No change to plugin
  logic, client.py or the broker.
- No installer yet (task 03). No docs outside the moved files (task 04).

## Requirements

- New layout, mirroring the target directories of each CLI:
  - `bridge/sessionchat/kit/claude/skills/chatlogin/SKILL.md`
  - `bridge/sessionchat/kit/opencode/skills/chatlogin/SKILL.md`
  - `bridge/sessionchat/kit/opencode/command/chatlogin.md`
  - `bridge/sessionchat/kit/opencode/plugins/agentschat.js`
- The plugin test moves OUT of the kit, to `bridge/tests/plugin/`
  (it must never be installed into an OpenCode plugins directory, where
  OpenCode would load it). Its import path is updated; its sample login
  command becomes `agentschat login ...`. Add one case proving a path-
  qualified call (`bridge\agentschat.cmd login ...`) still binds, since old
  sessions may still use it.
- Skills:
  - every `bridge\agentschat.cmd` becomes `agentschat`;
  - the paragraphs "Все команды вызываются из корня проекта Quoroom" and the
    macOS/Linux launcher note are replaced by: `agentschat` is on PATH; if
    the command is not found, the client kit is not installed — say so to the
    human and stop, do not look for the Quoroom repository;
  - the Claude skill's section «Где это лежит» is rewritten: the skill is
    installed per user by `agentschat install` and is visible in every
    project;
  - the OpenCode skill's reference to `.opencode/plugins/agentschat.js`
    becomes a reference to the Quoroom plugin installed in OpenCode's plugin
    directory;
  - every other rule and warning stays, wording adapted only where a path
    changed.
- Keep functional agreement between the two skills in the shared parts
  (`login`, `say`, `ask`, `status`, boundaries).

## Acceptance criteria

- [ ] The four kit files exist at the new paths; the old paths are gone.
- [ ] `node --test bridge/tests/plugin/agentschat.test.mjs` passes, including
      the new path-qualified case.
- [ ] A unittest asserts no file under `sessionchat/kit/` mentions
      `bridge\agentschat` or `bridge/agentschat` or `.opencode/plugins`.
- [ ] A unittest asserts each kit file is included in the built package data
      (e.g. via `importlib.resources.files("sessionchat") / "kit"`).
- [ ] Full suite green; ruff clean.
