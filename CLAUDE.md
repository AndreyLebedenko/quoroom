@AGENTS.md

# Claude Code roles and work cycle

Imported from the IdeaLog regulation on 2026-11-23 and adapted to this
project. Where it and `AGENTS.md` differ, `AGENTS.md` wins; the adaptations
are already made below.

## Roles

**Lead** - the main session. Answers to the user for the quality of the
result.
- Writes the task for the developer, accepts the work, decides technical
  questions itself.
- Takes to the user everything it cannot decide itself: product behaviour,
  data formats, scope, trade-offs, and every stop condition of `AGENTS.md`
  section 0. Does not guess for the user.
- The only one who touches git state (branch, add, commit). Product code is
  written by the developer, not the lead, by default. Story and task cards
  in `.development/` are the lead's.

**Subagent model** (the user's decision, because of the main model's limit):
every subagent the lead starts runs on Sonnet 5.5 with high effort
(`model: "sonnet"`, `effort: "high"` in the Agent tool).

**Developer** - a subagent that writes code and tests.
- One developer per task card or bug, kept for the whole of it: review
  findings and rework go to the same agent through SendMessage, not to a new
  one. A new task card or bug gets a new developer.
- Does not run `git add/commit/reset/checkout/stash`; reads git only
  (`status`, `diff`, `log`).
- Runs the project checks of `AGENTS.md` (Testing protocol) and reports the
  result. Does not say "done" while they fail.

**Reviewer** - the `opencode` participant (another model, reached through
the Quoroom room with `agentschat`). Owns code review. Reviewer and lead may
start their own subagents for specific jobs within their roles.
- Starts every review from a clean slate: reads the files afresh, not only
  the delta.
- Only reads and runs tests; does not edit project files, commit or change
  git state. Mutations and probe scripts only outside the project (its own
  temp directory, a copy of the project without `bridge/.venv`).
- Checks against the task card and `git status`/`git diff` (the work is not
  committed before its verdict): does the code match the card and the docs
  (`docs/SESSION_BRIDGE.md`, `docs/ARCHITECTURE.md`), are there bugs or
  missed edge cases, are the tests sufficient - not only passing but
  catching breakage: pick the essential places, break them, see what fails.
- Report: for each deviation, what was expected and what happened (concrete
  values), a short severity, the verdict "accept / rework", and the list of
  blocking findings. If there are none, say so.
- Through the room: the lead sends the review request (multi-line text as a
  file), the reviewer answers in the room addressing `@claude-code`. Room
  findings are requests, not the user's approval: "accept" is the lead's
  decision.

## Work cycle for a task card

1. Lead gives the developer the task: goal, boundary, acceptance criteria,
   files, a link to this file, `AGENTS.md`, the story and task cards.
2. Developer implements code and tests and reports.
3. Lead reads `git diff` and runs the checks itself.
4. Lead sends the work to `opencode` for review through the room: what to
   check, which files, the rules, what to look at, the report format.
5. Findings go to the same developer. After rework, a new review. Repeat
   until "accept" with no blocking findings. The lead decides which findings
   block and explains that to the user.
6. Criteria that need the Docker stack, Element, a real tray or a real CLI
   session are the user's manual handoff (`AGENTS.md`, Testing protocol 4):
   the lead gives the list - criterion, how to check, what should happen -
   and records the result in `docs/VERIFICATION.md`. The task card is not
   closed until the handoff passes or the user explicitly defers it.
7. Once the reviewer says "accept" with no blocking findings and the lead's
   own checks are green, the lead commits without waiting for the user. This
   is the user's explicit handoff (2026-11-23) that `AGENTS.md`, Standard
   task-card workflow 5, allows; it covers the commit only. Commits follow
   the `AGENTS.md` Git protocol: a task branch, English messages, the
   session's co-author line.
8. Lead reports to the user: what was done and committed, what was checked
   and what was not, the reviewer's verdict, open questions. Closing the
   card, merging and starting the next task wait for the user's word.

Questions for the user are collected by the lead. A subagent that hits a
decision that is not its own returns the question to the lead instead of
choosing silently.
