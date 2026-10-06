# Task english-release-22: The participant installer teaches the client the room language

**Status:** Planned.
**Story:** story-english-release.md (shared rules apply).
**Depends on:** tasks english-release-07 (client language source), 11 (kit install) and 12 (machine contract).
**Blocks:** closing task english-release-20 (the Russian run expects this behaviour).
**Estimate:** 1-2 hours.

## Summary

After the participant installer has confirmed that the broker answers, it runs
`agentschat status` once. The client learns the room language from the answer
and stores it in `~/.agentschat/language`, exactly as it does on any broker
answer. From then on everything the client says by itself is in the room
language, before the person has run a single command of their own.

## Why

Owner decision (2026-10-06) on the open item of task 20. The client learns the
room language only from a broker answer, and the installer probes `/status`
without the client. So on a participant machine of a Russian room, `agentschat
--help` and a first failure (the broker unreachable at the first command) are in
English until the first successful `login`. Before the story the client always
spoke Russian, so "`ru` prints what it printed before" is not met in that
window.

Chosen over "`agentschat install --lang` writes the value": the source of the
value is the broker, not a flag the person may have got wrong. The fallback to
English when no broker has ever answered stays; it is the documented default.
The kit language remains the installer's `--lang` (unchanged).

## Context you need

- `bridge/sessionchat/installer/participant.py`: `participant_role` (the ordered
  `install` steps), `BrokerStep` (`check` is the `/status` probe, `apply` only
  refuses), `KitInstallStep.apply` (how the installer runs the client:
  `run.boundaries.run([agentchat(run), ...])`, reading the machine contract, not
  the prose), `broker_url`, `env_lines`.
- `bridge/sessionchat/client.py`: `do_status` (`status_answer` learns the
  language), `base()` (the client reads the broker address from `AGENTSCHAT_URL`
  and the default otherwise), the `AGENTSCHAT-RESULT` line.
- `bridge/sessionchat/client_language.py`: `remember`, `RoomLanguage.learn`.
- `bridge/sessionchat/installer/boundaries.py`: `run`, the environment and the
  home directory the installer uses (tests redirect them).
- The installer's catalogues (`installer_messages` en/ru) and how the existing
  steps name themselves in the output.
- `docs/INSTALL.en.md` section "Room language", and the removal and purge
  contract of the participant role (ownership record).

## Boundary

- `participant.py` (a new step after `BrokerStep` in `install`; the `both` role
  gets it through the participant role), its catalogue keys in both languages,
  tests, and the documents that state the old behaviour: `CHANGELOG.md` (the
  "Added" line about `~/.agentschat/language` and the upgrade note that says
  `install` does not write it), `docs/INSTALL.en.md` and `docs/INSTALL.md`
  (section "Room language" / its Russian counterpart), and the handoff in
  `docs/VERIFICATION.md` (step R1 and the item about the client language in
  "Выведено из кода"; the handoff is not a recorded run, so it may be edited, and
  any recorded result stays untouched).
- Not in scope: the broker, the client commands, the precedence rules, the kit
  language, `uninstall`, what purge removes.

## Requirements

- The step runs the client with the same broker address the installer used
  (`--broker-url`, passed as `AGENTSCHAT_URL` in the child's environment) and the
  same home as the installer, so the file is written where the person's later
  commands will read it.
- The installer decides by the machine contract (the `AGENTSCHAT-RESULT` line of
  `status`), never by the sentences `status` prints.
- Idempotent: the step is DONE when `~/.agentschat/language` already holds a valid
  language (any client command refreshes it later); TODO otherwise. Re-running the
  installer changes nothing in that case.
- A failure of this step (the child cannot be run, the result is not ok) does not
  fail the install: the broker was confirmed one step earlier, and the cost of the
  miss is only the old behaviour. The installer's final report states that the
  language was not learned and what the person gets (English until the first
  broker answer). If the installer has no channel for such a note, stop and ask
  (AGENTS.md 0.1).
- The installer's own output names the step in the same style as the others, in
  both languages, with identical key and placeholder sets (task 01 rules).
- Locality contract unchanged: the child sends nothing but `GET /status`, and no
  token is read or printed.

## Stop conditions specific to this task

- If the participant removal or purge contract says the installer removes
  everything it created and the new file is therefore owed a removal step, stop
  and explain (AGENTS.md 0.3): that changes what purge does and is the owner's
  decision. Today purge removes only token files and leaves `~/.agentschat`.
- If `boundaries.run` cannot carry an environment for one child process, stop and
  explain rather than changing the process environment of the installer.

## Tests

- With a fake broker answering `/status` with `language: ru` on an empty home:
  after the install the file holds `ru`; with `en`, `en`.
- A second run with the file present does not run the child.
- `--broker-url` other than the default reaches the child as `AGENTSCHAT_URL`.
- The child fails or returns a not-ok result: the install still succeeds and the
  report says the language was not learned.
- The step's output lines exist in both languages and the catalogue contract test
  passes.
- The home directory is redirected in every test; tests never touch the real home.
- List every edit to an existing test in the report (step lists in existing
  participant tests are expected to change).

## Acceptance criteria

- [ ] After a participant install against a broker of a `ru` room, on a clean
      home, `agentschat --help` and a failure before any other broker contact are
      Russian.
- [ ] The install does not depend on this step succeeding.
- [ ] CHANGELOG, INSTALL guides and the VERIFICATION handoff no longer say that
      the client language appears only after the first broker answer; R1 expects
      Russian from the start.
- [ ] Full suite, `node --test`, `ruff check`, `ruff format --check` green
      (sequentially).
- [ ] Report `.development/reports/task-english-release-22-installer-teaches-client-language.md`
      lists the keys added, the tests added, each document line changed, and every
      edit to an existing test.
