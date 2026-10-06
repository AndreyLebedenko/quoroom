# Task: Verify the English release on the existing Windows installation

**Status:** Completed. Existing-installation English/Russian checks and restoration passed; owner review done.
**Candidate:** 9744e12 (story/english-release).
**Verified runtime commit:** ee1d1d12606e6741ad9a43db96859ea925ee38de (parent 9744e12).
**Related story:** story-english-release.md.

## Summary

Verify the release candidate against the existing local Matrix data, in English
and Russian, including real Claude Code and OpenCode sessions outside Quoroom.
The owner explicitly authorized agent-run live checks on 2026-10-06, overriding
only the human-run handoff requirement of AGENTS.md for this assignment.

## Boundary

- Automated project checks, client commands, participant installation, room
  language, depth-limit notice, and real session delivery.
- Preserve the existing installation and restore all temporary configuration,
  client package and kit changes. Use only task-related files and processes.
- No server purge, clean-machine claim, unrelated production code fixes, task-20 closure,
  commit or merge. Record defects separately and obey remaining stop conditions.
- Existing server data remain in D:/AI/Quoroom. Temporary runtime files and
  evidence remain within this task's workspace and ignored local state.
- The owner authorized a focused prerequisite: exclude tokens from the broker
  access log, preserve useful diagnostics, verify it, record it, then resume E2E.

## Acceptance criteria

- All four project checks pass on the candidate before live changes.
- Record the tested build and runtime origins explicitly.
- Verify English default without the language key and explicit Russian.
- Verify client commands and stable machine results in both languages.
- Verify participant-install language learning with clean client language state.
- Verify a depth-limit refusal and room notice in both languages.
- Verify installed skills and login-result plugin binding in real sessions,
  human-to-agent delivery and agent exchange in both directions.
- Record actual observations in VERIFICATION.md, distinguishing an existing-
  installation regression run from the clean-machine release gate.
- Restore the initial stopped stand, client package origin, kit and client state.
- Stop for owner review after verification or any remaining stop condition.

## Current handoff

Preflight confirmed that the installed client is editable from D:/AI/Quoroom
(7feb147), the Matrix volumes remain, and no agentschat containers or listeners
on 443/8770 were running. The four installed kit files match their manifest.
Seven task-related original files were backed up under ignored
bridge/state/e2e-20261006/backup, without changing the originals. The manifest
already contains historical temporary-directory entries; they were not cleaned.

The authorized access-log fix is implemented and verified: 1767 unittest
tests passed, one skipped; 28 plugin tests passed; Ruff check and format check
passed. A separate client network-error disclosure was recorded without
expanding the production fix.

The candidate client package was temporarily installed and the original Docker
stack started with its existing volumes. The execution tool then rejected the
readiness-and-broker-start command before execution, with blocked by policy.
Following the Codex stop rule, no alternate launch was attempted. The candidate
broker, participant installation and session E2E were not run.

The original editable package origin, receipt and launcher were restored.
Scoped state checks and all existing .agentschat file hashes match the backup.
The three containers and network created for the task were removed; the three
server volumes remain. The initial stopped stand is restored. See the report
with this filename under .development/reports/ for commands and observations.

The owner then authorized a direct Matrix request without approve. After
starting the original stack again, the direct cURL readiness request executed
but failed in Windows Schannel with CRYPT_E_NO_REVOCATION_CHECK (0x80092012).
Stop rule 0.9 applies. No alternate client, certificate-check bypass or broker
launch was attempted. The client and participant files were unchanged in this
continuation. Docker compose down restored the stopped stand without deleting
the three original volumes. The report records the exact command and error.

The owner subsequently authorized --ssl-revoke-best-effort for the local
readiness request, which returned Matrix versions successfully. The candidate
client, English participant kit and task broker were started. English terminal
commands and max_depth 1 refusal passed against real Matrix; both registrations
were logged out. Actual CLI session binding and the Element notice are not
proven by those terminal checks. Computer Use stopped while reading the owner's
open Chrome Element window because it could not determine its current URL.
The candidate installation, Docker and broker remain active; restoration is
pending. The report separates all attempts and records the current state.

The owner connected the Chrome extension. Reading General now succeeds under
human, and the actual English depth-limit notice was observed. The attempted
Russian phase switch then stopped before mutations: the task broker's process
tree includes conhost.exe, which the helper's Python-only guard rejects. This
task helper already required one correction; another change/rerun is held for
owner review. See e2e-phase-switch-rejects-conhost.md. The English broker,
candidate client and Docker remain active; both participants are disconnected.

The owner authorized the helper correction; bounded conhost validation and
DryRun passed. Russian participant installation, all command scenarios and
depth refusal passed live. Element displayed both languages' room notices.
After owner-authorized retry of native input, OpenCode's task scratch project
and fresh draft opened. No login or plugin binding has occurred there. Claude
--bg refused that directory as untrusted before launching; the owner was asked
to run claude there once, accept trust only for that folder and exit. The
Russian broker and candidate installation remain active without participants.
Actual session delivery and final restoration remain open.

The owner completed trust and dismissed Claude's browser-tools question. The
normal interactive scratch session is visible. Two authorized --bg launches
returned identifiers and idle, but logs failed with ENOENT for the background
control pipe; neither background session appeared in agents --json. Stop rule
0.9 applies. See claude-background-session-control-pipe-unavailable.md.

Final restoration passed: the original package origin, launcher and receipt,
all kit/session inventory checks and all original .agentschat file hashes.
The task broker and task-launched OpenCode were stopped; Docker containers and
network removed with all three original volumes preserved. No 443/8770 listener
remains and D:/AI/Quoroom is clean. The owner's interactive Claude and Chrome
were retained. Actual session binding, listener and human delivery remain open.
The task is held for owner review; no commit, merge or card closure occurred.

The owner subsequently authorized an interactive handoff: they type commands
in real CLI sessions and Codex verifies broker status, task logs and Element.
The original inventory was checked before holding the two backed-up session
files again. The English candidate client, kits, Docker and task broker are
ready; both participants remain disconnected. The --bg path is not retried.
Original backups remain for final restoration after the interactive checks.

## Final verification handoff

Owner-driven real sessions passed in English and Russian: positive OpenCode
binding by login result, Claude listener startup/wake-up/restart, human delivery
to both sessions and substantive replies, and agent exchange in both directions.
Claude initiated the English chain (56); OpenCode initiated the Russian chain
(54). Both human checks returned 42. Claude's actual incoming envelopes in both
languages identify human versus agent and show the expected chain depth and
authority boundary. The rendered OpenCode envelope itself was not inspected.

Both language phases ended with successful logout inside the real sessions.
The final plugin poll and Claude wait stopped before broker shutdown. Original
package origin, receipt, launcher, kit/session inventories and all initial
.agentschat file hashes match the backup. No 443/8770 listener or agentschat
container remains; the three original Docker volumes are preserved and the
old Quoroom checkout is clean. Owner-opened CLI apps and Chrome were retained.

Automated checks remain green: 1767 unittest tests, one skipped; 28 Node tests.
Final Ruff check and format check and git diff --check passed. No production
code changed after the full suite. Saved broker logs contain neither configured
Matrix tokens nor token= query markers. The detailed report distinguishes these
observations from the remaining clean-machine installation gate.

All acceptance criteria for this existing-installation task are satisfied.
The card remains open for owner review; no merge or closure occurred. At the
owner's subsequent request, the unchanged access-log fix, its tests and closed
issue report were committed as ee1d1d12606e6741ad9a43db96859ea925ee38de.
The main checkout's current branch does not contain that fix. The report records
file hashes proving identity with the runtime used for the suite and live checks.
