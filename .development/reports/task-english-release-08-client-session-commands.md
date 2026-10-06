# Report: task english-release-08 (login, logout, status and the result line)

Branch: task/english-release-08-client-session-commands (worktree D:/AI/AgentsChat-wt/task-08). Nothing committed.

## Decisions and reasons

1. The result line is a last line of the default output, not a `--json` mode.
   Why: the program that needs the result (the OpenCode plugin, task 12) does not
   run the command; the agent does, with the arguments its skill told it. The
   plugin sees only the output after the fact and cannot add a flag to a command it
   did not start. A `--json` mode (as `install --json` has) replaces the sentences,
   so the agent would read nothing; here one run serves both readers, the agent
   reads the sentences and the program reads the line. Costs: a consumer must find
   the line among other lines (take the last one that starts with the prefix).
2. Format: `AGENTSCHAT-RESULT ` + one JSON object, compact separators, pure ASCII
   (`ensure_ascii`, so a Russian label cannot break a console in another code page).
   Printed on stdout, once per command, after the sentences, with `flush`. A
   refusal sentence goes to stderr as before and the line to stdout, so the line is
   still last in a merged stream. Built by `client_result.line()` (new module,
   `PREFIX`), used by `client.report()`.
3. `session` key of the card's recommended line is not used. `"session":"<id>"` has
   no source: the broker's login answer carries no session id (only `token`, `room`,
   `mode`, `reconnected`, `language`), the token is a secret and a hash of it is
   not needed by anyone, and the OpenCode session id is known to the plugin, not to
   the CLI. Inventing an id would be code for no reader. Instead `login` reports
   `mode` and `reconnected`, which a program can decide on (for example "start a
   listener" is `mode == "listener"`) instead of reading "Listener запускать НЕ
   надо". If the owner wants a session id in the line, the broker has to issue one;
   that is a broker decision, not this card's.
4. Key order is part of the contract: `command`, `ok`, then `agent` (login, logout),
   then the rest, `code` last on a refusal. Tests pin the exact line of a listener
   login and of a logout.
5. Exit codes are unchanged (0 success, 1 refusal or unreachable broker). `status`
   returns 0 as before even when its answer is unusable (`ok:false`,
   `code:unexpected_answer`); changing that would change an exit code.
6. A broker refusal: the client shows `explain()` (the broker's `message`) and puts
   the body's `code` in the line. The client does not branch on `code` anywhere (it
   only forwards it). A refusal without a code (a proxy page, aiohttp's own 404/405)
   gets `broker_refused`.
7. Where each sentence comes from: refusals from the broker already rendered;
   success sentences, the "start the listener" instruction, the unreachable-broker
   sentences, the not-logged-in sentences and the help texts from the client
   catalogue through `speak`. Variants (listener, plugin, push, reconnect with or
   without listener) are chosen in `login_sentences()`, one key per sentence; lines
   are joined with newlines and the two sentences of the last line with one space,
   as the old code printed them. The command line to start the listener
   (`    agentschat wait --agent <agent>`) is a command, not prose, and stays in code.
8. `credentials()` is shared with `wait`, `inbox`, `say` (task 09). Its sentence is
   now catalogued (`not_logged_in`, `not_logged_in_login`) and its behaviour is
   unchanged; the file read is split out as `saved_credentials()` so `logout` can
   report `not_logged_in` with a result line while the other commands keep failing
   as before.
9. `do_login` writes the credentials file before it prints the sentences (it
   printed the reconnect sentence first before). On success the output is the same;
   the order only matters if the file cannot be written (see "Noticed").
10. The Russian wording the OpenCode plugin matches is kept: "подключена к комнате"
    (login, in the reconnect and the three connected variants) and "отключена"
    (logout). Tests assert both words so a catalogue edit cannot lose them before
    task 12 moves the plugin to the line. In `en` the plugin does not bind a
    session until task 12; this is the ordering the story set (12 depends on 08).
11. `status` unreadable answers keep their old printing: a non-JSON answer is
    printed as is, a JSON object without `sessions` prints an empty line (an existing
    test pins that), plus one change: a JSON body with a non-blank `message` (a broker
    refusal shape) prints that message. In all three cases the line says `ok:false`
    with the body's `code` or `unexpected_answer`.
12. Equivalence under `ru`: I ran the same 17 scenarios (login in 3 modes x
    reconnect, login refused / unreachable, logout normal / forced / refused /
    unreachable / not logged in, status normal / plain text / without sessions /
    unreachable) against the client at HEAD and against this tree with the
    remembered language `ru` and a fresh HOME. stdout (without the result line),
    stderr, the exit code and the presence of the credentials file were identical
    in all 17. The script lived in the scratch directory and is not in the repository.

## The result line

```
AGENTSCHAT-RESULT {"command":"login","ok":true,"agent":"claude-code","mode":"listener","reconnected":false}
AGENTSCHAT-RESULT {"command":"login","ok":false,"agent":"claude-code","code":"slot_taken"}
AGENTSCHAT-RESULT {"command":"logout","ok":true,"agent":"claude-code"}
AGENTSCHAT-RESULT {"command":"logout","ok":false,"agent":"claude-code","code":"not_logged_in"}
AGENTSCHAT-RESULT {"command":"status","ok":true,"language":"ru","sessions":[{"agent":"claude-code","state":"listening","label":"x","registered":"10:00:00","quiet":12},{"agent":"opencode","state":"not_connected"}]}
AGENTSCHAT-RESULT {"command":"status","ok":false,"code":"broker_unreachable"}
```

`status` sessions are the broker's entries without `line` (the sentence). The line
never contains a token (tests check every scenario).

| code | when | exit |
|---|---|---|
| (the broker's code, e.g. `unknown_agent`, `reconnect_without_registration`, `reconnect_token_mismatch`, `slot_taken`, `slot_in_store`, `session_not_registered`) | the broker refused `login` or `logout` | 1 |
| `broker_unreachable` | the request could not reach the broker (all three commands) | 1 |
| `not_logged_in` | `logout` without `--force` and no credentials file for the agent | 1 |
| `broker_refused` | a non-200 answer of `login` / `logout` that carries no code | 1 |
| `unexpected_answer` | `status` got an answer without a `sessions` list and without a code | 0 |

Codes are snake_case; a test requires that shape for every failure.

## Catalogue keys added (23, `bridge/sessionchat/client_messages/{en,ru}.json`)

login_broker_unreachable, login_connected, login_help, login_label_help,
login_listener_restart, login_listener_start, login_listener_woken,
login_plugin_holds, login_plugin_no_listener, login_push_delivery,
login_push_no_listener, login_reconnect_help, login_reconnected,
login_reconnected_listener, login_reconnected_slot_kept, logout_broker_unreachable,
logout_done, logout_force_help, logout_help, not_logged_in, not_logged_in_login,
status_broker_unreachable, status_help.

Sorted, printable ASCII without Cyrillic in `en.json`, same keys and placeholders in
both files (the `CatalogueContract` test of `test_client_language.py` runs on them),
every key of the client catalogue is referenced in `client.py` (a new test). The `ru`
texts are the old literals split at sentence boundaries; Russian output verified
character for character (decision 12). English wording the owner may want to read:
`login_listener_start`, `login_plugin_holds`, `login_push_delivery`,
`login_reconnected` (the Russian "—" became " - ", the Russian "ты"/"подними" became
second person and imperative).

## Broker changes (`bridge/sessionchat/broker.py`, three lines)

`"language": self.language` added to the success answer of `/login` (fresh
registration and reconnect, one line each) and to the `/wait` 200 answer next to
`rendered` (the Envelope fields and `rendered` are untouched; the OpenCode plugin
reads `rendered` / `text`). Refusals and the `/wait` 204 are unchanged. Tests in the
new `tests/test_broker_login_wait_language.py` (5): language in both languages for
login, reconnect and wait; the login answer keeps `token`, `room`, `mode` plus
`language`; the `/wait` answer keeps every field the plugin reads.

## Files

- `bridge/sessionchat/client.py`: `do_login`, `login_sentences`, `do_logout`,
  `do_status`, `status_answer`, `status_sessions`, `unreadable_status`,
  `saved_credentials`, `not_logged_in_message`, `credentials`, `report`,
  `fail_with_result`, `refusal_code`, parser help of login / logout / status, four
  code constants. Nothing of `install` / `uninstall` / `wait` / `inbox` / `say` /
  `ask` was touched.
- `bridge/sessionchat/client_result.py` (new, 7 lines): the line format.
- `bridge/sessionchat/client_messages/{en,ru}.json`.
- `bridge/sessionchat/broker.py`: three lines.
- `docs/SESSION_BRIDGE.md`: one Russian paragraph under the error-contract section
  (AGENTS.md rule 2). `docs/AGENTS_INTEGRATION.md` is task 19.
- New tests: `tests/test_client_session_commands.py` (46), `tests/test_broker_login_wait_language.py` (5),
  `tests/result_line.py` (reader helpers: `result_lines`, `read_result`,
  `without_result`).

New client tests, in short: every login variant (listener, plugin, push, each also as a
reconnect) in both languages with the exact sentences (Russian as before, English
as catalogued), the exact result line, exit code; logout success / forced / refused /
unreachable / not logged in in both languages; status result and printing; a reader
test that replaces every sentence of the catalogue with other words ("WORDS key") and
still gets the same result and exit code for ten scenarios; exactly one result line
per command in every scenario; no token in output; fixed prefix plus one JSON object;
`command` and `ok` first; code shape; no Cyrillic in any `en` output; help of the
three commands in both languages; a static scan (ast) that `do_login`, `do_logout`,
`do_status`, `credentials` and the parser entries of the three commands hold no
Cyrillic literal.

## Edits to existing tests (each with its reason; no Russian expectation changed)

1. `tests/test_client_language.py`:
   - `setUp`: the stand-in catalogue is now the real client catalogue overlaid with
     the two stand-in keys (`failure_line`, `probe`) instead of only those two keys.
     Why: `do_login`, `do_status` and `main()` now ask the catalogue for keys
     beyond those two and a missing key is an error by design. The tests still
     prove the same thing with the same stand-in texts.
   - `test_status_prints_the_text_of_the_answer_exactly_as_before` and
     `test_status_prints_a_plain_text_answer_untouched_and_learns_nothing`: the
     compared output is wrapped in `without_result(...)`. Why: the result line is
     added after the sentences; the expected text is untouched.
   - import of `without_result` from the new `tests/result_line.py`.
2. `tests/test_broker_say_status.py` (`StatusAsTheClientPrintsItTests`): `printed()`
   returns `without_result(output)`, and the two tests that compared the whole
   output (`..._whatever_sentences_the_broker_rendered`,
   `..._without_sessions_prints_an_empty_line`) wrap it the same way. Why: same, the
   line is added after. Expected texts untouched. This is the case the brief called
   a signal; the construction fix is the filter, nothing else.
3. No other existing test needed a change (`test_broker_url.py`,
   `test_client_refusals.py`, `test_kit_installer.py`, `test_listener.py` pass
   unedited; `test_client_refusals.py` and a few others now print the result line
   to the real stdout during the run, which is noise only).

## Checks (from D:/AI/AgentsChat-wt/task-08/bridge, in order)

1. `unittest discover -s tests -t .`: Ran 1479 tests, OK, 2 skipped (baseline 1428,
   +51: 46 client, 5 broker).
2. `node --test tests/plugin/agentschat.test.mjs`: 4 pass, 0 fail (run alone).
3. `ruff check`: All checks passed.
4. `ruff format --check`: 64 files already formatted (I ran `ruff format` on the
   files I touched first).

No live checks were run. No process was killed.

## Noticed, not touched

- The OpenCode plugin still decides by the Russian phrases; in an English room it
  will not bind a session until task 12 reads the line. Skills (`kit/*/skills`) quote
  the Russian login/logout sentences; tasks 14 and 15.
- `main()` builds the parser (and its `speak` help calls) before the arguments are
  parsed, so the help of the three commands follows the remembered language, not a
  `--lang` given on the same command line; task 11 adds `--lang` and decides where
  the language is fixed. Until task 09, the other subcommands (`wait`, `say`, `ask`,
  `inbox`) still have Russian help, so `agentschat -h` lists mixed languages.
- If the credentials file cannot be written, `do_login` ends with a traceback and
  prints no result line, while the broker already holds the registration. A coded
  `credentials_not_saved` refusal would be a new behaviour; not part of this card.
- `wait`, `inbox`, `say`, `ask` still print sentences with no result line (task 09),
  and `credentials()` now speaks from the catalogue for them too.
- `do_login` reports `mode: null` if a broker ever omits `mode`; the broker always
  sends it today.
- A participant-supplied label can contain a line that looks like a result line
  (it is printed inside the broker's status line and inside a slot-taken sentence).
  The real line is always last, so the rule for readers is: take the last line that
  starts with the prefix. It is in `SESSION_BRIDGE.md`; task 19 should repeat it in
  `AGENTS_INTEGRATION.md`, and task 12's plugin reader must do it.
- Russian comments in `client.py` (module docstring, the two comments left in
  `do_login` / `do_logout`) are untouched; out of the story scope.
- `client.py` and the catalogue files have CRLF line endings in this worktree; I
  preserved them. New files are LF.
