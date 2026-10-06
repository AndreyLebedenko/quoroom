# Report: task english-release-18 (docs/INSTALL.en.md)

Branch: task/english-release-18-docs-install-english (worktree D:/AI/AgentsChat-wt/task-18). Nothing committed. No code, script, catalogue or directory changed.

## What was created and changed

- New `docs/INSTALL.en.md`: the whole of `docs/INSTALL.md` in English, all sections (no split at the middle boundary). 33 headings, same numbering (0, 1.1-1.5, 2, 3.1-3.4, 4, 5.1-5.11) and the same unnumbered ones, in the same order. Anchor of the "end of file" link is `#5-manual-install-fallback`. Pointer on line 3: "Russian version: INSTALL.md".
- `docs/INSTALL.md` (Russian, CRLF kept): pointer "Английская версия: INSTALL.en.md" under the title, plus the in-step edits listed below.
- `README.md`: the four `docs/INSTALL.md` references (three in prose, one in the layout list) now point to `docs/INSTALL.en.md`; the layout bullet names the Russian version. The two lines added by task 19 (ARCHITECTURE.en.md, AGENTS_INTEGRATION.en.md) are untouched.
- `README.ru.md`: its INSTALL.md links stay; the layout bullet names `docs/INSTALL.en.md`.

## Edits to the Russian guide (all of them)

1. Pointer to the English version.
2. Task 05 (named by the story): the broker "ready" line in 5.9 is now `BROKER READY room=!AbCdEf...:agentschat.local port=8770` (matches `log.info("BROKER READY room=%s port=%s", ...)` in broker.py), in both guides.
3. Task 11 (named by the story/card): the participant section 1.1 says the kit language is the installer's `--lang`, not the room's, with the fix `agentschat install --lang <room language>`.
4. Beyond the named items, needed for the card's own requirement (the guide must say the room language is chosen once, the kit follows it, and how to change it): a new unnumbered subsection "Язык комнаты" / "Room language" after "Installer language", plus one sentence in 5.10 about `--lang` of `agentschat install`. The Russian guide did not have this text, so the English could not carry it alone and still be in step.
5. The "known limitation" paragraph (Russian block printed by `agentschat login`, to be fixed by `task-client-bilingual`) is replaced in both guides by one sentence: the kit's messages follow the run's language (installer passes its `--lang`). Reason below (finding 1).

## Findings: where the Russian guide disagrees with the code or other documents

1. **Stale limitation, replaced.** The Russian guide said `agentschat login` stays Russian inside an English run. After tasks 07-09 the client speaks the room language (explicit `--lang`, then the broker's answer, then the remembered `~/.agentschat/language`, then `en`; `client_messages/en.json` has the login lines). Carrying the sentence into an English public guide would have stated something false, so it was replaced, not translated. This is the one place where the translation is not a translation. Decision for the owner: accept, or revert in both guides.
2. **Kit language variants depend on tasks 13-15.** In this tree `bridge/sessionchat/kit/` has no per-language layout. The "Room language" text ("the kit is installed in the language given by `--lang`; changing the language later = edit the key, restart the stand, re-run `agentschat install --lang <new>`") follows the cards (18, 13 design point 3, the task 11 note) and is true only once 13-15 land. The statement that `agentschat install` replaces the kit files on re-run reuses the existing "skills and plugin are copies, `agentschat install` updates them" (section 2); I deliberately did not add the card-13 claim about hand-edited files. "Restart the stand" comes from ARCHITECTURE.en.md ("The broker reads the key at start").
3. **Task 11 findings 6 and 7 not carried out.** The client's own `install --json` and its exit code `5` (refused install) are still undocumented for a human; the card's boundary ("translated, not rewritten") and the brief did not allow new sections, so I left them. Section 5.10 does now mention `--lang`. Owner decision whether to add the `--json` / code `5` paragraph.
4. **README.md line 10** still says "the detailed documentation in docs/ is written in Russian". Left (task 20 owns what the README says about Russian documents); it is now partly untrue for INSTALL, ARCHITECTURE and AGENTS_INTEGRATION.
5. **Nothing re-verified.** Statements the Russian guide makes without live proof stay that way: the Linux scenario and browser trust of the certificate on a Linux desktop are "not tried / unverified"; the Windows path is "done by hand on 5 October 2026". `CAROOT` renewal date, `RENEWAL.md`, `register_account.py` flags, the `0xC000013A` Ctrl+C code, `docker image rm <image>` in the removal report were translated as written and not checked against code.

## Places with two readings (translation choices)

- "снятие" = removal, "очистка" = purge (matching the installer's `--remove` / `--purge`), "набор" = kit, "стенд" = stand, "листовые сертификаты" = leaf certificates.
- "уже верное помечается «уже сделано»" is rendered as `marked "already done"`, which is the installer's English line `{step}: already done.` (en.json `steps.already_done`).
- Placeholders inside commands cannot stay byte-identical: `/путь/к/Quoroom` -> `/path/to/Quoroom`; `<ваш логин в Element>` -> `<your Element login>`; `<токен из лога>` -> `<token from the log>`; the server's line `<выданный-сервером-токен>` -> `<token-issued-by-the-server>`; the chat message `привет, представься одним предложением` -> `hi, introduce yourself in one sentence`. Everything else in code blocks is byte-identical outside comments (checked by script).
- The Ubuntu comment that quotes the installer's mkcert line now reads `CAROOT="<path>" mkcert -install (as root)`, which is `server.trust_command_linux` with `{caroot}` as `<path>`.
- `SESSION_BRIDGE.md` is linked as "(in Russian)" in the English guide (an addition, true, helps a reader who lands in it); `start.ps1` / `stop.ps1` link goes to `../README.md`.
- "Нативная Linux-машина в проекте не проверялась, живой сценарий Linux не выполнялся (путь для Windows человек прошёл вручную 5 октября 2026)" is kept as one sentence with its parenthesis; it reads awkwardly in Russian too.
- The new English file has LF line endings; the working copy of the Russian one is CRLF. `.gitattributes` has `text=auto`, so the index is LF either way.

## Checks

Run from `D:/AI/AgentsChat-wt/task-18/bridge`, one after another:

| Check | Result |
|-------|--------|
| `.venv/Scripts/python.exe -m unittest discover -s tests -t .` | Ran 1598 tests, OK (2 skipped) |
| `node --test tests/plugin/agentschat.test.mjs` | 28 pass, 0 fail |
| `ruff check` | All checks passed |
| `ruff format --check` | 66 files already formatted |

Script checks on the documents (script in the scratchpad, not in the repository):

- non-ASCII characters in `INSTALL.en.md`: 0;
- headings: 33 in each, identical numbering and order;
- code blocks: 30 in each; after removing comments, every block is identical except the five placeholder / chat-message differences listed above;
- quoted installer text: `already done` and `CAROOT="{caroot}" mkcert -install (as root)` are present in `installer/messages/en.json`; the other installer behaviours the guide describes are prose, not quotes. The broker line matches `broker.py`.

No live check was run.
