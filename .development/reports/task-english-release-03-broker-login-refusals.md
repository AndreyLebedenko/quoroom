# Report: task english-release-03 (broker login refusals)

Branch: task/english-release-03-broker-login-refusals (worktree D:/AI/AgentsChat-wt/task-03). Not committed.

## Decisions and reasons

1. Error body: JSON `{"code", "message", "params"}`, as recommended. HTTP statuses
   unchanged. Built by one helper, `Broker._refusal(status, code, params, keys, **words)`,
   which composes the message from catalogue keys in the room language and
   raises the aiohttp exception with `content_type="application/json"`. The body
   is serialised with `ensure_ascii=False`, so a person running `curl` reads
   Russian instead of `\uXXXX`, and the existing tests that look for Russian
   substrings in the raw response text still pass unedited.
2. Compatibility: client and broker ship in one package and one version, so there
   is no mixed-version window and no old-text path in the broker. One thing stays
   on the client side: `explain()` shows `message` when the body is a JSON object
   with a non-blank `message`, and otherwise prints the body text as it is (or
   `HTTP <status>` when empty). This is needed anyway for answers that are not the
   broker's (aiohttp's own 404/405, a proxy page) and, until task 04, for the
   `say` refusals, which are still plain text.
3. One key per sentence, not per refusal. A refusal whose Russian text was several
   sentences is a list of keys joined with one space, in code. The Russian join is
   byte-identical to the old concatenation (the old text was already joined with
   single spaces). Variants (which advice sentence) are chosen in code, not in the
   catalogue. A test asserts the full Russian message of every scenario, character
   for character, as the old code built it.
4. Placeholder `state_word` in `broker.slot_taken` is rendered from the catalogue
   (`broker.state_*` keys) and passed as a "word" separate from `params`; `params`
   carries the language-independent `state` code.
5. Session state needed a code now (task 04's boundary overlaps here, because the
   slot-taken sentence quotes the state). Smallest change that serves both:
   `Registration.state_code()` returns `listening | processing | not_listening`
   (same conditions as before); `Registration.state()` is unchanged in output, it
   now returns `BROKER_CATALOGUE.text("ru", "broker.state_<code>")`. So `/status`
   and its tests are untouched, no Cyrillic literal remains in `state()`, and
   task 04 can delete `state()` and switch `handle_status` to the code plus the
   same three catalogue keys. Task 04 should reuse `broker.state_*`, not add its own.
6. `Registration.advice()` now returns `(advice_code, {"quiet", "left"})` instead
   of a Russian string (`over_limit | polled | silent`); the broker maps the code
   to catalogue keys (`ADVICE_SENTENCES`). Its only caller is the slot refusal.
7. `registration_of` (token not known / not matching) is included, because the card
   names it. It is shared with `wait`, `inbox`, `say`, so those endpoints now answer
   with the same coded body. One code for both "no registration" and "wrong token"
   on purpose: telling them apart would let a caller probe for registered agents.
8. The delivery-mode refusal (`unknown_delivery`) is a startup `ValueError` in
   `Broker.__init__`, not an HTTP answer, so it has a code name and keys but no
   status. Its message is composed from the catalogue in the room language. The
   `БРОКЕР НЕ ЗАПУЩЕН:` prefix that `main()` adds is task 05's.
9. `package-data` in `bridge/pyproject.toml` now includes `broker_messages/*.json`
   (the packaging test from task 01 requires it).
10. Client branching: the client has no code that branches on a refusal text
    today (it prints and exits 1), so nothing branches on `code` either and no
    `code` reader was added: an unused reader would be speculation. Tests prove
    the displayed text depends only on `message`, never on `code` or `params`.

## Codes (code, HTTP status, catalogue keys of the message, in order)

| code | status | keys |
|---|---|---|
| `unknown_agent` | 404 | `broker.unknown_agent` |
| `reconnect_without_registration` | 409 | `broker.reconnect_without_registration`, `broker.reconnect_without_registration_hint` |
| `reconnect_token_mismatch` | 409 | `broker.reconnect_token_mismatch`, `broker.reconnect_token_mismatch_owner` |
| `slot_taken` | 409 | `broker.slot_taken`, one advice group, then `broker.slot_taken_not_yours`, `broker.slot_taken_token_proof`, `broker.slot_taken_ask_human`, `broker.slot_taken_force` |
| `slot_in_store` | 409 | `broker.slot_in_store`, `broker.slot_in_store_next` |
| `session_not_registered` | 409 | `broker.session_not_registered` |
| `unknown_delivery` (startup `ValueError`, no HTTP) | - | `broker.unknown_delivery`, `broker.unknown_delivery_allowed` |

Advice groups of `slot_taken`, chosen by the `advice` param: `over_limit` ->
`broker.advice_over_limit`; `polled` -> `broker.advice_polled`,
`broker.advice_polled_meaning`; `silent` -> `broker.advice_silent`,
`broker.advice_silent_meaning`.

`params` per code: `unknown_agent`, `reconnect_*`, `slot_in_store`:
`{"agent"}`; `session_not_registered`: `{}`; `slot_taken`: `agent`, `registered`
(HH:MM:SS), `label`, `state` (code), `advice` (code), `quiet` (s), `left` (s).
No token or secret in any `message` or `params` (a test checks both the token of
the holder and the token in a reconnect attempt).

## Catalogue keys added (23, `bridge/sessionchat/broker_messages/{en,ru}.json`)

broker.advice_over_limit, broker.advice_polled, broker.advice_polled_meaning,
broker.advice_silent, broker.advice_silent_meaning,
broker.reconnect_token_mismatch, broker.reconnect_token_mismatch_owner,
broker.reconnect_without_registration, broker.reconnect_without_registration_hint,
broker.session_not_registered, broker.slot_in_store, broker.slot_in_store_next,
broker.slot_taken, broker.slot_taken_ask_human, broker.slot_taken_force,
broker.slot_taken_not_yours, broker.slot_taken_token_proof,
broker.state_listening, broker.state_not_listening, broker.state_processing,
broker.unknown_agent, broker.unknown_delivery, broker.unknown_delivery_allowed.

Keys are sorted, `en.json` is printable ASCII without Cyrillic, key and
placeholder sets are identical (`CatalogueContract` from task 01 runs on it).

## Files

- `bridge/sessionchat/broker.py`: catalogue, `_compose`, `_refusal`, refusals, `state_code`, `advice`.
- `bridge/sessionchat/broker_messages/en.json`, `ru.json`: new.
- `bridge/sessionchat/client.py`: `explain` only.
- `bridge/pyproject.toml`: package-data.
- `docs/SESSION_BRIDGE.md`: one short section on the error contract (Russian).
- New tests: `bridge/tests/test_broker_refusals.py` (35), `bridge/tests/test_client_refusals.py` (12).

## Edits to existing tests

1. `bridge/tests/test_sessionchat.py`: the shared `CONFIG` gained `"language": "ru"`
   (one line). Reason: the broker default is now `en` and these tests assert the
   Russian text, so they must run with the room language `ru`, as the story says.
   No expectation was edited.
2. `bridge/tests/test_broker_language.py` (task 02's tests): it imported `CONFIG`
   from `test_sessionchat`, and its tests need a config WITHOUT `language` to
   prove the default. Construction only: it now imports the shared config as
   `RUSSIAN_CONFIG` and builds its own `CONFIG` without the `language` key
   (two import lines and one assignment). No expectation changed.

## Checks (from D:/AI/AgentsChat-wt/task-03/bridge, in order)

1. `unittest discover -s tests -t .`: Ran 1209 tests, OK (skipped=2). Baseline 1162,
   +47 new (35 broker refusals, 12 client).
2. `node --test tests/plugin/agentschat.test.mjs`: 4 pass, 0 fail.
3. `ruff check`: All checks passed.
4. `ruff format --check`: 54 files already formatted.

No live checks were run.

## Noticed, not touched

- Log lines in login/slot code are still Russian (`_release_stale`,
  `handle_login`, `handle_logout`: "слот ... освобождён", "переподключение ...",
  "подключена сессия", "отключена сессия"). Task 05 owns them explicitly
  ("the `log.info(...)` calls for a slot being freed, re-attached, connected,
  disconnected"), so card 03's acceptance line "no Cyrillic literal in the
  login / logout / slot code" is read as "no user-visible refusal literal"; the
  scan test excludes arguments of `log.*` calls for that reason. Task 05 should
  tighten the scan when it moves them.
- `say`, `inbox`, `wait` refusals other than `session_not_registered` (empty
  message, depth limit, rate limit, notes) are still plain Russian text: task 04.
  `Registration.state()` and its Russian output stay for `/status` until task 04.
- `join_all` / `publish` `RuntimeError`s, `only_agents`, `run()`/`main()` messages:
  tasks 05.
- The OpenCode plugin logs `response.text()` of a 409 from `/wait`; it now logs the
  JSON body. It decides by status, not by text, so nothing breaks; task 12 owns
  the plugin and its log.
- Cyrillic comments and docstrings in `broker.py` remain (out of story scope).
- The docs (`INSTALL.md`, `ARCHITECTURE.md`, skills) may quote the old refusal
  texts; not checked, tasks 14-19.
