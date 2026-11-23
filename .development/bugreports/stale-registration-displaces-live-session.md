# A 49-day-old registration displaced a live session

**Detected:** 2026-11-23, commit b8174eb (branch feat/tray-launcher).
**Status:** Open. Cause not established.

## Symptoms

- At 13:32 the Quoroom lead session logged in as `claude-code` (label
  "Quoroom: tray launcher, lead") and listened normally; opencode reviewed
  through the room until about 14:00.
- During the manual check of task-tray-01 the owner stopped and started
  Docker Desktop and the stand; the broker was unreachable for a while.
- Afterwards `agentschat wait --agent claude-code` exited with "The session
  is not connected or the token is wrong", and `agentschat status` showed:
  `claude-code  NOT LISTENING  Поиск работы: CV и отклики (connected
  14:15:47, quiet for 4239047s)`.
  The label belongs to a Claude Code session in another project; opencode
  was shown as not connected.
- `logout --agent claude-code --force` plus a fresh login restored the slot.
  The store then held the new row (registered 2026-11-23 14:48:20) and a
  `glm` row registered 2026-10-05 14:30:20.

## What the numbers say

The "strange" quiet value is arithmetically consistent: 4239047 s is
49 d 1 h 30 m. Counting back from the status call (about 14:46 local) gives
2026-10-05, and the 1-hour difference from the shown 14:15:47 is the summer
to winter time change between the two dates. So the registration shown was
created on 2026-10-05, not today. `status` prints only the time of day
(`%H:%M:%S`) of `registered_at`, which made a 49-day-old registration read
as fresh.

## Suspected current cause

Two separate problems, the second unexplained:

1. Display: `_session_status` formats `registered_at` without a date, so an
   old registration looks current. Low severity, misleading.
2. Resurrection: a registration from 2026-10-05 came back and took the
   `claude-code` slot over a live registration from the same day. The
   `registrations` table has `agent` as PRIMARY KEY, and the 13:32 login
   should have replaced any older row, so a plain restore from this store
   does not explain it. Hypotheses, none checked: a second broker or a
   broker started with another `bridge/state` (the stand restart reported
   "already running (PID 11932)"); a `--reconnect` from the other project's
   session presenting a token the broker still accepted through
   `_restore_one`; registrations in a store that never expire (the
   October `glm` row is still there).

## Temporary decision

Released the slot by hand (`logout --force`, owner's decision) and logged
in again; no code changed. The tray work continues: it does not touch
registration logic. Chosen over investigating now because the cause needs
the broker log of the time window and the other session's token file, and
pulling that into the tray story would widen its scope.

## Future considerations and boundaries

- First collect evidence: `bridge/broker.log` around the stand restart
  (login/reconnect/restore lines for `claude-code`), the process list for
  more than one `sessionchat.broker`, and which `~/.agentschat` token file
  the other project's session used.
- Decide whether stored registrations need an age limit, and whether
  `_restore_one` may ever bring back a registration older than the current
  holder's.
- Show the date in `status` when `registered_at` is not today.
- Not in scope: the token-in-output defect
  (client-network-error-exposes-session-token.md).

## Addendum 2026-11-23: an escaped label in the stored registration

Seen in the tray menu at commit aab886d. The stored `glm` registration
(registered 2026-10-05 14:30:20, from an OpenCode session in
`D:\AI\ReReason`) has a label that holds literal backslash escapes, for
example `OpenCode, \u0440\u0430...` where the text meant Cyrillic. The
registrations table stores it that way, and `/status`, `agentschat status`
and the tray all show it as stored. The tray is right not to decode it: it
would be guessing at broken data. Unknown: whether today's login path can
still store such a label, or whether the 2026-10-05 client sent it already
escaped. Check at `login` whether a label containing `\uXXXX` should be
refused or kept as is.
