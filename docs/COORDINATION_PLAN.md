# Project coordination implementation plan

> **Отменено.** Этот план описывает координацию поверх моста первого
> поколения: сессии, принадлежащие мосту, и отдельный контур эскалаций
> для человека. От обоих решений отказались — человек стал участником
> наравне с агентами, а сессии в чат приводит он сам. Живая
> архитектура описана в [SESSION_BRIDGE.md](SESSION_BRIDGE.md).
> Документ сохранён как история решения.


Status: In progress.

## Approved objective

Use bridge-owned continuing agent sessions, Matrix for short exchanges, and
project files for durable reports and decisions. Human attention belongs in
Escalations. SpaceRobots is the first connected project; implementation checks
must use an isolated project and must not start development work in SpaceRobots.

## Boundaries and contracts

- One deployment connects one project, General, Escalations, and three named
  agents. Session identity is (discussion, agent); the working directory is the
  project root. This keeps unrelated discussions out of each other's context.
- Agents publish concise summaries and explicit routing actions. Full reports
  are immutable Markdown records under a bridge-owned subdirectory of each new
  discussion in `.agent-comms/active`. Existing discussions are not migrated.
- SQLite owns delivery state, session IDs, sync cursors, and an outbox. Files own
  substantive reports and human decisions. Matrix event links preserve evidence.
- Event IDs deduplicate input. Stable Matrix transaction IDs deduplicate output.
  A process crash during an agent run has an uncertain outcome: stop that job and
  notify the human rather than re-executing potentially completed code changes.
- No automatic CLI retry after an ambiguous failure. Failed publication can be
  retried independently of agent execution. Records are written before notices.
- Each discussion has a coordinator, participants, a round (maximum three), and
  blocking issues. Only its coordinator opens a revised round. Bound requests
  per round to prevent an accidental agent loop; hitting the limit escalates.
- Veto, requests for a human decision, and readiness for acceptance block further
  execution in that discussion. Already executing turns cannot be undone; their
  results may be recorded, but subsequent work remains blocked.
- Only configured human Matrix identities can start work or resolve issues.
  An explicit `/answer ISSUE text` in Escalations records human guidance and
  releases the corresponding blocker. A plain reply is not inferred approval.
  Remaining blockers continue to prevent execution. Human guidance is delivered
  to the coordinator; original failed jobs are never replayed automatically.
- Agents must read project instructions, task cards, decisions, and referenced
  artifacts. Chat does not override required project approvals or git policy.
- The service does not modify SpaceRobots source, close task cards, or merge code
  during deployment. Real work begins only with a user's project request.
- Desktop/mobile notification delivery also depends on Element/OS settings;
  the bridge supplies an explicit human mention and a Matrix event permalink.

## Implementation sequence

1. Durable state, strict response protocol, artifact writer; behavioral tests.
2. Claude, Codex and OpenCode session adapters; timeout and parsing tests.
3. Coordinator, queues, blockers, human decisions, rounds and outbox; functional
   tests covering restart, duplicate events, publication failure and veto.
4. Matrix transport and service lifecycle; explicit start/stop/status commands.
5. Isolated live checks with the actual three CLIs and Matrix, then connect the
   idle production service to SpaceRobots. Document commands and limitations.

## Acceptance evidence

Record red/green checks, relevant coverage, real session-resume checks and live
Matrix results here as each stage completes. Do not describe an unexecuted check
as passed.

## Initial state

- Repository signing disabled locally: commit.gpgsign=false, tag.gpgsign=false.
- Baseline saved before implementation on branch feat/project-coordination.
- Legacy bridge remains running until the replacement passes isolated checks.
