# Integration with Claude Code / Codex / OpenCode

> **Cancelled.** Describes how the first-generation bridge called the CLIs in
> headless mode. The broker does not call a CLI at all: sessions are opened by a
> human. See [SESSION_BRIDGE.md](SESSION_BRIDGE.md). The "Contracts" section at
> the end of this document describes the current client and is not cancelled.

Russian version: [AGENTS_INTEGRATION.md](AGENTS_INTEGRATION.md).


The bridge does not "understand" any of the three tools - it just launches the
CLI in headless/non-interactive mode with the message text as the prompt, waits
for the process to finish and publishes the result back to Matrix.
This document records what exactly is confirmed by the official documentation
at the time of writing, and what you need to check by hand before trusting the
integration with real tasks.

## Claude Code - confirmed by the official documentation

```
claude -p "{prompt}" --output-format json --permission-mode auto --permission-prompts none
```

- `-p/--print` - headless mode.
- `--bare` is not used in the working configuration. This flag does not load
  hooks/skills/MCP/CLAUDE.md from `~/.claude` and the current folder; startup is
  faster and the same on any machine. Because of this, **OAuth credentials are not
  read in bare mode** - the machine where the bridge runs must have the
  `ANTHROPIC_API_KEY` environment variable (see the documentation on `--bare`).
  If you would rather have Claude Code use your ordinary subscription/login,
  remove `--bare` from the command in `config.yaml` - then your usual
  hooks/MCP/CLAUDE.md from the home folder are loaded, which can be both a plus
  and a source of surprises (the bridge will implicitly inherit everything
  configured in `~/.claude`).
- `--output-format json` - the final text is in the `result` field of the JSON
  object printed last to stdout. This is confirmed verbatim by the official
  documentation.
- `--permission-mode auto --permission-prompts none` - the agent works without
  asking a human (nobody confirms permissions in the background). This is a
  deliberate compromise for an autonomous bot - check that the agent's `workdir`
  (`workspace/claude-code`) contains nothing you would hate to break.

## Codex CLI - headless mode confirmed, JSON schema not

```
codex exec --sandbox workspace-write --skip-git-repo-check --cd "{workdir}" --output-last-message "{tmp}" "{prompt}"
```

- `codex exec "prompt"` - headless mode, confirmed.
- `--sandbox workspace-write` restricts writing to the working directory and the
  permitted temporary directories. `--skip-git-repo-check` is needed because the
  stand's working directories are not Git repositories. Verified with CLI 0.153.4.
- `--output-last-message <file>` - "Write agent's final message to file",
  confirmed verbatim by the official documentation. This is what the bridge uses
  to pick up the final answer (`result_mode: file` in the config).
- The `--json` flag (newline-delimited JSON events) also exists and is confirmed
  by name/purpose, **but the exact event schema (in which field the final answer
  text lies) was not verified live by us** - different secondary sources name
  different fields. So by default the bridge uses `--output-last-message`, not
  parsing of `--json`.

**Check before real use:** run
`codex exec --help` and `codex exec --sandbox workspace-write --skip-git-repo-check --cd . --output-last-message out.txt "напиши файл test.txt с текстом hi"`
yourself, to make sure that the Codex version installed on the machine
understands exactly these flags (the CLI has short aliases and versions differ).
(The prompt in the second command is Russian: "write a file test.txt with the text hi".)

## OpenCode CLI - headless mode confirmed, JSON schema not

```
opencode run --dir "{workdir}" "{prompt}"
```

- `opencode run "prompt"` - headless mode, confirmed by the official
  documentation.
- `--dir` - the working directory, confirmed.
- The `--format json` flag exists ("raw JSON events"), but, as with Codex, **the
  exact schema (the name of the field with the final text) was not verified live
  by us** - so by default the bridge takes the plain text stdout
  (`result_mode: raw_stdout`) and just strips the ANSI color codes.
- OpenCode also supports a persistent server (`opencode serve` +
  `opencode run --attach http://localhost:4096 "prompt"`), which saves cold start
  time on frequent messages - not enabled in v1 (`command` in the config can be
  changed to the `--attach` variant if, after testing, it makes a noticeable
  difference).

**Check before real use:** run `opencode run --format json "тест"`
yourself and look at the real structure of the output, if you decide to switch
`result_mode` to `json_field` for more reliable and richer parsing.
(The prompt is Russian: "test".)

## General logic of the bridge (`bridge/matrix_bridge.py`)

1. `mention_only`: a message is processed only if the text mentions the agent's
   localpart (`@claude-code`) or display name, or `m.mentions.user_ids` contains
   the agent's Matrix ID. Configured aliases and `@room` with
   `respond_to_room_mention: true` are also supported.
2. `max_replies_per_minute`: if exceeded, the message is simply ignored (the CLI
   is not launched), and at most one notice about the limit is sent to the room
   every 5 minutes, so that there is no silence without explanation.
3. `timeout_seconds`: if the CLI process did not finish in that time, it is
   killed and a timeout message goes to the room.
4. Each message is a **separate one-shot CLI call**, without
   `--continue`/`--resume`/`--session`. The agent does not see the room history
   beyond the text of the incoming message itself. This is the simplest and most
   predictable start; adding memory between messages is the next step (Claude
   Code and OpenCode have documented session-continuation flags; for Codex, a
   continuation mechanism through `codex exec` was not verified by us and needs a
   separate study of `codex exec --help`).

## Debugging

- Look at the PowerShell window of the corresponding bridge - there `logging` at
  the INFO level by default (`--verbose` for DEBUG) prints the exact command the
  bridge launched and the exit code of the process.
- If the bot does not answer at all, check that: the room matches (`room_id` in
  `config.yaml`), the bot is in the room (Join, not just Invite), the message
  text really contains its localpart/name (if `mention_only: true`).
- If the bot answers "(ошибка запуска ...)" (a launch error; the bridge's own
  message, in Russian) - the message contains the stderr tail of the corresponding
  CLI, which usually points to a wrong flag for the installed CLI version (see
  the sections above - it is worth checking against the `--help` of the locally
  installed version).

Results of the live check and the actual CLI versions are in [VERIFICATION.md](VERIFICATION.md).

## Contracts

This section describes the current `agentschat` client and what it reads from
the broker, not the first-generation bridge. For whoever connects an agent
platform or writes a script on top of the commands, the main rule is this:
**the outcome of a command is read from a code, not from a sentence.** Sentences
in the room language are meant for a human and a model; their text may change,
and the code does not. How the broker's refusals and the answers of `status`,
`say` and `inbox` are built is in the "Contracts" section of
[ARCHITECTURE.en.md](ARCHITECTURE.en.md).

### Room language

There is one language per room: the `language` key (`en` or `ru`) in
`bridge/config.yaml`, `en` by default. The broker, the client and the message
envelope for the agent speak it. The client learns the language from the
`language` field of the broker's answers (`login`, `wait`, `say`, `inbox`,
`status`) and remembers it, so it speaks that language even when the broker is
unreachable. The room language is also reported by the result line of `status`:
the `language` field.

### Result line

`login`, `logout`, `status`, `say` and `ask` print exactly one line on stdout
after their sentences:

```
AGENTSCHAT-RESULT {"command":"login","ok":true,"agent":"claude-code","mode":"listener","reconnected":false}
AGENTSCHAT-RESULT {"command":"login","ok":false,"agent":"claude-code","code":"slot_taken"}
AGENTSCHAT-RESULT {"command":"logout","ok":true,"agent":"claude-code"}
AGENTSCHAT-RESULT {"command":"status","ok":true,"language":"en","sessions":[{"agent":"claude-code","state":"listening","label":"x","registered":"10:00:00","quiet":12},{"agent":"opencode","state":"not_connected"}]}
AGENTSCHAT-RESULT {"command":"say","ok":true,"agent":"claude-code","event_id":"$e","warning":"unaddressed"}
AGENTSCHAT-RESULT {"command":"ask","ok":true,"agent":"claude-code","event_id":"$e","answered":false}
AGENTSCHAT-RESULT {"command":"ask","ok":false,"agent":"claude-code","event_id":"$e","code":"broker_unreachable"}
```

- Format: the prefix `AGENTSCHAT-RESULT`, a space and one compact JSON object
  (no spaces after `,` and `:`). The line is ASCII only: non-ASCII characters (for
  example, a Russian session label) are written as `\uXXXX`. The key order is
  fixed: `command`, `ok`, then `agent` (for the commands that take it), then the
  rest, and on a refusal `code` goes last.
- **Read the last line with this prefix.** The sentences contain text set by the
  participants (the session label in a `status` line and in a `slot_taken`
  refusal), and it can look like a result line. The real line is always printed
  after all the sentences.
- The sentence of a refusal goes to stderr, the result line to stdout. The exit
  codes are as before: 0 on success, 1 on a refusal or an unreachable broker;
  `status` gives 0 even with `ok:false`.
- There is no token in the line.
- `wait` and `inbox` do not print a result line: their output is read by a model.
  The outcome of `wait` is the exit code (0 - an envelope was printed, 1 - the
  listener stopped or the connection was lost) and the frame.

Keys on success:

| Command | Keys after `command`, `ok` |
|---------|----------------------------|
| `login` | `agent`, `mode`, `reconnected` |
| `logout` | `agent` |
| `status` | `language`, `sessions` |
| `say` | `agent`, `event_id`, and, when the broker has a remark, `warning` or `note` |
| `ask` | `agent`, `event_id`, `answered` |

- `login` has `mode` (the delivery mode of the slot, for example `listener`) and
  `reconnected` (`true` if the session returned to its own registration) instead
  of a session id. The broker does not issue a session id, and the token is a
  secret and does not go into the line.
- `sessions` of `status` are the broker's entries from its `/status` answer,
  without the `line` field (the sentence).
- `warning` and `note` are the codes `warning_code` and `note_code` from the
  broker's answer (`unaddressed`, `addressed_to_person`); the client prints the
  sentences themselves as they came.
- `answered` of `ask`: whether an answer came within the timeout. Silence is not
  a refusal: the message was delivered, `ok` is `true`, the exit code is 0.

A refusal: `ok` is `false`, and `code` comes last. `status` has no `agent` field.
If `ask` broke off while waiting for the answer, the line has `event_id`: the
message has already gone out.

| `code` | When | Exit code |
|--------|------|-----------|
| a broker code (`slot_taken`, `session_not_registered` and the others from the "Contracts" section of [ARCHITECTURE.en.md](ARCHITECTURE.en.md)) | the broker refused `login`, `logout`, `say` or `ask` (for `ask` also while waiting for the answer) | 1 |
| `broker_unreachable` | the request did not reach the broker | 1 |
| `not_logged_in` | there is no token file for this agent: `logout` without `--force`, `say` or `ask` | 1 |
| `broker_refused` | an answer other than 200 without a code (a proxy, aiohttp's own 404 and 405) | 1 |
| `nothing_to_send` | `say` or `ask` with no text, no `--file` and no `-` | 1 |
| `envelope_without_text` | `ask`: the broker answered the wait without the envelope text | 1 |
| `unexpected_answer` | `status` only: an answer without a `sessions` list and without a code | 0 |

The client itself decides nothing by a code; it only passes it into the line.

The OpenCode plugin is one reader of this line: it binds the session of the call
to the agent by the `login` line with `ok:true` and removes the binding by the
`logout` line with `ok:true`. A refusal changes nothing, and the plugin does not
read the Russian phrases of the output.

### The `wait` frame and the envelope

The first line of what `wait` prints on a stop is a frame of the form
`=== AGENTSCHAT: <title> ===`. The prefix `=== AGENTSCHAT: ` and the suffix
` ===` are set by code, and the title comes from the catalogue and depends on the
room language. Whoever needs a marker that does not depend on the language should
rely on the prefix. The titles in English are `broker connection lost` (the
broker has been unreachable longer than allowed, exit code 1) and
`listener stopped` (the broker refused the wait or answered without the envelope
text, exit code 1); in Russian they are different words with the same meaning.

The broker assembles the envelope for the agent itself and hands it over in the
`/wait` answer in the `rendered` field; the client and the plugin print it and do
not retell it. The other fields of the answer: `sender`, `kind`, `text`,
`event_id`, `stamp`, `depth`, `language`. **`kind` is a code, `human` or
`agent`**; the word "human" or "agent" stands only in the text of the envelope,
in the room language. If the wait window ended without messages, the answer is
204. The client treats an answer without `rendered` as the contract error
`envelope_without_text`. The first line of the envelope in an English room is
`=== AGENTSCHAT: incoming message ===`; in a Russian room it is the same line in
Russian. The last line depends on whether the listener dies on delivery: the
broker adds the requirement to start a new listener only where it really dies;
the plugin is not given it.
