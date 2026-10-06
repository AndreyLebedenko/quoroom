# Broker access log exposes the session token in wait and inbox URLs

**Detected:** 2026-10-06.
**Candidate commit:** 9744e12, story/english-release.
**Status:** Fixed on codex/english-release-e2e; implementation and tests committed with this report, awaiting owner review.

## Symptoms and evidence

The automated unittest run prints aiohttp access-log records for GET /wait and
GET /inbox whose request URLs include the token query parameter unredacted.
The observed requests are to fake brokers on ephemeral localhost ports and use
test tokens. At this initial detection stage no real broker or real session
had been started for the assignment.

Sanitized form of an observed record:

`GET /wait?agent=claude-code&token=<test-token> HTTP/1.1`

The broker entry point configures root logging at INFO, then creates an
aiohttp AppRunner without an access-log override. Its wait endpoint authenticates
with the token query parameter. The actual live path has not been executed:
the expected disclosure of a real session token is inferred from the source and
the same observed request logging on test brokers.

## Suspected cause

The default aiohttp access logger records the request target, including query
parameters. Broker.main enables that logger through root INFO configuration.
The session token is therefore included when a token holder polls /wait or
reads /inbox. The plugin passes the token in those URLs as well.

## Initial temporary decision

Stop before starting the live broker, installing the candidate kit, changing
the participant package, or sending messages. AGENTS.md's locality contract
forbids logging a token; the owner's override covers human-run handoffs only.
Disabling logging only in an ad-hoc test launcher would change the tested
runtime and bypass the default behavior, so that was not done.

The automated suite was interrupted during launch-script tests after this
finding. No green result is claimed and the remaining project checks were not
started. Only its identified process tree was stopped. Test fixture directories
were not manually removed. The old installation and server data are unchanged.

## Original recommendation and boundaries

Resolve the token exposure in a separately authorized focused prerequisite,
covering the broker's actual startup logging and both authenticated GET paths.
Assert that session tokens never appear in emitted logs while retaining useful
English diagnostic records. Inspect other token-bearing log paths in that
prerequisite. Do not change delivery, language or Matrix access-token ownership.

After the prerequisite is reviewed, select and record a new candidate commit
and run the required checks before restarting live verification. Cleaning up
historical logs or rotating existing credentials is outside this report's
proposed implementation boundary and requires an explicit owner decision.

## Authorized resolution, 2026-10-06

The owner authorized a focused fix and continuation of the live checks.
Broker.run now selects a custom aiohttp access logger through access_log_class.
It records method, path, status and duration, excluding query parameters,
request headers and response bodies. A real-startup HTTP functional test first
reproduced token disclosure on /wait and /inbox, including refused requests,
then passed with this change. Three unit tests cover the retained diagnostics
and secret-bearing query parameters, headers and response bodies.

The complete unittest suite passed: 1767 tests, one skipped. The 28 plugin
tests, ruff check and ruff format --check passed. No dependency or protocol
change was required. The fixed report is preserved under bugreports/closed/.
The owner subsequently requested a durable commit identifying the verified
runtime. The implementation, its tests and this report are committed together;
the task card remains open for review.

The first live attempt was subsequently stopped by an execution-policy rejection
before the candidate broker could be launched. The old client and stopped
Docker state were restored. This blocker is independent of the logger fix;
see task-english-release-e2e-existing-install.md in .development/reports/.

Later owner-authorized attempts completed the existing-installation English
and Russian checks, including interactive human delivery and bidirectional
agent exchange. The old installation was restored and hash-checked. The
production files committed here are byte-identical to those used for the full
automated suite and live checks. The report and open task card now reside in
D:/AI/AgentsChat/.development/; code and ignored evidence remain in this worktree.
