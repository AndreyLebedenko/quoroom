# Report: task-local-installers-01-cli-broker-url

**Branch:** `task/local-installers-01-cli-broker-url` (from `feat/local-installers`)
**Base commit:** 54d0949
**Status:** implemented and verified automatically, not committed, no live check.

## What changed

- `bridge/sessionchat/protocol.py`: added `DEFAULT_URL`, built from
  `DEFAULT_PORT`, next to it. `DEFAULT_PORT` stays: the broker still reads it
  from `sessionchat_port` in `config.yaml`.
- `bridge/sessionchat/client.py`: `port()` is gone; `base()` now returns
  `(os.environ.get("AGENTSCHAT_URL") or DEFAULT_URL).rstrip("/")`. Every request
  URL and every diagnostic that named the broker address already went through
  `base()`, so they follow the configured URL without further edits.
- `bridge/tests/test_broker_url.py`: new, 12 tests written before the code.
- `docs/SESSION_BRIDGE.md`: the "Почему на пользователя" passage now states that
  the full URL lives in `AGENTSCHAT_URL` and that the CLI and the OpenCode plugin
  read the same variable with the same default.

## Test coverage against the acceptance criteria

| Criterion | Test |
| --- | --- |
| default URL | `test_absent_variable_leaves_the_local_default`, `test_empty_variable_leaves_the_local_default`, `test_the_local_default_names_the_broker_port` |
| override | `test_the_variable_gives_the_base_url` |
| trailing slash | `test_a_trailing_slash_does_not_double_up_in_a_request_path` (asserts the URL `do_status` really requested) |
| non-local URL accepted | `test_a_non_local_url_is_accepted_as_is` |
| CLI default equals the plugin's `BROKER` default | `test_the_default_is_the_same_url_the_plugin_falls_back_to` (reads `kit/opencode/plugins/agentschat.js` and extracts the `AGENTSCHAT_URL \|\| "..."` literal) |
| `AGENTSCHAT_PORT` no longer read | `test_the_removed_port_variable_no_longer_moves_the_address` |
| address read per call, not cached at import | `test_the_address_is_read_per_call_and_not_cached` |
| refusals and diagnostics name the URL in use | `test_status_refusal_names_the_configured_address`, `test_login_refusal_names_the_configured_address`, `test_deaf_listener_notice_names_the_configured_address` |

## Verification (all run from `bridge/`)

- `.venv/Scripts/python.exe -m unittest discover -s tests -t .` — Ran 185
  tests, OK.
- `node --test tests/plugin/agentschat.test.mjs` — tests 4, pass 4, fail 0.
- `.venv/Scripts/ruff.exe check` — All checks passed.
- `.venv/Scripts/ruff.exe format --check` — 18 files already formatted.

`ruff` is not on PATH in this shell; the project virtualenv's
`.venv/Scripts/ruff.exe` is the same tool, version 0.16.6.

Red before green: with the tests in place and the code unchanged, the module
failed to import (`ImportError: cannot import name 'DEFAULT_URL'`), so all 12
tests were red.

## Deviations and interpretations

1. `AGENTSCHAT_PORT` still appears in `bridge/tests/test_broker_url.py`. The
   test is what pins the removal (AGENTS.md, Core 7: an invariant is a test,
   not a comment), and the card's criterion names code, kit, and docs, not
   tests.
2. `AGENTSCHAT_PORT` also still appears in
   `.development/tasks/story-local-installers.md` and in this task card. Those
   are the records of the decision and of the pre-change state; editing them
   would erase the decision the story's implementation gate item 3 holds.
3. `docs/INSTALL.md` and `README.md` never named the CLI's address variable, so
   they are untouched. Task 08 owns them.
4. Refusals that do not name the address at all (`do_logout`, `do_inbox`,
   `do_say`, `do_ask`: "брокер недоступен: <error>") were left as they are. The
   requirement covers the ones that name the address. Adding the address to the
   others is not in the card; say the word if it should be.
5. Nothing was verified live, so `docs/VERIFICATION.md` is unchanged. The task
   card stays `Planned` in `.development/tasks/` until you review it.

## Not done, by design

- No broker change, no plugin behavior change, no new test or code that rejects
  a non-local address.
- No commit, per instruction.