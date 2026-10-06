# Story: English release - one language per room

**Status:** Planned.
**Blocks:** opening the repository to the public (owner decision: a public
release that is Russian-only works against the project).
**Depends on:** task installer-bilingual (completed): the installer already
speaks English by default and Russian with `--lang ru`.

## User-facing goal

A person who does not read Russian clones the repository, follows
`README.md` and `docs/INSTALL.md`, installs the stand and a participant, and
every sentence they or their agents are shown - installer, `agentschat`
commands, broker answers, room notices, the messages agents receive, the
`/chatlogin` skills - is in English. The owner of a room can choose Russian
instead, once, in `bridge/config.yaml`, and then the whole room speaks Russian
exactly as it does today.

## Decisions already made (owner, 2026-10-05)

1. **One language per room**, set in `bridge/config.yaml` (`language: en|ru`).
   No per-participant language. English is the default.
2. **Machine-readable exchange between components is required**, at every
   level, in addition to localisation and not instead of it. A component never
   decides what happened by reading another component's sentences.
3. **The repository is not opened to the public before the runtime path is
   English** (tasks 01-17 and the install guide, task 18). The remaining
   documents may lag if the README says so (task 20).

## The principle behind the tasks

Today four places treat a Russian sentence as an identifier:

- the installer reads the client's output to learn whether files were written
  (`kit.Action` values) and whether the install was refused (`KitConflict`
  text);
- the OpenCode plugin decides a session is logged in or out by looking for two
  Russian phrases in the CLI's output;
- the broker's status word (listening / processing / not listening) is both
  the state and its text, and the tests match the text;
- the envelope `kind` field carries a Russian word as data.

Localising these as they stand would freeze the dependency on prose in two
languages. So every task follows one rule:

> A message that crosses a component boundary carries a stable code and
> parameters. A sentence is rendered only by the component that faces a human
> or an agent, from the catalogue, in the room language. The code, not the
> sentence, is what the other side reads.

Logs (`broker.log`, the plugin log, tracebacks) are for the person debugging
and are English in every configuration; they are not catalogued.

## Shared rules (every task card in this story)

- AGENTS.md applies as written: rule 7 (no comments), rule 9 (ASCII
  punctuation in English text; normal Russian typography in Russian text),
  Testing protocol (`unittest`, `node --test`, `ruff check` then
  `ruff format --check`, one after another), locality contract (no token or
  secret in any message; `Secrets.scrub` where a scrubber exists), 0.x stop
  conditions, the standard task-card workflow (branch per task, stop for review
  before committing and merging).
- Catalogues use the format and loader from task 01: flat JSON keys,
  `str.format` templates with named placeholders (never `key` or `self`), one
  sentence per key, variants chosen in code, an `en.json` and a `ru.json` per
  component with identical key sets and identical placeholder sets, no Cyrillic
  and only printable ASCII in `en.json`. A missing key is a failing test, not a
  runtime fallback.
- Russian text is moved, not rewritten: `ru.json` holds, character for
  character, what the code printed before the task. Existing tests keep
  asserting that Russian text unchanged (they run with the room language `ru`);
  an expectation edited to make a test pass is a defect. A task may change a
  call or an import in an existing test when a signature changes, and its
  report lists each such edit.
- Machine-readable fields are language-independent: a record, a manifest, a
  state file or a code written under one language is read under the other.
- Every task ends with the full suite, `node --test`, `ruff check` and
  `ruff format --check` green, and a report that lists the keys added, the
  codes introduced and every edit to an existing test.
- Estimates are 2-3 hours of implementation plus review. A task that grows
  past that is split in its own card and the report says so (AGENTS.md 0.3).

## Boundaries

- Local-only contract unchanged: the broker is the only holder of Matrix
  tokens, nothing gets a new path to a token, Federation stays off.
- No change to the Matrix event format beyond what a task states; no change
  to the idempotency, queue or ack semantics of the v1.0.0 core.
- Out of scope for the whole story: translating source-code comments and
  docstrings (listed under "After the release"), contributor-only files such as
  `.gitignore`, `.gitattributes` and `bridge/requirements.txt` comments,
  `docs/SESSION_BRIDGE.md`,
  `docs/VERIFICATION.md`, `docs/COORDINATION_PLAN.md`, and any language other
  than `en` and `ru`.

## Task sequence

Phase A - foundation

1. `task-english-release-01-shared-catalogue.md` - the catalogue loader moves
   out of the installer so the broker and the client can use it.
2. `task-english-release-02-room-language-config.md` - `language` in
   `config.yaml`, validated by the broker, reported in `/status`, written by
   the server install.

Phase B - broker (it speaks in the room language)

3. `task-english-release-03-broker-login-refusals.md` - error contract and the
   login / reconnect / slot refusals.
4. `task-english-release-04-broker-send-status-room-posts.md` - send, inbox,
   status, the notices posted into the room, status as a code.
5. `task-english-release-05-broker-runtime-and-store.md` - startup and
   shutdown, English logs, coded store errors.
6. `task-english-release-06-envelope-language.md` - envelope `kind` as a code,
   the envelope text for agents in both languages.

Phase C - client and kit

7. `task-english-release-07-client-language-source.md` - how the client knows
   the room language, including when the broker is unreachable.
8. `task-english-release-08-client-session-commands.md` - `login`, `logout`,
   `status`, with a machine-readable result.
9. `task-english-release-09-client-messaging-commands.md` - `wait`, `inbox`,
   `say`, `ask`, and the help of every subcommand.
10. `task-english-release-10-kit-machine-contract.md` - `install` and
    `uninstall` report actions as codes; the installer stops parsing prose.
11. `task-english-release-11-kit-install-messages.md` - the sentences of
    `install` / `uninstall`, the language flag, the installer forwards it.
12. `task-english-release-12-plugin-machine-contract.md` - the OpenCode plugin
    stops matching Russian phrases; its log is English.

Phase D - what agents read, and what the operator runs

13. `task-english-release-13-kit-language-layout.md` - the kit ships a variant
    per language and the install picks one.
14. `task-english-release-14-skill-claude-english.md` - the Claude Code
    `chatlogin` skill in English.
15. `task-english-release-15-skill-opencode-english.md` - the OpenCode skill
    and command in English.
16. `task-english-release-16-launch-scripts-and-templates.md` - `start` /
    `stop` scripts and the Docker and config templates.
17. `task-english-release-17-operator-tools-and-final-scan.md` - the remaining
    operator tool and the test that nothing Russian is left outside the
    catalogues.

Phase E - documents and the gate

18. `task-english-release-18-docs-install-english.md` - the English install
    guide.
19. `task-english-release-19-docs-architecture-integration-english.md` - the
    English architecture and agent-integration guides.
20. `task-english-release-20-public-release-gate.md` - what the README says
    about the documents still in Russian, a clean-machine English run by the
    human, the CHANGELOG, the decision to open the repository.

Dependencies: 02 needs 01; 03-06 need 02; 07 needs 02; 08 and 09 need 07;
10 needs nothing; 11 needs 07 and 10; 12 needs 08; 13 needs 11 and 12; 14 needs
13, 08, 09; 15 needs 14; 16 needs 02; 17 needs 01-16; 18 needs 11; 19 needs 06
and 08; 20 needs all. Tasks 01, 10 can start at once; 03-06 can run in parallel
after 02 only if their catalogue files are merged by key (they share
`broker_messages/*.json`), otherwise run them in order.

## Known issues

Open defect reports at the time the story is merged. None is fixed by this
story. Statuses are those the reports carry; whether any of them blocks opening
the repository is an owner decision, not recorded here.

Found by the live run on the existing installation (2026-10-06):

- [Client network-error text can expose the session token](../bugreports/client-network-error-exposes-session-token.md).
  `wait`, `inbox` and `ask` print the full `requests` exception, and the URL of
  an authenticated GET carries the token. Shown with a synthetic token only; not
  exercised with a real token or a real outage.
- [Claude background launch cannot be verified through its control pipe](../bugreports/claude-background-session-control-pipe-unavailable.md).
  `claude --bg` reports "backgrounded", but `claude logs` fails with ENOENT on
  the daemon pipe. Environment of the installed CLI, not Quoroom code; the live
  run used interactive sessions instead.
- [Windows cURL cannot establish revocation status for the mkcert certificate](../bugreports/windows-curl-mkcert-revocation.md).
  A strict readiness request to the local Matrix fails with
  `CRYPT_E_NO_REVOCATION_CHECK`; the run used `--ssl-revoke-best-effort` with
  the owner's permission.

Found earlier, in the local-installers and kit work:

- [Ctrl+C at the purge prompt does not give exit code 4](../bugreports/installer-ctrl-c-at-purge-prompt.md).
  The installer ends with a traceback and the interpreter's exit code instead of
  the code for a declined purge.
- [A usage error raised inside a step exits 1, not 2](../bugreports/installer-usage-error-inside-a-step.md).
  Needs an unreadable first answer to the interactive CLI question.
- [The plugin does not strip a trailing slash from AGENTSCHAT_URL](../bugreports/plugin-trailing-slash-broker-url.md).
  The OpenCode plugin requests a doubled slash; the CLI does not. Read off the
  source, not observed live.
- [verify-copy.sh checks a plugin path that the kit no longer has](../bugreports/verify-copy-checks-a-missing-plugin-path.md).
  A test helper in `tools/linux-container/` reports success for a check that
  cannot run.

## After the release (not gating)

- Source-code comments and docstrings in `bridge/` (about the same count as the
  runtime strings) move to English in a separate card; AGENTS.md rule 7
  already says comments are exceptions, so part of this is deletion.
- `docs/SESSION_BRIDGE.md`, `docs/VERIFICATION.md`, `docs/COORDINATION_PLAN.md`
  in English, if contributors ask for them.
- Retiring `README.ru.md` and `docs/*.ru.md` is not planned; the Russian
  documents stay as the second language.

## Acceptance criteria

- [ ] On a clean machine, with `language` unset in `config.yaml`, installing
      the stand and a participant and exchanging a message between two agents
      produces English only in the installer, every `agentschat` command, the
      broker's answers, the room notices, the agent envelopes and the skills.
      The human runs this and the result is recorded in `docs/VERIFICATION.md`.
- [ ] With `language: ru`, the same run prints what it printed before this
      story, character for character where the text is catalogued.
- [ ] No component decides an outcome by matching a sentence: a test per
      boundary (installer-client, plugin-client, client-broker) passes with the
      sentences replaced by different words.
- [ ] A scan test finds no Cyrillic in runtime code, scripts and templates,
      outside the `ru` catalogues, the `ru` variants of the kit and an explicit,
      reasoned allowlist.
- [ ] Full suite, `node --test`, `ruff check` and `ruff format --check` green.
- [ ] `README.md` says which documents remain in Russian.
