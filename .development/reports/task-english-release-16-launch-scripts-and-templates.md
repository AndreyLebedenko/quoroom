# Report: task english-release-16, launch scripts and configuration templates

Branch: task/english-release-16-launch-scripts-and-templates. Nothing committed.

## What changed

- `start.ps1`, `stop.ps1`, `start.sh`, `stop.sh`: every user-visible line comes from a
  message table per language (Russian, English) and is printed in the room language.
- `docker/.env.example`, `docker/continuwuity/continuwuity.toml.example`,
  `docker/caddy/Caddyfile`, `docker/docker-compose.yml`: Russian comments replaced by
  English ones. No key, value or non-comment line changed.
- `docs/INSTALL.md`: one bullet in "Дальнейшие шаги" (Russian, like the rest of the guide)
  saying how the scripts pick the language.
- New tests: `bridge/tests/test_launch_scripts.py` (29), `bridge/tests/test_configuration_templates.py` (17).

## How the scripts choose the language

1. `--lang en|ru` or `--lang=en|ru` from the arguments, when given. A given flag is
   authoritative: any value other than the exact string `ru` (including `RU`, `xx`, empty,
   `--lang` with no value) prints English and does not fall back to the config.
2. Otherwise the first top-level line `language:` of `bridge/config.yaml`, when the file
   exists. One line is selected and read (`Select-String` / `sed`); nothing else of the file
   is read into a variable or printed (the tests plant a token in the config and assert it
   never appears in the output). The value is cut at ` #`, trimmed, and one pair of
   matching quotes is removed (what the YAML loader would give for the same line).
   An indented `language:` (a nested key), `RU`, an empty value or any other word gives English.
3. Otherwise English.

Same rule as the broker's strict `en`/`ru`, except that a bad value does not stop the
script: a launch script that refuses to run over a typo would be worse than English output.

## Decisions and reasons

1. PowerShell scripts lost `[CmdletBinding()]` and scan `$args` for `--lang`, the pattern
   of `install.ps1`. With `[CmdletBinding()]` an unknown positional `--lang` is a binding
   error, and `-Lang` would not match the flag the installer wrapper and the kit use.
   Consequence: an unknown argument is now ignored instead of rejected, and the common
   parameters (`-Verbose` etc.) are gone. `-Logs` and `-KeepDocker` work as before.
2. `start.ps1` and `stop.ps1` now carry a UTF-8 BOM (`install.ps1` already does). Without
   it Windows PowerShell 5.1 reads the file in the system ANSI code page, and the Russian
   table would print as mojibake on a machine whose ANSI page is not UTF-8. On this machine
   the ANSI page is 65001, so a test cannot show the difference here; the BOM is kept as
   the safe choice (a test asserts it).
3. A blank line after `#Requires` in both `.ps1`: without it `Get-Help` does not see the
   comment-based help (checked on PowerShell 5.1).
4. Comment-based help: English, with real `.SYNOPSIS` / `.DESCRIPTION` / `.PARAMETER` /
   `.EXAMPLE` keywords. `Get-Help` has no language, so English is the only choice that fits
   the default; the Russian explanation lives in `docs/INSTALL.md`. A test runs
   `Get-Help -Full` on both scripts and asserts English text and no Cyrillic.
5. Inline comments in the four scripts were deleted (AGENTS.md rule 7, and the old ones were
   Russian). The `.sh` scripts keep a short English header (usage, language rule, "not
   verified live on macOS/Linux"): it is their equivalent of the PowerShell help. The stale
   `# shellcheck disable` line in `stop.sh` was dropped with the other comments.
6. `stop.sh` now treats `--keep-docker` as a flag anywhere in the arguments (it used to look
   at `$1` only), so `--lang ru --keep-docker` works. `$1 = --keep-docker` behaves as before.
7. English text follows the installer's wording where the sentence is the same
   ("Next, call /chatlogin in each CLI session. To stop everything: ...").
8. The labels (`ОШИБКА` / `ERROR`, `ПРЕДУПРЕЖДЕНИЕ` / `WARNING`) are part of the language
   switch, not of the message tables' sentences. Exit codes and behaviour are untouched
   (verified by tests on every refusal path: exit 1).

## Message table

Lines per language (Russian = English count; labels excluded):

| Script | Messages | Notes |
|---|---|---|
| `start.ps1` | 18 | 7 refusals, progress, 2 warnings, 2 final lines, log follow |
| `stop.ps1` | 8 | 2 warnings |
| `start.sh` | 11 | plus `error_label` |
| `stop.sh` | 7 | the warning carries its label inside the sentence, as before |

Total 44 per language. The Russian strings were compared mechanically with `git show HEAD:`
of each script (placeholders normalised) and are identical. `MessageTableTests` pins every
Russian string as a literal, so any edit to `ru` fails a test; it also checks identical
key sets and placeholder sets, no Cyrillic and only printable ASCII in the English tables.

## Tests

`test_launch_scripts.py`:
- tables: Russian pinned, parity of keys and placeholders, English ASCII-only (4 tests);
- script text: BOM, no PowerShell 5.1-incompatible construct, Cyrillic only inside the
  Russian table, comments only in the help/header, valid POSIX sh with no bashism (7);
- `start.ps1` driven through a caller that shadows `docker`, `Start-Sleep`, `Start-Process`
  and `Get-CimInstance` with functions (functions defined by the caller are visible to the
  script it invokes, so no real Docker, broker or process scan is touched; `Start-Process`
  throws if reached). Each refusal in English by default and in Russian on request; the
  language matrix (23 flag/config combinations); the "broker already running" progress run
  (ordered lines);
- `stop.ps1` the same way: the matrix (6 combinations), a real sacrificial Python process
  stopped through its pid file, `docker compose down` failure as a warning, missing docker
  as a warning with exit 0;
- `start.sh` / `stop.sh` with a fake-PATH (shims for `docker`, `curl`, `pgrep`, `python3`):
  refusals, the matrix (23 combinations for `start.sh`, 23 for `stop.sh`), exact output of a
  fresh start and of an "already running" start (a wrapper writes its own `$$` as the pid),
  a live pid-file stop, `down` failure as a warning, flag order for `--keep-docker`;
- `Get-Help` is English.

`test_configuration_templates.py`: no Cyrillic and only printable ASCII in the four
templates; the installer's own extractors (`toml_value`, `TOML_KEY`, `toml_place`, `IMAGE`,
the `SERVER_NAME=` rule) return the same keys and values from each template; the toml parses
with `tomllib` to exactly `{global: {allow_registration, registration_token}}`; the compose
file parses with PyYAML to the same services, environment, ports, mounts and volumes; the
Caddyfile directives are pinned. The same extractors were also run by hand against the
`HEAD` versions of the templates: identical output.

Not tested behaviourally (needs real port 8770 free, a real 443, or a long wait):
the "broker exited at startup", "broker ready" and "port did not open" lines of
`start.ps1`, `-Logs`, and the "found by command line" line of the stop scripts. They are
covered by the pinned tables only.

## Edits to existing tests

None. No existing test ran these scripts or read the changed comments; no test expectation
was touched.

## Checks (from D:/AI/AgentsChat-wt/task-16/bridge, in order)

1. `unittest discover -s tests -t .`: Ran 1252 tests (1206 baseline + 46 new), OK, 2 skipped.
2. `node --test tests/plugin/agentschat.test.mjs`: 4 pass, 0 fail.
3. `ruff check`: All checks passed.
4. `ruff format --check`: 56 files already formatted.

No live checks (Docker, real stack) were run.

## Noticed, not touched

- The server installer runs `start.ps1` / `stop.ps1` (and the `.sh`) without `--lang`. The
  scripts then use `language:` from `bridge/config.yaml`, which the installer writes from its
  own `--lang` when it creates the file. If `config.yaml` already existed without a
  `language:` key and the installer is run with `--lang ru`, the scripts still print English.
  Passing `--lang` through is a one-line change in `installer/server.py` (`StartStep.argv`,
  the stop argv), outside this card.
- `winstart.ps1` (not in scope) has Russian text and is the one place a person double-clicks.
- Tests for the ready/exited/no-port progress lines would need an injectable port for the
  scripts; adding one would change script behaviour, so it was not done.
