# Report: task english-release-19 (architecture and integration guides in English)

Branch: task/english-release-19-docs-architecture-integration-english (worktree D:/AI/AgentsChat-wt/task-19). Nothing committed. No code, script or catalogue changed.

## Created and changed

- New `docs/ARCHITECTURE.en.md` (translation of `docs/ARCHITECTURE.md`, same sections in the same order, plus the new "Contracts" section).
- New `docs/AGENTS_INTEGRATION.en.md` (translation of `docs/AGENTS_INTEGRATION.md`, plus the new "Contracts" section at the end).
- `docs/ARCHITECTURE.md`: one pair line ("Английская версия: ARCHITECTURE.en.md") and the same "Контракты" section, in Russian, inserted before "Безопасность и секреты". Nothing else touched.
- `docs/AGENTS_INTEGRATION.md`: a pair line, one sentence added to the "Отменено" banner ("the Контракты section at the end describes the current client and is not cancelled"), and the "Контракты" section appended at the end.
- `README.md`: the `docs/ARCHITECTURE.md` bullet now points to `docs/ARCHITECTURE.en.md`; a new bullet for `docs/AGENTS_INTEGRATION.en.md`. `README.ru.md`: the ARCHITECTURE bullet extended with the contracts, a new bullet for `docs/AGENTS_INTEGRATION.md`.
- Layout follows the owner decision: new `.en.md` files beside the Russian ones; the Russian files stay. CRLF working-copy endings preserved in the four edited files; new files are LF.

## Split of the contracts between the two documents

ARCHITECTURE (broker side): the one rule (a boundary message carries a code, the sentence is rendered only by the human/agent-facing component), room language, broker refusal body and the code table (code, status, when, params), answers of `say` / `inbox` / `status` (including `warning_code`, `note_code`, the `/status` shape), envelope `kind`, and a pointer to the result line.
AGENTS_INTEGRATION (client side): room language as the client sees it, the `AGENTSCHAT-RESULT` line in full (format, key order, ASCII, "read the LAST line with the prefix" and why, stdout/stderr, exit codes, keys per command, the code table, the OpenCode plugin as a reader), the `wait` frame and the `/wait` answer with `kind` and `rendered`. Both Russian and English carry the same text.

Contracts documented (all from reports 02, 03, 04, 06, 08, 09, checked against the code):
- `language: en|ru` in `bridge/config.yaml`, one per room, default `en`, strict values, English refusal at start, `language` field in answers of login / wait / say / inbox / status.
- error body `{"code","message","params"}`, statuses unchanged; codes `unknown_agent` 404, `reconnect_without_registration` 409, `reconnect_token_mismatch` 409, `slot_taken` 409, `slot_in_store` 409, `session_not_registered` 409, `empty_message` 400, `depth_limit` 403, `rate_limit` 429; `unknown_delivery` as a startup refusal without status.
- `/status` states `listening`, `processing`, `not_listening`, `not_connected`; `warning_code` `unaddressed`, `note_code` `addressed_to_person`.
- envelope `kind` = `human` / `agent`; `rendered`; `envelope_without_text`; first envelope line.
- `AGENTSCHAT-RESULT`: login has `mode` and `reconnected` (no session id), say/ask fields (`event_id`, `warning`/`note`, `answered`), client codes `broker_unreachable`, `not_logged_in`, `broker_refused`, `nothing_to_send`, `envelope_without_text`, `unexpected_answer`; `wait`/`inbox` print no line; the `=== AGENTSCHAT: ... ===` frame prefix is code, the title is catalogue text.

## Reports against code

No disagreement found. I checked: refusal codes and statuses and params in `broker.py`, `/status`, `say` answer fields, `language` in login / wait / say / inbox / status answers, `KINDS`, `Envelope.as_dict`, `client_result.line`, the client code constants. Also consistent with the paragraphs already in `docs/SESSION_BRIDGE.md`. One observation, not a disagreement: report 08 lists `reconnect_*`, `slot_in_store` etc. as codes of the login refusals; they are broker codes forwarded by the client, and the documents say so.

## Translation spots with two readings

1. The Russian ARCHITECTURE "Установщик" text has a line break inside a quoted question; translated as `"is this already done?"`.
2. AGENTS_INTEGRATION says `--bare` "is not used in the working configuration" and then continues as if it were. Translated as it stands, not reconciled.
3. "Не проверено нами вживую" kept as "was not verified live by us"; "подтверждено" kept as "confirmed"; "Проверено с CLI 0.153.4" as "Verified with CLI 0.153.4". Nothing strengthened.
4. Config/identifier examples that contain Russian words: `aliases: ["все", "агенты"]` became `aliases: ["all", "agents"]` ("all, status?"); `@<ваш логин>:...` became `@<your login>:...`; `~/.quoroom/installer/<роль>.json` became `<role>.json`. These are placeholders or sample values, not commands.
5. Box-drawing characters in the installer diagram replaced by ASCII (`--+`, `+-->`), the multiplication sign in `bridge (x3)` by `x`.
6. The Russian doc has a mixed-script typo in the mermaid label ("упоminание"); left alone in Russian, translated as "mention" in English.
7. The wait frame titles are quoted in English in both documents' contracts; the Russian doc also quotes the Russian titles, the English doc says "different words with the same meaning" instead of quoting Cyrillic. Same for the Russian first line of the envelope.

## Decisions for the owner

1. Commands are byte-identical to the Russian ones, as required. Two of them contain Russian test prompts (`"напиши файл test.txt с текстом hi"`, `"тест"`) and one quoted bridge message `"(ошибка запуска ...)"` stays Russian with an English gloss added in parentheses. The glosses are my additions. If you prefer English prompts, it is a three-place edit.
2. `ARCHITECTURE.en.md` links to `INSTALL.en.md` (task 18's file). It does not exist in this tree; the link is dead until task 18 merges. If task 18 chooses another name, one link changes.
3. Merge note: `README.md` and `README.ru.md` bullets I edit sit directly under the `docs/INSTALL.md` bullet that task 18 will edit; expect a textual conflict in that hunk.
4. `AGENTS_INTEGRATION.md` is cancelled apart from the new section; I added one sentence to its banner so a reader does not stop at "Отменено". Revert that sentence if you want the banner untouched.

## Checks (from D:/AI/AgentsChat-wt/task-19/bridge, in order)

1. `unittest discover -s tests -t .`: Ran 1574 tests, OK, 2 skipped (baseline).
2. `node --test tests/plugin/agentschat.test.mjs` (alone): 28 pass, 0 fail. No process killed.
3. `ruff check`: all checks passed (via the shared venv, `python -m ruff`).
4. `ruff format --check`: 66 files already formatted.
5. Script, ASCII punctuation: the two new English files contain no dashes, curly quotes, ellipsis characters, arrows, check marks, non-breaking spaces; `ARCHITECTURE.en.md` has no non-ASCII character at all; `AGENTS_INTEGRATION.en.md` has Cyrillic only on three lines (the two commands and the quoted bridge message above).
6. Script, commands: all four fenced blocks of AGENTS_INTEGRATION are identical in both languages; every inline code span without Cyrillic in the Russian files is present in the English files (whitespace-normalised, multi-line spans included); the only differences are the `.en.md` file names and the placeholders listed in point 4 of the translation spots.
7. Line endings of the four edited files are pure CRLF; `git diff --check` clean.

No live checks were run.
