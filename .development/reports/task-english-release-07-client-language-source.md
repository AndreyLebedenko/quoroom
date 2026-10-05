# Report: task english-release-07 (how the client knows the room language)

Branch: task/english-release-07-client-language-source (worktree D:/AI/AgentsChat-wt/task-07). Nothing committed.

## Decisions and reasons

1. Precedence: explicit `--lang` > the broker's answer in this run > the remembered
   file > `en`. As recommended. Any source holding something other than the exact
   strings `en` / `ru` is skipped for the next one (never an error).
2. Storage: plain file `~/.agentschat/language` (`STORE / "language"`), content is
   the code and a newline, not per agent, not secret. Written through a temporary
   file `language.<pid>.tmp` in the same directory and `os.replace`; the pid in the
   name keeps a `wait` listener and a `say` from colliding. A write error
   (unwritable store, failed replace) is swallowed, the temporary file removed and
   the old value kept: the file is a convenience, and failing `say` because of it
   would be worse than speaking the old language. The write is skipped when the
   file already holds the same value (a corrupt file is repaired by the next valid
   answer).
3. Two brokers on one machine: the file is per machine, so the broker that
   answered last wins, and the client speaks that room's language until the next
   answer. Accepted, as the card proposes. A per-agent value was rejected because
   half of the client's own messages (`status`, `install`, usage errors) have no
   agent to look it up by. The effect is at worst one message in the other room's
   language right after switching rooms.
4. What the client sends the broker to get `language` (checked against the code at
   the time): after task 02 only `GET /status` carries it, and only with
   `Accept: application/json` (answer `{"language", "text"}`). So `do_status` now
   sends that header, learns `language`, and prints `text` exactly as before. A
   response whose `Content-Type` is not JSON (an older broker) is printed raw and
   teaches nothing. Login, wait, inbox and say also call `learn_language(data)` on
   their JSON answer; it is a no-op until tasks 03-04 put `language` into those
   answers, and picks it up with no further change when they do. Non-dict answers
   (including `MagicMock`s in old tests) and non-`en`/`ru` values are ignored.
5. `fail()` through `speak`: `fail(message)` keeps its signature, because the
   existing callers pass literal Russian sentences that tasks 08, 09 and 11 move
   into the catalogue. It now prints `speak("failure_line", message=message)`, and
   `failure_line` is `AGENTSCHAT: {message}` in both languages, so the printed text
   is identical to before. Tasks 08/09/11 will pass `speak(...)` results to `fail`.
   If you want `fail(key, **params)` instead, it can only be done once the existing
   sentences are catalogued, so I left it to those tasks.
6. Where the code lives: language resolution is in a new module
   `bridge/sessionchat/client_language.py` (`valid`, `remembered`, `remember`,
   `RoomLanguage`), stdlib plus `i18n` only; `client.py` only gained `CATALOGUE`,
   `ROOM_LANGUAGE`, `speak`, `learn_language`, `status_text`, the `learn_language`
   calls, the `Accept` header in `do_status` and one line in `main`. Reason: SRP,
   and it keeps the `client.py` diff small for the parallel tasks 03 and 10. The
   card names `client.py` only; this is a small widening of the boundary.
7. `--lang` hook: `main()` does `ROOM_LANGUAGE.insist(getattr(args, "lang", None))`
   before running the command. Task 11 adds the `--lang` argument to `install` and
   `uninstall`; until then the attribute is absent and the hook is inert.
8. `speak` tests use a fake catalogue (patched onto `client.CATALOGUE`) with
   different English and Russian frames, because the real catalogue has one key
   whose two languages are identical on purpose.

## Added

- Keys (`bridge/sessionchat/client_messages/{en,ru}.json`): `failure_line`
  (`AGENTSCHAT: {message}`, same in both).
- `package-data` entry `client_messages/*.json` in `bridge/pyproject.toml`.
- Tests: `bridge/tests/test_client_language.py` (44 tests): speak, precedence table
  (10 rows plus invalid values), `main` handing over the flag, file creation /
  replacement / no rewrite / atomic failure / unwritable store / junk answers,
  corrupt file variants, `fail` output unchanged in both languages, unreachable
  broker English with nothing known and Russian after one `ru` answer, every
  command refreshing, `status` sending `Accept` and printing the text unchanged,
  the client catalogue under `CatalogueContract`. Every test redirects
  HOME/USERPROFILE and `client.STORE` to a temporary directory.
- Codes introduced: none.

## Edits to existing tests

None.

## Checks (from D:/AI/AgentsChat-wt/task-07/bridge, in order)

1. `unittest discover -s tests -t .`: Ran 1206 tests (1162 + 44), OK, 2 skipped.
2. `node --test tests/plugin/agentschat.test.mjs`: 4 pass, 0 fail.
3. `ruff check`: All checks passed.
4. `ruff format --check`: 54 files already formatted (I ran `ruff format` on my own
   new files and `client.py` first).

The real `~/.agentschat/language` does not exist before or after the full suite.
No live checks were run. The packaging test from task 01 was satisfied by the
`package-data` entry.

## Noticed, not touched

- Existing tests that reach `fail()` without patching `client.STORE` would read
  the real `~/.agentschat/language`. None does today (the install test patches
  `STORE`), and the frame is identical in both languages anyway.
- The reconnect line "подключена к комнате" is still the string the OpenCode
  plugin matches; task 12 owns it.
- `status` JSON handling is deliberately minimal; task 08 turns it into the
  machine-readable result.
- `client.py` has CRLF line endings; I preserved them. The new files are LF
  (as git normalises them).
