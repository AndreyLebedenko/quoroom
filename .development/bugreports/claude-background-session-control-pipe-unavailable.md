# Claude background-session launch cannot be verified through its control pipe

**Detected:** 2026-10-06.
**Candidate commit:** 9744e12c0e858ad23a40b14ffa6ca57d2fb67d07.
**Status:** Open; installed CLI environment, outside the Quoroom code change.

## Symptoms

Claude Code 2.1.288 initially refused --bg in the task scratch directory because
it was untrusted. The owner ran the normal trust step there and authorized
continuation. Retrying the exact bounded launch returned exit 0 with
"backgrounded", id f14d26c8 and an idle state. This output is not proof that
the supplied /chatlogin prompt ran or that any listener started.

The follow-up supported `claude logs f14d26c8` printed:
"Couldn't read logs for f14d26c8 - connect ENOENT \\.\pipe\cc-daemon-*-control"
(punctuation normalized). `claude agents --json --cwd` for that scratch
directory returned []. The broker has no connected task participants.

## Suspected cause

The background CLI's control endpoint is absent or undiscoverable in this
execution environment. The observed output does not establish why. No daemon
repair, alternate launch, trust-setting edit or permission bypass was attempted.

## Temporary decision

Stop under AGENTS.md rule 0.9 and preserve evidence. Restore the original
installation and stopped stand. Do not claim real listener behavior or plugin
binding from successful terminal client checks. A separate native OpenCode
draft exists only in the task scratch project; no prompt was submitted.

## Later boundary

Resolve the CLI control endpoint before another automated --bg attempt, or
have the owner run the real sessions interactively as a separate explicit
handoff. Quoroom credentials, protocol, server volumes and unrelated project
settings remain outside the repair. The existing-installation run cannot
close the clean-machine release gate.

## Owner-authorized retry and preservation, 2026-10-06

The owner dismissed Claude's Chrome-tools question and authorized continuation.
The normal interactive scratch session now appears in agents --json as idle,
PID 27784. Repeating the same bounded --bg launch returned id 15c4f5cc and idle.
logs again reported ENOENT for the same control-pipe pattern; the background
session did not appear in the list. The earlier empty list is historical; the
current list contains only the owner's interactive session. Dismissing the
browser-tools question did not resolve the observed background control failure.

The original package, kit and client files were restored and hash-checked;
the task broker and task-launched apps stopped, Docker taken down preserving
all original volumes. The owner's interactive Claude session was retained.
No actual chatlogin invocation or participant registration is claimed.
