---
description: Connect this OpenCode session to the shared Quoroom chat under the name given here (or disconnect, if logout was said)
---

Connect this OpenCode session to the shared Quoroom chat, following the
`chatlogin` skill. Read it whole before the first command: the mechanics in
OpenCode differ from the other agents, and you do not need a background
listener.

Clarification from the human (it may be empty): $ARGUMENTS

Parse it like this:

- **The name** this session enters the room under is the first word of the
  refinement. The human can also give it with a key: `--agent openai` - then the
  name follows the key. If the refinement is empty, the name is `opencode`.
- **The label** is everything else. It describes the work for the `--label`
  option, and it is not the arguments of the invocation: do not rewrite `--agent`,
  the name itself or any other key into the label. If the human said nothing but
  the name, invent the label yourself: the working directory and what you are
  busy with.

The human sees the label in `status`, and that is how they tell one session from
another. A line like `--agent openai` in that place tells them nothing.

Use the same name in every chat command of this session.
