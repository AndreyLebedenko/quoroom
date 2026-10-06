# English release: focused logging fix and existing-installation E2E

**Status:** Existing-installation English/Russian verification passed; original installation and stopped stand restored. Awaiting owner review.
**Base candidate:** 9744e12, story/english-release.
**Verified runtime commit:** ee1d1d12606e6741ad9a43db96859ea925ee38de.
**Branch:** codex/english-release-e2e.
**Owner authorization:** 2026-10-06, agent-run live checks and the focused
access-log prerequisite; unrelated storage and code remain outside scope.

**Implementation and ignored evidence:**
C:/Users/adinor/.codex/worktrees/english-release-e2e/AgentsChat.
This report and the open task card were transferred to D:/AI/AgentsChat at the
owner's request. Production changes, backups and the five related issue reports
remain in the implementation worktree; no code change was transferred or merged.
Original issue reports are in that worktree's .development/bugreports/ (including
closed/ for the fixed broker logger and phase-switch helper). The open client
network-error and Claude control-pipe reports were also copied without changes
to this checkout so the result's limitation links remain usable.

## Verified outcome, 2026-10-06

The existing-installation regression run passed on the runtime now identified
by commit ee1d1d12606e6741ad9a43db96859ea925ee38de. The owner typed commands in real Claude
Code and OpenCode sessions; Codex checked broker status, process ownership,
plugin logs, the exact task Claude transcripts and the signed-in Element room.

| Scenario | English | Russian |
| --- | --- | --- |
| Participant install learns room language before first help | Passed | Passed |
| Client commands, refusals and stable machine results | Passed | Passed |
| Depth-limit refusal and actual Element room notice | Passed | Passed |
| Claude background listener startup, wake-up and restart | Passed | Passed |
| OpenCode binding by login result and delivery into that session | Passed | Passed |
| Human message independently received and answered by both sessions | Passed | Passed |
| Agent exchange in both directions, with a final report to human | Passed | Passed |
| Orderly logout before shutdown | Passed | Passed |

Full automated discovery before live work: 1767 tests, one skipped, no failures;
28 Node plugin tests passed. No production code changed after those checks.
Final Ruff check and format check passed; git diff --check passed. The initial
client package origin, receipt, launcher, kit and client state were restored
and hash-checked. Docker is stopped with all original volumes preserved.

The rendered incoming envelope was read in Claude in both languages. OpenCode
was verified through positive login-result binding, delivery logs and actual
room replies; its rendered envelope itself was not inspected. Existing data
and manual session input do not establish the clean-machine release gate.
The separate background-launch control-pipe issue remains recorded; interactive
handoff completed the task's session scenarios without repairing that CLI path.
The runtime was committed after the run at the owner's request; no merge or
task-card closure was performed.

### Durable identity of the verified runtime

Commit ee1d1d12606e6741ad9a43db96859ea925ee38de has parent
9744e12c0e858ad23a40b14ffa6ca57d2fb67d07. Its only production changes are
access_log.py and the Broker.run wiring in broker.py. It also records the four
logging tests and the closed issue report. The commit exists in the shared
repository and can be inspected from D:/AI/AgentsChat with git show; it has
not been merged into that checkout's current branch.

The commit was created after E2E, without changing the runtime files. Their
SHA256 values match those recorded after the full suite and live checks:

| File under bridge/ | SHA256 of the verified working file |
| --- | --- |
| sessionchat/access_log.py | 66F03A3C3737A68C1D5C91BBE93BF26B9293504497F9DC84D860C69A48A12550 |
| sessionchat/broker.py | 1EB34F6ED9BC135B21FFD424A29E43B32AE05BE655E338DF805784756E1E6400 (working file with CRLF) |
| tests/test_broker_access_log.py | B70B184E95ACC8B77EF8DBF2F2910A7A06DE9A06FADDF0460CD673621C213F24 |

The hash of `broker.py` is that of the working file, which has CRLF line
endings on this checkout (`* text=auto` in .gitattributes). The blob stored in
`ee1d1d12606e6741ad9a43db96859ea925ee38de` has LF endings and its SHA256 is
DCEA1B131C87E112CC5FB02D59DC22F51823EA16CBED9D9437AC1A582C96CC37. The working
file hashed after converting CRLF to LF gives this same value, so the code is
the same.

The four access-log tests were run again before committing and passed. The
complete suite and E2E were not repeated because the code is unchanged.
Earlier sections describing an uncommitted fix record the state at those
historical handoffs; the full commit above supersedes that identification.

Consolidated limits: the rendered OpenCode envelope was not inspected; random
session-token values were not audited retrospectively; the clean-machine gate
remains open. Separate known issues remain: [client network-error disclosure](../bugreports/client-network-error-exposes-session-token.md)
and [Claude background control-pipe failure](../bugreports/claude-background-session-control-pipe-unavailable.md).
The first was not exercised with real tokens; the second was replaced by an
interactive handoff without repair. Passing delivery scenarios do not claim
these issues are fixed.

## Focused prerequisite

The default aiohttp access logger includes both query parameters and Referer.
A functional test exercising Broker.run with real HTTP requests reproduced
session-token disclosure for accepted and refused GET /wait and /inbox.

The broker now selects a dedicated AccessLogger through AppRunner's supported
access_log_class option. Records contain method, path, response status and
duration. Query parameters, headers and response bodies are excluded. The HTTP
protocol, authentication, Matrix credentials, queue and delivery behavior are
unchanged. No new dependency was added.

Added three unit tests and one startup functional test in
test_broker_access_log.py. Unit tests exercise successful and refused requests,
repeated token parameters, secret-bearing request headers, response bodies,
and retained diagnostics. The functional test covers actual startup wiring and
both authenticated GET endpoints with valid and invalid session tokens.
No existing test was changed.

The initial functional test enabled capture after the HTTP connection had been
created, so aiohttp had already cached logging as disabled for that connection.
The fixture was corrected to enable logging before opening the connection; it
then failed on the actual token disclosure. Production code was changed once,
and the same functional test passed without further changes to its expectations.

Targeted validation: unittest tests.test_broker_access_log
tests.test_broker_runtime_store, 49 tests passed. Ruff formatted the new test
file; both production files required no formatting changes. Full checks and
live observations follow below.

Additional checks passed: node --test tests/plugin/agentschat.test.mjs,
28 tests; ruff check, no findings; ruff format --check, 77 files formatted.
After adding the new files to Git's tracked-file inventory, the Cyrillic scan
was checked again: 49 tests passed. The complete unittest discovery passed:
1767 tests in 852.538 seconds, one skipped; no failed tests remain.

The related-path inspection found a separate client network-error disclosure.
An isolated request with a synthetic token proved that requests.ConnectTimeout
contains the query credential. client.py renders requests exceptions in wait,
inbox and ask. This finding is recorded in
client-network-error-exposes-session-token.md and is outside the focused
broker logger change. No real-token outage was induced. Successful-response
E2E and orderly logout before broker shutdown do not exercise that path.

## Existing installation and preservation

The installed agentschat launcher resolves to editable D:/AI/Quoroom/bridge at
7feb147. Claude Code is 2.1.288. OpenCode Desktop is installed. Docker has the
three original server volumes, but initially no agentschat containers or
listeners on 443 or 8770 were running.

The four installed kit files match their existing manifest. Seven task-related
original files were copied into ignored bridge/state/e2e-20261006/backup with
an existence/hash inventory for restoration. The manifest's historical
temporary-directory entries were preserved without cleanup.

The original quoroom uv tool environment, its receipt and agentschat launcher,
and the original OpenCode plugin log were also copied into the ignored backup.
Hashes of every existing .agentschat file were recorded so restoration can
also verify unrelated participant files. OpenCode Desktop is version 1.18.34.

This is a regression run using existing Matrix data. It does not satisfy the
clean-machine installation gate of task english-release-20.

## Live attempt and execution-policy stop

After all required checks passed, uv tool install --force --editable switched
the installed agentschat launcher from D:/AI/Quoroom/bridge to this worktree's
bridge. uv reported exactly one package replacement, with the same version
1.0.0rc2. Docker compose up -d from D:/AI/Quoroom created and started the three
agentschat containers using the existing Docker volumes. No purge was run.

The next execution-tool call combined an HTTPS Matrix readiness request and
starting the candidate broker through Start-Process with WindowStyle Hidden,
explicit project Python, task configuration and only claude-code,opencode.
The execution tool rejected the entire command before execution:
CreateProcess / Rejected / blocked by policy. It supplied no more specific
reason. Neither the readiness request nor the broker launch ran. No broker
PID file, log or registration database was created by that rejected call.

AGENTS.md, Codex rule 2 requires stopping after a denied approved run and
forbids another command, shell, interpreter or workaround. No alternate
broker launch was attempted. Participant installation, English/Russian client
checks, Element, real CLI login, plugin binding, session envelopes and depth
notices remain unverified in this assignment. The terminal driver and four
ignored task configurations were prepared but not run.

## Restoration after the first attempt

uv tool install --force --editable D:/AI/Quoroom/bridge restored the original
client source. Its receipt and agentschat.exe SHA256 match their original
backups. All nine scoped existence/hash checks passed, and all nine pre-existing
.agentschat files retain their recorded SHA256, including unrelated agents,
the complete manifest and the plugin log. The language cache and participant
ownership record remain absent, as before this task. No kit or session file
had been changed.

Docker compose down from the original clone removed only the three task-started
containers and their network. All three original server volumes remain.
There are no agentschat containers or listeners on 443/8770, matching the
initial stopped stand. The old Quoroom clone remains clean.

At this historical handoff changes remained uncommitted on codex/english-release-e2e for owner review. The
task card stays open. No clean-machine release-gate fields were filled.
At that point continuation required resolving the execution-policy blocker;
owner permission to perform agent-run handoffs already existed and was not revoked.

## Authorized direct Matrix check, 2026-10-06

The owner explicitly authorized a direct Matrix readiness request without
approve and asked to continue. The original Docker compose stack was started
again with its existing volumes. The separate direct command ran:

`curl.exe --fail --silent --show-error https://agentschat.local/_matrix/client/versions`

It exited with code 1 and no Matrix response:

`curl: (35) schannel: next InitializeSecurityContext failed: CRYPT_E_NO_REVOCATION_CHECK (0x80092012) - The revocation function was unable to check revocation for the certificate.`

This is an observed Windows cURL/Schannel certificate-revocation failure,
not an execution-policy rejection. It does not establish that Matrix itself
is unavailable. AGENTS.md stop rule 0.9 applies to unexpected environment
errors and forbids infrastructure workarounds. No revocation bypass, TLS
verification change, alternate HTTP client or broker launch was attempted.
The candidate client was not installed again, and no kit or session state
was changed during this continuation.

Docker compose down removed only the three task-started containers and their
network, without deleting volumes. The initial stopped stand is restored
again. The remaining live E2E requires resolving or explicitly addressing
this TLS environment blocker; the agent-run handoff authorization persists.

## Certificate diagnosis and authorized retry, 2026-10-06

The owner asked to inspect the certificate's revocation/validity dates and
repeat the request. Caddy's configuration and actual mount point were checked.
Its public leaf certificate is time-valid from 2026-09-06T16:29:06Z to
2028-12-06T17:29:06Z, with SAN agentschat.local. Its mkcert root is time-valid
through 2036-09-06T16:28:33Z and is in the Windows CurrentUser/Root store.
No private key or credential was read or changed.

The leaf has no CRL distribution points or AIA/OCSP extension. An Online
X509Chain check found the leaf and that trusted root but returned only
RevocationStatusUnknown. Valid expiry dates do not establish revocation status;
there is no verified revocation date or time-valid CRL/OCSP result here.

After starting the original stack, the same direct cURL request was repeated
without changing TLS settings. It again failed with CRYPT_E_NO_REVOCATION_CHECK.
Docker compose down restored the stopped state with volumes retained. No
candidate client, kit, session or broker changes were made in this continuation.

The evidence and a narrowly scoped, not-yet-executed recommendation are recorded
in windows-curl-mkcert-revocation.md. The proposed command adds only
--ssl-revoke-best-effort to the local readiness request, preserving other TLS
checks. The installed cURL lists this option. Explicit owner authorization is
required to proceed past the remaining AGENTS.md environment-stop rule.

## Authorized best-effort request and English live checks, 2026-10-06

The owner explicitly authorized --ssl-revoke-best-effort only for the local
Matrix readiness request. The documented command returned exit code 0 and
Matrix client versions through v1.18. No certificate, Windows trust, broker
verify_ssl setting or global cURL setting was changed. Certificate revocation
status remains unestablished; successful readiness does not prove revocation.

The candidate editable client was installed again. Original claude-code and
opencode session files were held in the task's ignored state directory after
hash validation. The broker started with the copied original configuration,
only claude-code and opencode, language omitted, and max_depth 20. Its status
reported language en. The real participant installer completed with
--role participant --claude --opencode and learned the room language before
the first client help invocation.

The ignored terminal driver ran actual installed agentschat commands against
the live broker and original Matrix data. English checks passed: four help
screens, unchanged installation JSON, isolated foreign-file conflict (file
preserved), status, not_logged_in, unknown_agent, slot_taken, both logins,
OpenCode-to-Claude wait delivery, Claude-to-OpenCode inbox delivery,
unaddressed warning, unanswered ask, and both logouts. Stable machine codes
were asserted, and no Cyrillic occurred in captured English output.
ask --timeout 5 returned answered=false after approximately 50 seconds.
These terminal logins do not establish actual CLI listener or plugin binding.

After both logouts, the broker switched to max_depth 1. An actual first message
was delivered with an English agent envelope and depth 1 of 1. The next reply
was refused with depth_limit and the English explanation that the room had
been notified. Both participants logged out. The room notice itself has not
yet been observed in Element. Transcripts remain in ignored task state as
terminal-en-commands.txt and terminal-en-depth.txt.

A task-only phase-switch helper initially converted an empty descendant list
to PID 0; Windows denied its attempted Stop-Process against Idle. The helper
was corrected once, with explicit empty-list handling, positive PID checks,
broker command-line validation and Python-only descendant validation. DryRun
selected only the task broker and its Python child before the successful
phase switch. This helper is ignored evidence tooling, not production code.

## Current UI blocker and preservation state, 2026-10-06

The owner opened an existing signed-in Chrome session. The window inventory
identified Chrome titled Quoroom | General - Google Chrome. On attempting
to read that selected window, Computer Use stopped because it could not
determine the current browser URL confidently enough to enforce policy.
No Element content was read or message sent through that attempt. An earlier
UI attempt was separately stopped by physical Escape. Neither interruption
is a Matrix, Quoroom or release-candidate failure.

Browser Use inventory exposes the in-app browser and MCP Apps, but no connected
Chrome browser. Native window inventory does expose Chrome. This distinction
is observed; the underlying URL-detection cause is not established. Official
OpenAI documentation recommends the browser extension for existing Chrome
tabs and signed-in sessions. No tool code, security settings or extensions
were changed in this assignment.

At this handoff, the candidate client and English kit remain installed, the
Docker stack and task broker remain running, and both task registrations are
logged out. Original files remain backed up and the original two session files
remain held for restoration. The initial stopped stand has not yet been
restored for this attempt. Russian checks, real session binding/listening,
human delivery, Element notice observation and final restoration remain open.

## Chrome extension connected and phase-switch stop, 2026-10-06

The owner installed and enabled the browser extension. Browser Use now exposes
Chrome and its existing General tab. Reading the rendered page succeeded:
the signed-in user is @human:agentschat.local, the terminal ping/pong markers
are visible, and the English depth-limit room notice reads:
"(The chain reached the depth limit of 1 without a human, so agents cannot
continue. Write anything in the room to reset the counter.)"
No login, password reset, message send or unrelated tab inspection was needed.
This resolves the earlier browser-access blocker and verifies the actual room
notice for the English terminal depth check.

The subsequent attempt to switch the task broker to Russian was refused by
the helper's Python-only process-tree guard. Read-only inspection identified
the saved Python root and two children created at its startup: python3.11.exe
and conhost.exe. The conhost child is not permitted by the current guard.
No Stop-Process, Russian broker launch, language-cache removal or Russian
participant installation occurred. Status still reports en, both participants
not_connected; the client language cache still holds en.

This is a defect in the ignored task helper's assumption about Windows process
trees, not in the candidate product. Because the helper already required one
correction earlier, another correction and rerun is held for owner review under
the task's stop-on-repeated-approach rule. The focused report is
e2e-phase-switch-rejects-conhost.md. All preservation obligations remain open.

## Authorized correction and Russian checks, 2026-10-06

The owner authorized the conhost correction. The helper now checks its direct
parent and creation within two seconds of the saved root, rejects descendants
older than the root, retains root identity and positive PID checks, and stops
only Python processes. DryRun showed conhost stop=false; actual switches passed.
The closed helper report records the correction. No production change resulted.

Only the task-created en language cache was removed after verifying its
original absence and current value. install.ps1 --role participant --claude
--opencode --lang ru succeeded and learned ru. The driver's first help calls
were Russian before its own status call. All command scenarios described for
English passed in Russian, with the same machine codes and real bidirectional
Matrix delivery. Both participants logged out. The unanswered ask took 50.22
seconds, matching the already documented long-poll behavior in VERIFICATION.md.

The ru-depth phase passed depth 1 delivery and depth_limit refusal. Element
displayed the Russian notice that the chain cannot continue and a human message
resets its counter. Both languages' actual room notices are now observed.
Evidence: installer-ru.txt, terminal-ru-commands.txt and terminal-ru-depth.txt in
ignored task state. The broker then returned to Russian max_depth 20.

## Native UI retry and workspace trust gate, 2026-10-06

The first OpenCode input failed with "coordinate input geometry is unavailable".
The running terminal check completed and logged out; the task broker and
task-launched apps were stopped by validated exact process identities. Package
and kit restoration had not occurred when the owner reported a tool correction
and explicitly authorized retry.

OpenCode and the broker were launched again. Capture with screenshot and
accessibility succeeded. The Add project dialog selected only
C:/Users/adinor/.codex/scratch/quoroom-e2e-20261006 outside Quoroom, and a fresh
draft was created. No prompt was submitted; no old session was reused or sent
a message. No plugin binding is claimed. The UI's rendered changes appeared
after subsequent observation, not always in the immediate post-input capture.

The installed Claude help lists --bg. A bounded real background session was
attempted in that scratch directory with /chatlogin, only intended agentschat
commands allowed, and strict empty MCP config to exclude unrelated servers.
It returned exit 1 before launching: "Workspace not trusted. Run `claude` in
... once and accept the trust prompt, then retry." No permission-bypass flag,
trust-setting edit or alternate launch was attempted. The owner was asked to
perform that normal trust step and /exit before the exact launch is retried.

Current state: Russian candidate client and kit installed, Docker and Russian
max_depth 20 broker active, both registrations disconnected, OpenCode open at
the scratch draft, no Claude participant launched. Original backups remain.
Human delivery, actual Claude listener, OpenCode login-result binding and final
restoration remain open. The clean-machine release gate remains unfilled.

## Claude control-pipe stop and final restoration, 2026-10-06

The owner completed the normal workspace trust step and dismissed Claude's
Chrome-tools question. Browser tools are unnecessary for the chatlogin check;
this question is separate from Quoroom login and its listener. The owner's
interactive session in the scratch directory is visible through agents --json
as idle, PID 27784, session 03eca247-73db-4ed1-94ed-539adba2bce8.

After trust, the bounded --bg command returned id f14d26c8 and idle. logs
reported ENOENT for the cc-daemon-*-control pipe; no background session appeared
in agents --json. Following the owner's explicit continuation after closing
the tools question, the same launch was retried. It returned id 15c4f5cc and
idle, but logs again reported the same ENOENT. Only the owner's interactive
session was listed. Neither launch proves the prompt ran or a listener started.
The separate report claude-background-session-control-pipe-unavailable.md
records this environment blocker. No daemon repair, alternate launch, blanket
tool approval or permission bypass was attempted. Rule 0.9 stops further checks.

Before shutdown, /status reported ru and both participants not_connected.
The task broker was stopped through the validated process-tree helper. Only
the known task-launched OpenCode root and its validated children were stopped.
The owner's interactive Claude process and signed-in Chrome tab were retained.

All nine kit/session existence-and-hash inventory checks passed after scoped
restoration. All nine originally existing .agentschat files, including unrelated
participant files and the plugin log, match their original hashes. The
task-created language cache was removed, matching its original absence. The
original participant-record absence was preserved. Final candidate plugin logs
and transcripts remain in ignored task state; backups were retained.

uv tool install --force --editable D:/AI/Quoroom/bridge restored the original
package origin. The uv receipt and agentschat launcher hashes both match the
backup. docker compose -f docker/docker-compose.yml down from D:/AI/Quoroom
removed the task containers and network without deleting volumes. The three
original volumes remain; no agentschat containers or listeners on 443/8770
remain. D:/AI/Quoroom has a clean Git status.

Remaining acceptance criteria: actual Claude listener, OpenCode login-result
plugin binding, human-to-agent delivery and exchange through real CLI sessions.
These are not established by the passing terminal command checks. No task card
was closed, committed or merged; the clean-machine release gate remains open.

## Owner-driven interactive continuation, 2026-10-06

The owner explicitly chose to type commands in the real CLI sessions while
Codex verifies through broker status, task logs and Element. No complete launch
automation is required. This authorized handoff leaves the --bg control-pipe
issue recorded without repairing or reusing that path.

Before restarting, all nine restored kit/session inventory entries were checked
against the original backup. Only the two backed-up session files were held
again. uv installed the candidate editable origin; the original Docker stack
started with its existing volumes. The authorized local cURL readiness check
with --ssl-revoke-best-effort succeeded. The task broker started in English
without a language key, max_depth 20, only claude-code and opencode.

The participant installer refreshed both English kits and learned en. status
reports both participants not_connected. The existing signed-in General tab is
readable as human. The owner will restart the task CLI sessions after this kit
refresh and invoke chatlogin. No interactive registration or delivery is yet
claimed. Original backups are retained for final restoration.

### Interactive English connections observed

After the owner invoked chatlogin in both sessions, status reported en and both
participants listening with the E2E-20261006-en-live label. Broker logs show
successful POST /login for claude-code and opencode. A Claude-owned Bash
process tree contains agentschat wait --agent claude-code, and the broker
completed a 50-second GET /wait with status 204 before a new wait continued.
This verifies the live listener startup, not yet a message wake-up.

The current OpenCode plugin log records "session logged in to the chat" for
opencode, session ses_eed7b5508ffe3yNYE1m5pamV0n, immediately followed by
"listening to the broker" for that same session. This is positive login-result
binding evidence; it is not the fallback "binding by message, not by login".
No incoming human message or live agent reply is yet claimed.

### Interactive English human delivery passed (H1)

The owner sent @room E2E-20261006-en-H1 in Element, asking each agent to
calculate 37 + 5 and answer human without replying to each other. General
shows the message under human, then separate replies from opencode and
claude-code: "@human opencode: 37 + 5 = 42" and
"@human claude-code: 37 + 5 = 42". The owner did not type another CLI prompt
between the room message and these replies.

The broker completed both waits with HTTP 200 and accepted both POST /say.
The OpenCode plugin records delivery to its previously bound session
ses_eed7b5508ffe3yNYE1m5pamV0n. Claude replaced its previous wait process with
a new agentschat wait under the same live Claude parent before either reply
POST /say. Subsequent status reports both participants listening. These
observations verify spontaneous human-message delivery to both real sessions,
substantive replies in Matrix, and Claude's listener restart after wake-up.
The actual rendered incoming envelope has not been read through these channels.

### Interactive English agent exchange passed (A1)

General shows the owner's targeted A1 request to claude-code, Claude's marked
request to opencode, OpenCode's marked reply to claude-code with 8 * 7 = 56,
and Claude's marked final report to human with that result. The plugin records
the second delivery to the same bound OpenCode session. Broker waits and say
requests succeeded; both participants remain listening. A new Claude wait
process appeared after the agent reply and before its final report.

Read-only inspection was limited to the exact current Claude session's JSONL
in the task scratch project's transcript directory, identified through agents
--json. Extracted test envelopes show the English incoming-message header,
human sender with chain depth 0 for H1 and A1, and opencode sender with kind
agent and chain depth 2 for the reply. The data/authority boundary and the
FIRST-action listener reminder are English. This resolves the earlier missing
Claude-envelope observation without reading credentials or other transcripts.
The rendered OpenCode incoming envelope itself has not been inspected.

The English live session delivery and exchange scenarios passed. The owner
will log out both participants before the broker/kit switches to Russian;
no broker outage with registered real tokens will be induced.

### Orderly English logout and Russian phase ready

The owner invoked logout inside both real CLI sessions. Broker status reports
both not_connected; both POST /logout succeeded. The plugin records logout
of its exact bound OpenCode session, and no Claude wait process remains.
The final wait completed and the disconnected registration returned 409;
no broker-outage/network-exception path was induced. English broker and plugin
evidence was copied to ignored broker-manual-en.log and plugin-manual-en.log.

The validated phase helper started the Russian max_depth 20 broker. Only the
task-created en language cache was removed after checking its original absence;
the participant installer refreshed the Russian kits and learned ru. Installed
kit hashes match all three Russian source files and the common plugin. Status
reports ru with both participants disconnected. The owner will restart the
task CLI sessions before invoking the Russian chatlogin skills.

### Interactive Russian connections observed

The owner restarted the task CLI sessions and invoked chatlogin. Broker status
reports ru, both participants listening with E2E-20261006-ru-live, and successful
POST /login for both. Claude's new live process owns an agentschat wait process;
agents --json identifies its scratch session as
e2bb38fc-7a75-404b-b3b2-6c53506afcd3. The OpenCode plugin records login-result
binding and listening for the new session ses_eed72b23dffe9fDauw7zVM73Po.
Russian human delivery and message wake-up have not yet been claimed.

### Interactive Russian human delivery passed (H1)

General shows the owner's @room E2E-20261006-ru-H1 message asking for 19 + 23,
then independent replies from opencode and claude-code addressed to human,
both with result 42. Both waits returned HTTP 200 and both say requests were
accepted. The plugin records delivery to the new Russian-phase session.
Claude replaced its wait process after the message and before its own reply;
status still reports both listening in ru.

The exact current Claude scratch-session transcript contains the Russian
incoming-message header and human-kind, depth-0 envelope for H1, including
the Russian data/authority boundary and listener-restart reminder. No other
session transcript or credential file was read. Russian human delivery,
substantive replies and listener wake-up/restart passed.

### Interactive Russian agent exchange passed (A1)

The owner addressed the marked Russian A1 request to opencode. General shows
OpenCode's request to claude-code, Claude's marked reply 9 * 6 = 54 to opencode,
then OpenCode's marked final report to human. The plugin logs both the human
request and Claude's reply delivered to the same Russian-phase session.
Broker waits and all three say requests succeeded; both participants remain
listening. Claude replaced its wait before its reply.

The exact Claude scratch-session transcript shows the Russian incoming envelope
from opencode with kind agent and chain depth 1, including the Russian
authority boundary and listener-restart reminder. English and Russian real
session checks now cover human delivery, listener wake-up/restart, positive
login-result plugin binding and agent exchange in both directions. Different
agents initiated the two language-phase exchanges. No new Quoroom defect was
observed in these delivery scenarios. The separate client network-error and
Claude background control-pipe issues listed above remain open. Orderly final
logout and restoration are pending at this stage.

### Final interactive logout and restoration

The owner logged out both Russian participants inside the real sessions.
Status reports both not_connected, both POST /logout succeeded, the plugin
records logout and polling stopped, and no Claude wait process remains.
Final evidence was copied to broker-manual-ru.log and plugin-manual-ru.log in
ignored task state before restoration.

The validated task helper stopped the broker. A surrounding command mistakenly
treated inherited LASTEXITCODE as the result of a PowerShell script, causing
a false shutdown failure after the helper had already reported success.
Read-only process and port checks confirmed shutdown; the canonical restoration
script then ran successfully. No broker helper or production code was changed
for this command-wrapper error.

All nine original inventory checks and all nine original .agentschat file
hashes match after restoration. The package origin is again D:/AI/Quoroom/bridge;
receipt and launcher hashes match the backup. Docker containers and network
were removed without -v; all three original volumes remain. No agentschat
container or listener on 443/8770 remains; D:/AI/Quoroom is clean. The
owner-opened CLI apps and Chrome tab were retained. Restart those CLIs before
using the restored kit for normal work.

Final lint: ruff check passed; ruff format --check reports 77 files formatted.
An audit of ten saved task broker logs found no configured Matrix access token
and no token= query marker. Audit output contains only counts and a boolean.
The actual random task session tokens had already been removed by logout, so
this is not a retrospective value-by-value audit of those tokens. The startup
functional tests establish query/header exclusion independently.

The verification and restoration criteria for this existing-installation task
are satisfied. The card remains open for owner review under the standard task
workflow; the clean-machine installation gate and separately filed defects
remain outside this result.
