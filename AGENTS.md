# Agent Instructions

0. Stop and explain when:
   0.1. There is a question to which there is no answer in the spec,
        documentation, or this file.
   0.2. There is a conflict between requirements — e.g. the spec contradicts
        existing code or two other files.
   0.3. A change turns out to affect more than expected — e.g. a small fix
        requires reworking something large.
   0.4. Two approaches have non-obvious trade-offs and the choice has
        architectural consequences.
   0.5. Tests are failing for a reason outside the scope of the task.
   0.6. A circular dependency is detected.
   0.7. You are looping — if you are attempting the same fix or approach for
        the second time, stop. Specific symptoms:
        - The same error reappears after a fix
        - You are applying a third (or more) workaround to the same place
        - A test was written, broke, rewritten, and broke again for the same
          reason
   0.8. You cannot write a test for code you just wrote — this is a design
        problem, not a test problem.
   0.9. Build or test tooling produces an unexpected error (including
        access/permission errors, missing dependencies, environment issues).
        Do not attempt to work around infrastructure problems.
        Exception: follow the Codex approval rules in the `Codex` section
        before treating `A specified logon session does not exist` as a stop
        condition.
        Rule: an error in the code is your responsibility;
              an error in the environment is not.

## Project context

1. Read `README.md` and `docs/SESSION_BRIDGE.md` before any work.
   `SESSION_BRIDGE.md` is the source of truth for architectural decisions and
   why the first-generation bridge was abandoned; `docs/ARCHITECTURE.md`
   describes the parts. `docs/VERIFICATION.md` records what was verified live,
   as opposed to what is only covered by tests. Facts recorded there as
   verified are settled; do not re-test or reverse them without the human's
   explicit request.
2. When an architectural decision changes, update `docs/SESSION_BRIDGE.md` in
   the same commit as the change. When something is verified live, add it to
   `docs/VERIFICATION.md` with what was run, what was observed, and the date.
   A spike's written result is read by an agent that will implement from it
   without having seen the probing. Write it so that implementation from the
   text alone is safe:
   - State *who consumes the mechanism and when it runs* — a trigger with an
     actor, not a general truth. "The broker reads X when a token holder
     reattaches" is implementable; "X must be read after a restart" invites
     an agent to build it on the wrong trigger, for everyone and at startup,
     where nobody needs it.
   - State *what breaks without it* — the operation that is impossible, not
     the benefit gained. An agent told only the benefit invents harmless-
     looking extra work; an agent told the concrete lost delivery knows
     exactly what the code path exists for.
   - Separate the verified finding (what was run, what was observed) from the
     recommendation built on it. Findings are settled; a recommendation is
     revisable without re-testing.
   Why this is right: the consumer of the text is an implementer with no
   access to this conversation. A formulation that is merely true leaves it
   to the reader to guess trigger, scope and purpose — and a guessing
   implementer programs the guess. The cost of a wrong guess here is real
   code doing real work for no one (polling dead subscriptions, restoring
   queues nobody will drain), not just a wrong sentence.
3. `legacy/` holds the first-generation bridge. It does not run and is not
   maintained. Do not import from it, fix it, or use it as a pattern.
4. Documentation references to project files should use stable filename
   identity when the filename is unique in the repository. Directory paths in
   prose are hints, not authority, unless the path is part of an executable
   command, storage contract, generated artifact location, import/module
   boundary, or intentionally path-scoped file. If a prose reference points to
   a file that is not at the written path, search by filename with `rg --files`
   before treating the reference as stale or broken.

## Core engineering principles

1. Always follow best practices.
2. Always respect SRP.
3. Always write clean code.
4. Code is clean if it is easy to test and easy to expand without violating
   the SRP or Best Practices.
5. Work in TDD style where practical.
6. Each test must be self-explanatory.
7. NO Comments: write a verbose test instead of a comment in the code.
   A rule you are tempted to explain in a comment is a rule you can assert.
   This includes relationships between constants — a threshold justified by
   another constant is an invariant, and an invariant is a test that breaks
   when the other constant moves, where a comment would silently go stale.
   Exceptions:
   a. Pinned versions (i.e. "Why this version?")
   b. Workaround for known/discovered bug or limitations (i.e. "Don't fix
      this")
   c. Comments in the tests to link them to a design spec or a task (or a
      bugfix)
   Not a fourth exception, a routing rule: a fact about the outside world that
   has no site in the code — what a CLI's control socket supports, what a
   homeserver implements — goes to `docs/VERIFICATION.md`. Having no natural
   site is the signal that it is documentation. Once such a fact does anchor to
   a line that would otherwise be "cleaned up", exception (b) already covers it.
8. Do not add code documentation to compensate for unclear design.
9. Use ASCII punctuation and status markers in English documentation, code
   identifiers, logs, and commit messages. Avoid symbols that render poorly in
   some terminals, such as long dashes and check marks.
   Exception: Russian text is data, not documentation — `README.ru.md`, `docs/`,
   the skills and command under `bridge/sessionchat/kit/`, and every runtime
   string an agent or a human reads (envelopes, refusals, broker notices).
   Normal Russian typography applies there; do not "fix" it.
10. Use UTF-8 for project files unless a file or external format explicitly
    requires another encoding.

## Locality contract

1. Everything runs on one machine. Federation with the outside Matrix world is
   off, and turning it on is not a task-level decision.
2. The broker is the only holder of Matrix access tokens. A session talks to
   the broker and never to the homeserver, so it cannot leave the room, send a
   direct message, or publish as another agent. Do not add a path that gives a
   session a Matrix token.
3. Secrets live in `bridge/config.yaml`, `bridge/state/` and
   `docker/continuwuity/continuwuity.toml`, all gitignored. Never commit them,
   never paste their contents into a report, never echo a token into a log.
4. Live checks need the Docker stack, Element in a browser and real CLI
   sessions. Nothing in CI may depend on them.

## Testing protocol

1. Automated tests are `unittest`. Run them from `bridge/`:
   `.venv/Scripts/python.exe -m unittest discover -s tests -t .`
   There is no pytest in this project; do not add one.
2. The OpenCode plugin is tested with `node --test` against
   `bridge/tests/plugin/agentschat.test.mjs`.
3. Lint and format with `ruff`: `ruff check` and `ruff format --check`.
   Run these commands sequentially, never in parallel: both write to the same
   `.ruff_cache`, including in check-only mode. More generally, serialize
   checks that share a writable cache or other generated state.
4. Anything that needs the Docker stack, Element, or a real Claude Code /
   Codex / OpenCode session is a human-run manual handoff. Prepare it
   explicitly — what to run, what to look for — and record the result in
   `docs/VERIFICATION.md`. "Green" for such work means the automated suite
   passes and the manual handoff is prepared.
5. Cloud CI, if added, is allowed only for the automated suite: installing
   `bridge/requirements.txt` plus `bridge/requirements-dev.txt` and running
   the two commands above.

## Tooling notes

1. This is a Windows 11 setup. Python 3.11, asyncio, aiohttp, matrix-nio.
2. The project virtualenv is `bridge/.venv`. Use it explicitly; the system
   Python does not have the dependencies.
3. Install Python packages with `pip`; keep `bridge/requirements.txt` current
   in the same commit that introduces a dependency. The runtime dependency
   list is deliberately short — adding to it needs a reason in the task card.
4. The `chatlogin` skill exists in two copies,
   `bridge/sessionchat/kit/claude/skills/chatlogin/` and
   `bridge/sessionchat/kit/opencode/skills/chatlogin/`, installed per user by
   `agentschat install` (see `docs/SESSION_BRIDGE.md`). They differ by design:
   delivery mechanics differ between the CLIs. Do not make them identical.
   What they share (`login`, `say`, `ask`, `status` and the boundaries
   section) must agree functionally; byte identity is not required. Changing
   a shared part in one copy without the other is a defect. Codex's skill
   location is `.agents/skills/`; it holds no chat skill (see the `Codex`
   section), and the directory is absent until a Codex skill appears.
5. When reading project text files with PowerShell, pass `-Encoding UTF8`
   explicitly, e.g. `Get-Content -Raw -Encoding UTF8 README.md`.
6. Codex may correct a Python command's console-encoding mismatch by setting
   `PYTHONUTF8=1` and/or `PYTHONIOENCODING=utf-8` for that process only. This
   is an approved environment normalization, not an infrastructure workaround,
   and does not require a stop under section 0.9. Do not change the system code
   page, registry, or persistent user/machine environment for this purpose. If
   the same encoding error recurs after the per-process setting, section 0.7 or
   0.9 applies as usual.
7. On Windows, do not pass wildcard path arguments such as `logs/*.log` or
   `src/module*` to `rg`; they can fail with OS error 123 because PowerShell
   does not expand them as a POSIX shell would. Keep `rg` as the default search
   tool and use its `-g` option when possible. If the operation specifically
   needs PowerShell wildcard enumeration, use
   `Get-ChildItem -File -Filter ... | Select-String -Pattern ...` instead of
   retrying the failing `rg` form.

## Git protocol

1. Commit before any destructive or wide-ranging change (file deletion,
   mass rename, rewriting a module).
2. Never delete or rewrite files outside the active task scope without
   explicit confirmation from the human.
3. Create a new git branch with a task-appropriate name unless the human
   explicitly asks to use the current branch.
4. Commit messages are English, and say what changed for the reader rather
   than which files moved.

## Codex

0. Codex works *on* this project; it is not a participant *in* the room. Room
   support for it was removed in v1.0.0 because its delivery mode could not
   acknowledge, and reinstating it is not a task-level decision. An OpenAI-
   backed participant is reached through OpenCode's plugin mode instead.
1. For Codex-based agents, the Codex approval mechanism is the default path
   for required commands and `approve` must be always used to run any commands
   or scripts.
2. If the approved run is denied, cannot start, or fails with the same
   infrastructure error, report the infrastructure error and stop. Do not
   attempt a different command, shell, interpreter, or other workaround.
3. For other Codex sandbox, logon-session, or permission failures, report the
   infrastructure error and stop unless the human explicitly authorizes an
   approved/escalated run. Use the approval mechanism for that exact command
   and record the result in the task handoff.

## Task documentation workflow

1. Keep implementation planning in `.development/`.
2. Use a story card for a larger feature or multi-step change. The story card
   should describe the user-facing goal, boundaries, acceptance criteria, and
   the ordered task-card sequence.
3. Use task cards for implementation slices that can be completed and verified
   independently. A task card should state status, summary, current boundary,
   and acceptance criteria.
4. Before starting a task card, read the relevant story card, task card,
   project docs, and source code. If the requirements are unclear or conflict
   with existing code, stop and ask before implementing.
5. While implementing, keep the code change scoped to the active task card.
   Do not silently pull later story-card steps into the current task.
6. When a task card is complete and verified, change its status to
   `Completed` and move it to `.development/tasks/closed/`. Leave the story
   card in `.development/tasks/` until the full story is complete.
7. Some tasks can be closed with `Rejected` + explanation.

## Standard task-card workflow

After reading the relevant story card, task card, docs, and source code:

1. Ask all blocking questions before implementation. If there are no
   questions, or the questions have been answered, proceed.
2. Follow the Git protocol above for branching.
3. Implement the required code and/or data changes within the active
   task-card boundary.
4. Run the required project checks and reach a green state, or stop and
   report if any stop condition from section 0 applies.
5. Unless the human explicitly asked for a different handoff, stop after the
   implementation and verification summary, then wait for human review before
   closing the task card, committing, merging, or starting the next task.

## How to report an issue

1. If an implementation or live check reveals a behavior that should not be
   fixed in the current change, write an edge case report before moving on.
2. Store reports as Markdown files under `.development/bugreports/`; move them
   to `.development/bugreports/closed/` when fixed, keeping the file rather
   than deleting it.
3. Include:
   - the current commit id where the issue was detected;
   - symptoms visible to the user or tester;
   - the suspected current cause;
   - the temporary decision, including why that decision was chosen over
     nearby alternatives;
   - future considerations and boundaries for later work.
4. Keep the report focused on the issue. Do not mix unrelated bugs, feature
   wishes, or broad roadmap notes into the same report.

---

## Communication protocol

- Russian for conceptual and architectural discussion; English for code,
  identifiers, commit messages, and development documentation under
  `.development/`. `README.md` is English and is the main README; `README.ru.md`,
  `docs/` and the skills are Russian — they are read by the human and by agents
  at runtime, not by the build. Keep the two READMEs in step.
- Be concise. No preamble, no postamble, no restating the task back.
- Prose by default; minimal markdown.
- Push back directly when you disagree or see a problem. Do not validate
  decisions you consider mistaken. A stated position with reasoning is
  expected; hedging without a position is not.
- Cross-domain analogies are welcome when they carry real explanatory weight.
