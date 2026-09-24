# Story: Client kit for any repository

**Status:** In progress (branch `feat/client-kit`).

## User-facing goal

A session opened in **any** repository on this machine can join the Quoroom
room with `/chatlogin`, in Claude Code and in OpenCode, without a single
Quoroom file in that repository. The human installs the client once per
machine and re-runs one command after updating Quoroom.

## Why per-user, not per-repository

Everything the client depends on is already per machine: one broker on
`127.0.0.1:8770`, tokens in `~/.agentschat/`, the plugin reads
`AGENTSCHAT_URL` and the home directory. The only repository-bound piece is
the skills calling `bridge\agentschat.cmd` "from the Quoroom root". Copying
files into each repository would bind a per-machine mechanism to
repositories, and the copies would drift.

The skills and the CLI are two sides of one contract. They ship in one
package and one version, so a skill never describes commands the installed
CLI does not have.

## Givens (from the human, 2026-09-24)

- OpenCode reads skills only from `.opencode/` and its own config directory,
  never from `.claude/`. Both skills keep the name `chatlogin`.
- The two skill copies must agree functionally, not byte for byte. What a
  user later edits in an installed copy is their own responsibility.
- Removing the project-level copies from the Quoroom repository is accepted:
  Quoroom sessions use the installed kit like any other repository.

## Observed on this machine (not a live check)

`~/.claude/skills/`, `~/.config/opencode/skills/`,
`~/.config/opencode/plugins/`, `~/.config/opencode/command/` exist and hold
other globally installed tools (graphify is installed exactly this way:
`graphify.exe` in `~/.local/bin` plus global skills). Whether OpenCode loads a
plugin, skill and command from these global directories is **not verified**
for our kit; that is the manual handoff of task 04.

## Boundaries

- Client side only. The broker, Docker stack and `config.yaml` stay in the
  Quoroom repository and are not packaged.
- No change to the client-broker contract. Story v1.0.0 task 07 changes it
  later and edits the kit in its new location.
- The installer writes only under the target directories it is given and
  never touches a file it did not install, unless told to.
- Nothing in the automated suite may write to the real home directory.

## Task sequence

1. `task-client-kit-01-package.md` — installable `quoroom` package with the
   `agentschat` entry point and client-only base dependencies.
2. `task-client-kit-02-kit-sources.md` — move skills, command and plugin into
   package data; skills call `agentschat` from PATH.
3. `task-client-kit-03-installer.md` — `agentschat install` / `uninstall`.
4. `task-client-kit-04-docs.md` — README, INSTALL, SESSION_BRIDGE, AGENTS.md,
   task-07 card; manual handoff prepared.

## Acceptance criteria

- [ ] `uv tool install --editable ./bridge` puts `agentschat` on PATH with
      `requests` as its only runtime dependency.
- [ ] `agentschat install` lays the kit into the user directories of both
      CLIs; `agentschat uninstall` removes exactly what it laid.
- [ ] No Quoroom repository path remains in any installed file.
- [ ] Full suite, `node --test` and ruff are green.
- [ ] Manual handoff (a foreign repository, both CLIs) is prepared and its
      result recorded in `docs/VERIFICATION.md` once the human runs it.
