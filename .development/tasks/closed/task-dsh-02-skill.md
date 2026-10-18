# Task: DSH chatlogin skill (ru + en)

Status: Completed
Story: story-dsh-participant.md
Branch: feat/dsh-participant

## Summary

The `chatlogin` skill for DeepSeek Harness, in both languages, teaching the
model how to act in the room once a session is joined: send with `say`, ask
with `ask`, inspect with `status` and `inbox`, all through the shell tool
(`pwsh`). The skill states the boundaries (never run login/logout itself,
print broker-rendered envelopes verbatim, never touch `~/.agentschat`
directly, never rephrase the room language).

The DSH skill lives in the kit tree (`bridge/sessionchat/kit/{ru,en}/dsh/`)
for content-completeness. It is NOT installed by `agentschat install` (the
kit install path); instead, the participant installer's `DshStep`
(`bridge/sessionchat/installer/participant.py`) copies the skill into the
DSH skills root and installs the plugin into the named profile. `dsh` is
deliberately not in `kit.CLIS` because the DSH participant is installed by
the participant installer, not by `agentschat install`.

## Boundary

- `bridge/sessionchat/kit/ru/dsh/skills/chatlogin/SKILL.md`
- `bridge/sessionchat/kit/en/dsh/skills/chatlogin/SKILL.md`
- `bridge/tests/test_kit.py` (kit-completeness tests updated to handle dsh
  explicitly without adding it to `kit.CLIS`)
- The shared parts (say, ask, status, inbox, boundaries) must agree
  functionally with the claude and opencode skill copies.

## Acceptance criteria

- `unittest discover` from `bridge/` passes, including the kit tests covering
  the dsh skill files (content completeness).
- The two language copies are functionally consistent with the existing skill
  copies.
