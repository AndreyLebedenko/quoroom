# Task local-installers-04: Disposable Linux environment

**Status:** Planned.
**Story:** `.development/tasks/story-local-installers.md`
**Depends on:** task 03.

## Summary

A disposable Ubuntu 24.04 environment with its own Docker engine
(`docker:dind`), in which `install.sh` runs for real. Agents use it for the
functional Linux flows of tasks 05-07; the human uses it for the live Linux
scenario.

## Context you need

- Story, gate item 1 (Linux): why the host's Docker Desktop engine is
  forbidden for the Linux server role, and the Ubuntu prerequisite procedure.
- `docker/docker-compose.yml`: fixed `container_name` values, port 443.
- `docker/element/config.json` and the Caddyfile: the stack serves only
  `agentschat.local` on 443.
- `.gitignore`: `bridge/live-checks/` is ignored, so this task does not use it.

## Boundary

- A new tracked directory `tools/linux-container/` with the compose file,
  runner, and a README. Nothing here joins the `unittest` suite or CI.
- No change to the repository's own Docker stack.

## Requirements

- Two containers: a plain `ubuntu:24.04` test machine and a privileged
  `docker:dind` engine. The test machine runs with
  `network_mode: "service:<dind>"`, so the stack the installer starts inside
  dind is reachable on the test machine's `127.0.0.1` and the server name's
  loopback check of task 06 is meaningful. `DOCKER_HOST` points at the dind
  engine; the host's Docker socket is never mounted.
- The repository is copied into the test machine, never bind-mounted: the
  server role writes configuration into its repository, and a bind mount
  would write into the host's checkout. Copy exactly the files listed by
  `git ls-files -co --exclude-standard` (tracked plus untracked-not-ignored),
  so uncommitted task code is tested and ignored secrets (`config.yaml`,
  `continuwuity.toml`, `docker/.env`, certificates, `bridge/state/`) are
  never copied. The copy lives under a path with spaces and Cyrillic.
- The test machine starts from plain `ubuntu:24.04` and gets its
  prerequisites by running the story's Ubuntu prerequisite procedure, so the
  procedure itself is exercised.
- Host port mapping is declared on the dind service. Default: none. For the
  live scenario, the runner has an option to publish 443 to the host's 443,
  and refuses it while anything already listens on the host's 443 (the
  Windows stack). See the story's live Linux access path.
- The runner brings the environment up, runs a named scenario, and tears it
  down including volumes. Teardown also works after a failed run.
- The human can open a shell in the test machine to install and log in to
  agent CLIs for the live scenario.
- A helper for the functional flows creates the room through the Matrix
  client-server API as the human account and invites the bots, standing in
  for the human's Element step of task 06. It runs only inside this
  environment and is not part of the installer.

## Acceptance criteria

- [ ] The runner brings the environment up, runs `install.sh --help` inside
      the test machine, and tears down cleanly, also after a failure.
- [ ] Verified while running: the host's Windows stack containers and
      volumes are untouched (`docker ps`, `docker volume ls` before/after).
- [ ] Verified: an ignored file present in the host checkout is absent in
      the test machine's copy; an uncommitted tracked change is present.
- [ ] `tools/linux-container/README.md` (Russian) states how to run it, how
      to open a shell, and how to publish 443 for the live scenario.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green.
