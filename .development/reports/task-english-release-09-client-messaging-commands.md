# Report: task english-release-09 (wait, inbox, say, ask and the help of the subcommands)

Branch: task/english-release-09-client-messaging-commands (worktree D:/AI/AgentsChat-wt/task-09). Nothing committed.

## Decisions and reasons

1. `wait` frames are assembled in code, the title comes from the catalogue. The code owns
   `=== AGENTSCHAT: {title} ===` (constant `FRAME`, helper `frame()`); the catalogue holds only
   the title (`wait_broker_lost_title`, `wait_listener_stopped_title`). Why: the card wants a
   stable marker; a catalogue edit (or a missing translation of the title) cannot change the shape
   of the first line. A test replaces every sentence with other words and the first line still
   matches `^=== AGENTSCHAT: .+ ===$`.
2. `ru` keeps the Russian title character for character (the orchestrator's decision); `en` is
   ASCII English with the same prefix. The card text says "ASCII marker in both languages"; in `ru`
   the first line therefore is not pure ASCII (only its `=== AGENTSCHAT: ` prefix and ` ===` are).
   Consumers that need a language-independent marker must use the prefix, not the title. Flagged
   for the owner in case the card meant a Latin title in `ru` too.
3. `wait` and `inbox` print no result line. Why: their output is read by a model, the card asks
   for a result line from `say` and `ask` only. A listener's outcome is its exit code (0 message,
   1 stopped or lost) plus the frame.
4. `say` and `ask` share one delivery step (`deliver(command, args)`), so `ask` prints exactly one
   result line (a line named `ask`, never an extra `say` line). `do_say` is that step plus its
   line; `do_ask` is the step plus waiting plus its line. `args.text` is no longer overwritten by
   `message_text` (nothing read it afterwards).
5. Result line fields (decision beyond the brief, each with its reason):
   - `agent` after `ok`, as for `login` / `logout` (task 08 convention: commands that take
     `--agent` carry it).
   - `warning` / `note` carry `warning_code` / `note_code` of the broker answer. The brief named
     `warning`; `note` mirrors it, because `addressed_to_person` ("no agent got it, a person did")
     is an outcome a program may want. A `warning` or `note` sentence without its code (an older
     broker) is printed but adds nothing to the line.
   - `ask` adds `answered` (true / false). Why: an `ask` that timed out exits 0 with the message
     delivered, and without this field a program could tell "answered" from "silence" only by
     reading the output.
   - `event_id` is present in every success and in an `ask` that broke while waiting (the message
     was already delivered; the code says why the wait ended). It is absent when the send itself
     was refused (there is no event).
6. The wait phase of `ask` gets a code. `poll_once` used to raise a bare `RuntimeError` for a
   non-200 answer and lost the broker's code; it now raises `ContractError(refusal_code(response),
   explain(response))` (a `RuntimeError` subclass, same message, so `do_wait` and every old test
   behave as before). `ask` maps: `ContractError` -> its code (`envelope_without_text` or the
   broker's refusal code), a `requests` error -> `broker_unreachable`, any other `RuntimeError`
   -> `broker_refused`. The client still never branches on a code; it only forwards it.
7. `credentials(agent, command=None)`: with a command the "not logged in" refusal carries the
   result line (`not_logged_in`), without one it fails as before (`wait`, `inbox`). It stays one
   function because the older tests patch `client.credentials`.
8. "Nothing to send" (`message_text`, shared by `say` and `ask`) keeps raising `SystemExit` through
   `fail` (an existing test pins that). `outgoing_text(command, args)` wraps it and prints
   the result line with code `nothing_to_send`. Its only `SystemExit` source is that one refusal.
9. Keys follow the zone (`wait_*`, `inbox_*`, `say_*`, `ask_*`, `usage_*`). Sentences that are
   equal in meaning stay separate per zone (`inbox_broker_unreachable`, `say_broker_unreachable`;
   `ask` uses the `say_` ones) instead of one shared key, as the brief asked for zone names.
   Shared by two subcommands on purpose: `say_text_help` and `say_file_help` (`ask` takes the same
   arguments).
10. Variants are chosen in code: the four lines of the lost-broker frame are four keys joined with
    a newline; the timeout is two keys (`ask_timeout`, `ask_timeout_delivered`) joined by a
    space; the inbox header is preceded by an empty line printed in code (layout).
11. English wording the owner may want to read: "The listener exited instead of pretending to
    work blind.", "messages that arrived while you were away: N" (the Russian has "messages
    received: N", an English count with a plural would need variants), "WARNING - ..." for
    "ВНИМАНИЕ — ...".
12. Equivalence under `ru`: a scratch script (not in the repository) ran 30 scenarios against the
    client at HEAD and this tree, remembered language `ru`, fresh store: stdout without the
    result line, stderr and exit code were identical in all 29 meaningful ones (wait lost short
    and long, stopped, message, no credentials; inbox pending, empty, no key, down, refused, no
    credentials; say sent, warning, note, refused, down, no credentials, empty; ask answered,
    timeout, down, refused poll, no envelope text, refused send, empty; help of say, ask, wait,
    inbox and the top listing). The 30th ("wait no text") was my scenario's mistake (a mock's
    repr differs by object id), not a behaviour difference.

## The wait frames (exact lines)

Lost broker (after `DEAF_SECONDS`; exit 1). `{url}` is the broker address, `{seconds}` the whole
seconds of silence, `{error}` the `requests` error text.

```
ru
=== AGENTSCHAT: связь с брокером потеряна ===
Брокер {url} недоступен уже {seconds}с: {error}
Listener завершился, чтобы не изображать работу вслепую.
Проверь, запущен ли брокер, и подними listener заново.

en
=== AGENTSCHAT: broker connection lost ===
The broker {url} has been unreachable for {seconds}s: {error}
The listener exited instead of pretending to work blind.
Check whether the broker is running and start the listener again.
```

Listener stopped (the broker refused the poll, or the answer had no envelope text; exit 1). The
second line is the broker's refusal message as it came (already in the room language), or the
client's `envelope_without_text` sentence:

```
ru
=== AGENTSCHAT: listener остановлен ===
{reason}

en
=== AGENTSCHAT: listener stopped ===
{reason}
```

Skills (tasks 14, 15) must quote the English first lines `=== AGENTSCHAT: broker connection lost
===` and `=== AGENTSCHAT: listener stopped ===` and the English envelope line of task 06
(`=== AGENTSCHAT: incoming message ===`).

## The result line of `say` and `ask`

```
AGENTSCHAT-RESULT {"command":"say","ok":true,"agent":"claude-code","event_id":"$e"}
AGENTSCHAT-RESULT {"command":"say","ok":true,"agent":"claude-code","event_id":"$e","warning":"unaddressed"}
AGENTSCHAT-RESULT {"command":"say","ok":true,"agent":"claude-code","event_id":"$e","note":"addressed_to_person"}
AGENTSCHAT-RESULT {"command":"say","ok":false,"agent":"claude-code","code":"session_not_registered"}
AGENTSCHAT-RESULT {"command":"ask","ok":true,"agent":"claude-code","event_id":"$e","answered":true}
AGENTSCHAT-RESULT {"command":"ask","ok":true,"agent":"claude-code","event_id":"$e","answered":false}
AGENTSCHAT-RESULT {"command":"ask","ok":false,"agent":"claude-code","event_id":"$e","code":"broker_unreachable"}
```

Printed on stdout once per command after the sentences (same `report()` and `client_result.line()`
as task 08); the sentence of a refusal goes to stderr. Exit codes are unchanged (0 sent / answered /
timed out, 1 any refusal).

| code | when | exit |
|---|---|---|
| the broker's code (`session_not_registered`, ...) | `say` / `ask` was refused by the broker; or `ask` was refused while waiting | 1 |
| `broker_unreachable` | the request or the wait could not reach the broker | 1 |
| `not_logged_in` | no credentials file for the agent | 1 |
| `broker_refused` | a non-200 answer without a code (a proxy page) | 1 |
| `nothing_to_send` | no text, no `--file`, no `-` | 1 |
| `envelope_without_text` | `ask`: the broker answered the wait without the envelope text | 1 |

Codes are snake_case. In an `ask` that broke while waiting, `event_id` is in the line (the message
was delivered).

## Catalogue keys added (22, in `client_messages/{en,ru}.json`, sorted)

ask_help, ask_interrupted, ask_timeout, ask_timeout_delivered, inbox_broker_unreachable,
inbox_empty, inbox_help, inbox_pending, say_broker_unreachable, say_file_help, say_help, say_note,
say_sent, say_text_help, say_warning, usage_nothing_to_send, wait_broker_lost_exited,
wait_broker_lost_restart, wait_broker_lost_title, wait_broker_lost_unreachable, wait_help,
wait_listener_stopped_title.

`ru` is the old literal, split at sentence boundaries, character for character (decision 12).
Codes introduced: `nothing_to_send` (client). The files keep their CRLF line endings.

## Files

- `bridge/sessionchat/client.py`: `credentials` (command argument), `poll_once` (raises
  `ContractError` with the broker's code), `frame`, `do_wait`, `show_pending`, `do_inbox`,
  `message_text`, `outgoing_text`, `deliver`, `delivered_fields`, `wait_failure_code`, `do_say`,
  `do_ask`, the parser entries of `wait`, `say`, `ask`, `inbox`; constants `NOTHING_TO_SEND`,
  `FRAME`. `install` / `uninstall` code, their parser entries and `JSON_HELP` were not touched.
- `bridge/sessionchat/client_messages/{en,ru}.json`.
- `docs/SESSION_BRIDGE.md`: one Russian paragraph after the task 08 one (AGENTS.md rule 2).
- New `bridge/tests/test_client_messaging_commands.py` (50 tests).

New tests, in short: every `wait` ending (lost broker, stopped listener, message, answer without
envelope text, short outage, no registration) in both languages with exact text; the ASCII
`=== AGENTSCHAT: ... ===` first line in both languages and under a catalogue of other words;
`inbox` with / without messages, no `pending` key, unreachable, refused, no registration, no
Cyrillic in `en`; `say` sent / warning / note printed as received (braces and `%s` in the text do
not break), the Russian texts verbatim, warning without code, request body, refusal with and
without a code, unreachable, no registration, nothing to send (no request made), `--file`, no
token and no Cyrillic in any `en` output; `ask` answered, warning, timeout, interrupted by an
unreachable broker / a refusal / a missing envelope text, refusal of the message (no waiting),
unreachable on the first request, no registration or no text; exactly one result line in every
scenario; the reader gets the same result when every sentence is "WORDS key" (11 scenarios);
command / ok / agent lead and `code` is last on a failure; ASCII prefix plus one JSON object;
help of `wait`, `say`, `ask`, `inbox` in both languages (and none Cyrillic in `en`); an ast scan:
no Cyrillic string literal in `client.py` outside `do_install`, `do_uninstall`, `refuse`,
`reported`, the `install` / `uninstall` parser entries and `JSON_HELP` (docstrings are skipped).

## Edits to existing tests (each with its reason; no Russian expectation changed)

1. `tests/test_listener.py`, `ListenerTests.setUp`: the client store is now a temporary directory
   holding the language `ru`, with a fresh `RoomLanguage` (two patches and one import
   `client_language`). Why: the Russian frame assertions (`связь с брокером потеряна`,
   `listener остановлен`) run under "the room language ru" as the story says; the client now
   chooses the frame language through `speak`, and with no remembered language it speaks English.
   No assertion changed. This is the case the brief warned about; I judged it a construction
   edit (the setup selects the language the test was always meant to run in), not an
   expectation change. If you disagree, the alternative is to leave the test and let it fail.
2. No other existing test needed a change. `test_broker_url.py` (deaf notice names the address),
   `test_envelope_language.py` (`do_wait` / `do_ask` print the code), `test_client_refusals.py`,
   `test_broker_say_status.py` (the Russian `say` lines, indexed by line number) and
   `test_client_session_commands.py` (including its "every catalogue key is used" scan) pass
   unedited.

## Checks (from D:/AI/AgentsChat-wt/task-09/bridge, in order)

1. `unittest discover -s tests -t .`: Ran 1574 tests, OK, 2 skipped (baseline 1524, +50). No flaky
   test seen.
2. `node --test tests/plugin/agentschat.test.mjs` (run alone): 4 pass, 0 fail. No process killed.
3. `ruff check`: All checks passed.
4. `ruff format --check`: 66 files already formatted.

No live checks were run.

## Noticed, not touched

- Russian docstrings and comments remain in `client.py` (module docstring, `poll_once`,
  `show_pending`, `message_text`, the comments in `do_login`, `do_logout`, `do_wait`,
  `message_text`). The story puts them out of scope ("After the release"), the new scan skips
  docstrings and comments. If task 17's scan should reject them, they need their own card.
  `JSON_HELP` and the `install` / `uninstall` parser texts are task 11's.
- `-h` of the top listing still mixes languages: `install` / `uninstall` help is Russian until
  task 11.
- `say --file` with a missing or unreadable file ends in a traceback and no result line (as
  before): not a usage error the card named. A coded `unreadable_file` refusal would be a new
  behaviour.
- `main()` builds the parser (and its `speak` calls) before the arguments are parsed, so help
  follows the remembered language, not a `--lang` on the same command line (already noted in
  task 08; task 11 decides).
- `do_ask` reads the credentials file twice (once inside `deliver`, once for the wait token),
  as the old code did.
- The OpenCode plugin and the skills still quote the Russian frames and sentences of `wait`,
  `say`, `ask` (tasks 12, 14, 15).
