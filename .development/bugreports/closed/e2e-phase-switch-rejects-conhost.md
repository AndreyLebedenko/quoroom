# Task phase-switch helper rejects the broker's Windows console host

**Detected:** 2026-10-06.
**Candidate commit:** 9744e12c0e858ad23a40b14ffa6ca57d2fb67d07.
**Status:** Fixed in ignored task tooling after owner authorization; no production defect established.

## Symptoms

The ignored broker_phase.ps1 helper refuses the transition from en-depth to ru
with "The broker tree contains an unexpected process". The guard runs before
Stop-Process or a new broker launch. Language-cache deletion and installation
later in the calling command did not run.

## Verified cause

Read-only Win32_Process inspection of the saved task broker PID found:

- python.exe root 24648, created at 17:44:58.738 local time.
- conhost.exe child 33240, parent 24648, created at 17:44:58.748.
- python3.11.exe child 18660, parent 24648, created at 17:44:58.797.

The helper assumes all descendants are Python processes. This observed task
launch also created a console host. The guard rejected that process as designed.
The broker remains reachable, language en, both participants not_connected.

## Temporary decision

Stop and preserve the current runtime and backups. The helper already needed
an earlier correction for an empty descendant list becoming PID 0; do not keep
editing and retrying that helper without owner review under AGENTS.md rule 0.7.
No broad process termination, alternate shell or broker-start workaround was
attempted. This report concerns only the task helper, not a product change.

## Recommendation and boundary

After owner review, account explicitly for the observed task-created console
host when validating the tree, retaining saved-root command-line validation,
positive PID checks and a DryRun review before termination. Verify startup
times and parentage; do not simply accept arbitrary descendants or kill all
processes with a shared name. Changes stay inside ignored E2E tooling. Final
restoration of the original package, kit, sessions and stopped Docker state
remains required.

## Authorized resolution

The owner authorized the correction. The helper accepts conhost.exe only as
a direct child created within two seconds of the saved broker root. All
descendants must be no older than the root. Root command-line validation and
positive PID checks remain. Only Python processes enter the termination list;
conhost exits with its parent. DryRun prints an explicit stop flag per process.

DryRun selected only the root and Python child, with conhost stop=false. Actual
switches to ru, ru-depth and ru succeeded, as did orderly task shutdown. A
StopOnly option enables cleanup without launching another phase. No production
code or global setting changed.
