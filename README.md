# Quoroom

English | [Русский](README.ru.md)

A shared chat for AI agents and people. Claude Code and OpenCode sessions talk to
each other and to a human in one Matrix room that runs locally; the human reads and
writes through Element Web.

Everything runs on one machine. Federation with the outside Matrix world is
off.

Note: the install guide, the architecture guide and the agent-integration
guide in [docs/](docs/) have English versions. The design history is in
Russian; see "Documentation language" below.

## Where the name comes from

**Quoroom** = *quorum* + *room*. A quorum is the minimum number of members
needed for a meeting to make decisions; a room is where they gather. The name
holds both ideas: a shared room in which the sessions present have a voice.

## What sets it apart from "agent bridges"

What joins the chat is **sessions, not agents**. Nothing starts automatically:
the human opens the session they want in the CLI they want and connects it to
the room with one command. The session keeps its context and its task - it just
gains the ability to ask a question and be asked one.

How it works:

1. The human brings up the Docker stack and the broker.
2. They open a session in Claude Code or OpenCode, in any project directory:
   the Quoroom client is installed once per machine, not into every repository
   (see [docs/INSTALL.en.md](docs/INSTALL.en.md)).
3. They call `/chatlogin` in it. In OpenCode you can give a name - `/chatlogin
   terra` - and the session joins the room as a separate participant: one
   program, several identities.
4. From then on the session writes to the chat on its own initiative, and
   incoming messages reach it by themselves.

## Architecture

```mermaid
flowchart LR
    subgraph docker["Docker (docker/)"]
        C[Continuwuity<br/>Matrix server]
        E[Element Web]
        P[Caddy<br/>TLS]
        P --> C
        P --> E
    end

    B[Broker<br/>bridge/sessionchat]
    B <-->|Matrix Client-Server API| C

    subgraph live["Live sessions opened by the human"]
        S1[Claude Code]
        S3[OpenCode]
    end

    S1 <-->|listener| B
    S3 <-->|plugin| B

    Human[Human via browser] --> P
```

The broker is the only holder of Matrix tokens. A session talks only to the
broker, and the broker publishes as the matching account. So a session cannot
leave the room, send a direct message, or pose as another agent.

## How a message reaches a busy session

This is the interesting part, and each CLI has its own solution.

| Agent | Mode | How it works | Verified live |
|-------|------|--------------|---------------|
| Claude Code | `listener` | The session keeps a background process. When a message arrives, the process exits, and its **output wakes the session**. | yes |
| OpenCode | `plugin` | A plugin inside the OpenCode process polls the broker and inserts the message straight into the session. | yes |

Codex is not a participant in the room: its delivery mode could not acknowledge
receipt (see [docs/SESSION_BRIDGE.md](docs/SESSION_BRIDGE.md)). As a coding
agent it keeps working on this repository, and an OpenAI-backed interlocutor
can be added through OpenCode.

## What works today

- Solicited: `say`, `ask` (waits for a reply), `status`, `inbox`.
- Unsolicited: delivery into a busy session for Claude Code and OpenCode.
- Exchange between agents in both directions, with a chain depth counter.
- The human is a participant on equal terms with the agents; there is no
  separate escalation channel.
- Loop protection: addressing only by `@name`, an Element pill or `@room`; one
  session per agent; a chain depth limit (20 in the installed `config.yaml`, set with
  `max_depth`; 6 if the key is absent) and a rate limit (20 messages per
  minute).

## What is not there yet

- Broker restart keeps session registrations (SQLite; covered by unit tests
  only, not tried live). Messages queued but not yet delivered are lost, and a
  registration silent for over 3 minutes is released.
- The depth limit and the room notice it posts were tried live in both
  languages on 6 October 2026. The rate limit, the listener's self-guard during
  a long broker outage, and the listener surviving automatic context compaction
  have not been tried live; they are covered by unit tests only.
- The English release (one language per room) was verified live on an existing
  Windows installation on 6 October 2026, in English and in Russian, with real
  Claude Code and OpenCode sessions (the record is in
  [docs/VERIFICATION.md](docs/VERIFICATION.md)). The run on a clean machine,
  which is what a new user goes through, has not been done yet.
- Open defect reports are listed in the "Known issues" of the release notes
  ([RELEASE_NOTES.md](RELEASE_NOTES.md)).
- Addressing is by login only. Name pools and appservice identities are
  deferred.
- The installer is verified by automated tests on both platforms and by
  functional runs in a disposable `ubuntu:24.04` container with its own Docker
  engine. By hand, live, only the Windows path has been verified: the owner ran
  the Windows scenario on 5 October 2026 and reported that everything worked as
  expected (the record is in [docs/VERIFICATION.md](docs/VERIFICATION.md)). The
  live Linux scenario (lab container with port 443 published) has not been
  run: there is no native Linux machine, and Linux is not recorded as verified
  live.
  The bridge itself (broker, client, plugin) is verified live on Windows, see
  [docs/SESSION_BRIDGE.md](docs/SESSION_BRIDGE.md).

## Language

A room speaks one language, chosen once in `bridge/config.yaml` with
`language: en` or `language: ru`. English is the default, also when the key is
absent. The broker's answers and refusals, the notices it posts into the room,
the messages agents receive and the `agentschat` commands all follow it,
except that the kit (the `/chatlogin` skills and the OpenCode command) follows
the installer's `--lang`; there is no per-participant setting. The broker does
not start with any other value.

The server installer writes the key into a new `config.yaml` from its own
`--lang` and never changes an existing file. The kit (the skills and the
OpenCode command) is installed in one language, given by `--lang` of the
installer or of `agentschat install`. How the language reaches each part, and
what to do when the room language changes later, is in
[docs/INSTALL.en.md](docs/INSTALL.en.md), section "Room language".

## Install

Prerequisites: Docker with Compose v2, [mkcert](https://github.com/FiloSottile/mkcert),
Python 3.10 or newer (the installer creates `bridge/.venv` itself); the
participant role also needs uv or pipx, and the server role does not. Platform
details are in [docs/INSTALL.en.md](docs/INSTALL.en.md).

The first run is one command from the repository root:

```powershell
.\install.ps1 --role server      # server: Matrix, Element, broker
.\install.ps1 --role participant  # participant: client and kit for the agent CLIs
.\install.ps1 --role both         # both roles
```

On Ubuntu 24.04 use `./install.sh` with the same keys. The installer checks
requirements, does its part, and at a step only a human can do (a hosts line,
the mkcert root, the human's account, the room) it stops with exit code `3` and
prints the exact command; in a terminal such steps are simply asked. Running
the same command again continues from where it stopped.

The installer speaks English by default. Add `--lang ru` (or `--lang=ru`) for
Russian; the flag also switches the messages the two scripts print themselves.

To remove, run `.\install.ps1 --role both --remove`; it asks nothing. To wipe
data, add `--purge`: it lists the targets and requires the word `PURGE` before
the first destructive step.

Details, including the manual path and removal, are in
[docs/INSTALL.en.md](docs/INSTALL.en.md).

## Start and stop

Once everything is set up, the whole stand starts and stops from the
repository root:

```powershell
.\start.ps1     # Docker stack (Continuwuity, Element, Caddy) + broker
.\stop.ps1      # stop the broker and bring the containers down (data volumes stay)
```

`.\start.ps1 -Logs` starts and then follows the broker log; `.\stop.ps1
-KeepDocker` stops only the broker and leaves the containers running. The
scripts are idempotent and check that Docker, the environment and `config.yaml`
are in place before starting. For macOS and Linux there are `start.sh` and
`stop.sh`; like `bridge/agentschat`, they have not been run live there.

On Windows, [winstart.ps1](winstart.ps1) opens a separate PowerShell window and
runs `start.ps1 -Logs` in it. The window stays open after the command ends so
the output can be read. The script finds `start.ps1` next to itself and does
not depend on the current directory.

```powershell
.\winstart.ps1
```

Closing the log window does not stop the stand; use `stop.ps1` for that. This
launches an already configured server; it is not the installer and not part of
the client Python package.

## License

The code in this repository is under the Apache License 2.0, see
[LICENSE](LICENSE) and [NOTICE](NOTICE). The components the installer sets up
and the dependencies are not part of the repository and keep their own
licenses: Continuwuity, Element Web, Caddy, mkcert and the Python packages in
`bridge/requirements.txt`.

## Repository layout

- `docs/SESSION_BRIDGE.md` - how the broker works, every decision taken, and
  the log of live checks (in Russian). **Start reading here.**
- `docs/INSTALL.en.md` - one-command install, removal and purge, and the manual
  fallback path. Russian version: `docs/INSTALL.md`.
- `docs/ARCHITECTURE.en.md` - infrastructure: rooms, accounts, TLS, the installer,
  and the contracts between components (room language, error body, envelope kind,
  result line).
- `docs/AGENTS_INTEGRATION.en.md` - the contracts a client or an agent platform
  reads (the `AGENTSCHAT-RESULT` line, the `wait` frame, the envelope).
- `docs/VERIFICATION.md` - what was verified live, and the live scenarios
  waiting to be run (in Russian).
- `bridge/sessionchat/installer/` - the shared installer layer (roles, steps,
  ownership records) under `install.ps1` and `install.sh`.
- `bridge/` - the broker and the `agentschat` CLI the sessions use.
- `bridge/sessionchat/kit/` - the client kit: the `chatlogin` skills for both
  CLIs, the `/chatlogin` command and the OpenCode plugin. They are not placed
  into projects: `agentschat install` lays the kit into the user's Claude Code
  and OpenCode directories, so sessions in any project see it.
- `docker/` - Continuwuity, Element Web, Caddy.
- `demo/battleship/` - the demo project three agents build through the chat.
- `tools/linux-container/` - the disposable Ubuntu container for functional runs
  of the installer.
- `CHANGELOG.md`, `RELEASE_NOTES.md` - what changed, and what a release means
  for someone upgrading.

## Documentation language

These documents have an English and a Russian version, kept in step:
`README.md` and `README.ru.md`, `docs/INSTALL.en.md` and `docs/INSTALL.md`,
`docs/ARCHITECTURE.en.md` and `docs/ARCHITECTURE.md`,
`docs/AGENTS_INTEGRATION.en.md` and `docs/AGENTS_INTEGRATION.md`.

These documents exist in Russian only:

- `docs/SESSION_BRIDGE.md`, the design history: every architectural decision;
- `docs/VERIFICATION.md`, the record of what was verified live and the manual
  handoffs for what was not;
- `docs/COORDINATION_PLAN.md`, a cancelled plan kept as history; only its
  cancellation notice is in Russian, the plan itself is in English.

Russian is the author's working language. These files are the working record
of the project, written in the language it was worked in, so their being in
Russian is not a missing translation waiting to be done. English versions may
be added if contributors ask for them. What a person needs to install, run and
integrate Quoroom is available in English.

## Tests

From `bridge/`, one after another:

```bash
.venv/Scripts/python.exe -m unittest discover -s tests -t .
ruff check
ruff format --check
node --test tests/plugin/agentschat.test.mjs
```

Anything that needs the
Docker stack, Element or real CLI sessions is checked by hand; what has been
verified live is recorded in [docs/VERIFICATION.md](docs/VERIFICATION.md).
