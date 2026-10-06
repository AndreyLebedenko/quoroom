# Report: task-local-installers-04-linux-container

**Branch:** `task/local-installers-04-linux-container` (from `feat/local-installers`)
**Base commit:** 8a81444
**Status:** third pass after review round 2, implemented and verified functionally,
not committed, no live browser check.

Every row of the verification table below was produced by running the code as it
stands now, after the last edit.

## Review round 2, item by item

**N1. A custom scenario ran nothing and returned 0.** The dispatcher passed only
the name, while the runner read the command from the second argument, so
`in_machine ""` was a no-op. `run_command` now falls back to the name:
`in_machine "${command:-$name}"`. Verified: `./run.sh scenario 'echo
ARBITRARY_RAN; exit 3'` printed `ARBITRARY_RAN` and returned `3`.

**N2. The 443 guard stopped refusing.** Windows `netstat -an` prints
`... 0.0.0.0:443 0.0.0.0:0 LISTENING`, so the old `LISTENING.*:443 ` pattern
never matched, and the early `return` kept the Docker-ports fallback from ever
running. The guard is now three independent checks with no early return:
`netstat -an | grep -Eq ':443[[:space:]].*LISTEN'`, `ss -ltn | grep -Eq
':443[[:space:]]'`, and finally `docker ps --format '{{.Ports}}' | grep -q
':443->'`. Verified **with a docker shim that fails any state-changing call**, so
a broken guard could not have reached a real `up`: with the Windows caddy holding
443, `PATH=<shim>:$PATH ./run.sh up --publish-443` returned 9 with
"ОШИБКА: порт 443 на хосте уже занят", the shim never fired (`ЗАГЛУШКА` count 0),
and no lab resource was created.

**1. The CR check was a bashism.** `$'\r'` is literal under dash, so the check
tested nothing. It is now `grep -q "$(printf '\r')"`. Verified both ways: a CRLF
file planted into the copy makes `verify-copy` exit 1 with "CR ОСТАЛСЯ в файле,
который git отдаёт как w/crlf"; after `down` and a fresh `up`, the same scenario
passes with "в файле, который git отдаёт как w/crlf, нет ни одного CR".

**2. `exec` broke on commands starting with `/`.** Git Bash rewrote
`LAB_COMMAND=/home/...` into `C:/Program ...`. `MSYS_NO_PATHCONV=1` is now set on
the `docker compose exec` inside `exec_in_machine` (and on the `shell` exec).
Verified: `./run.sh exec 'ls /home/lab/repo/install.sh'` printed the path with exit
0, and `./run.sh exec '/bin/echo ABSOLUTE_OK'` printed `ABSOLUTE_OK`.

**3. `exec-root` added**, scoped like `dc` and needed by task 06 for the human
steps it must perform as root. Verified: `./run.sh exec-root 'id -un; grep -c
"127.0.0.1" /etc/hosts'` printed `root` and `1`, exit 0. The machine still has no
`sudo`.

**4. The "after" snapshot is now taken after the teardown.** It moved into the
`EXIT` trap, so it prints on every exit path, failure included, and after
`down -v`. Verified: the snapshot that follows a scenario contains zero
`quoroom-linux-lab` resources.

**5. `teardown` no longer hides failures.** On a failing `down -v` it prints
"ВНИМАНИЕ: окружение убрать не удалось:", the failing output, and the leftover
containers, volumes and networks. Verified with a docker shim that fails
`compose down` while the lab was up: the warning and the leftover
`quoroom-linux-lab-dind-1` were printed; a real `down` afterwards left 0 resources.

**6. Comments.** The comment that restated the code is gone. The workaround note
now says the truth: Cyrillic passes through `-e` intact (checked, `CYR_OK`), the
real problem is paths starting with `/`.

**7. `compose.yaml` ends with a newline** - the last byte is now `0x0a`.

## What was run in this round, on the final code

| Run | Result |
| --- | --- |
| `scenario 'echo ARBITRARY_RAN; exit 3'` | printed `ARBITRARY_RAN`, exit 3 |
| snapshot printed after teardown | 0 lab containers, volumes, networks |
| `up --publish-443` with the docker shim, caddy on 443 | exit 9, shim never fired, no lab resource |
| CRLF file planted into the copy, then `verify-copy` | exit 1, "CR ОСТАЛСЯ" |
| fresh `up`, then `verify-copy` | exit 0, "нет ни одного CR" |
| `exec 'ls /home/lab/repo/install.sh'` | exit 0, path printed |
| `exec '/bin/echo ABSOLUTE_OK'` | `ABSOLUTE_OK`, exit 0 |
| `exec-root 'id -un; grep -c "127.0.0.1" /etc/hosts'` | `root`, `1`, exit 0 |
| `down` with a docker shim failing `compose down` | warning plus leftover container listed |
| real `down` afterwards | 0 lab resources |

Earlier rounds' results still hold and were re-run where the code changed:
`verify-shared-home`, `verify-copy` (139 files, owner `lab`, no ignored secrets,
no CR, uid 1001, no sudo), `install-help`, the forced preparation failure (exit 1,
zero lab resources), the refusal while a lab is live (exit 9), the second `up`
over a corrupted copy, and `room-helper.py` refusing on the host.

## The host's live stack was never touched

Snapshots of `docker ps -a`, `docker volume ls` and `docker network ls` before the
first run of this round and after the last:

- volumes 14 -> 14, `Compare-Object` zero differences;
- networks 7 -> 7, zero differences;
- `agentschat-caddy`, `agentschat-element`, `agentschat-continuwuity` still running
  with the same ports;
- no `quoroom-linux-lab` container, volume or network remains.

## Decisions

- **The guard checks three sources and never returns early**, because the source
  that answers differs by platform, and a silent "no listener found" is exactly
  the failure that would let a publication through.
- **The verification of a failing guard uses a docker shim**, so proving the guard
  cannot start a real stack. Anything else would risk the host's 443.
- **`exec-root` exists rather than a sudo in the machine**: task 06 must perform
  the hosts entry and `mkcert -install` as root, and the runner must be the only
  thing that touches `docker compose`.
- **The after-snapshot lives in the trap**, because a snapshot taken before the
  teardown always shows the lab's own resources and proves nothing.

## What is not verified here

- The live browser scenario (human-driven).
- The server stack started inside dind by tasks 05-07.
- `room-helper.py` against a real Matrix server: it needs an installed server role
  with a registered human account (task 06); only its refusal outside the lab is
  verified.
- The hosts check and browser certificate trust on a Linux desktop, as the story's
  gate item 1 already records.

## Verification, run from `bridge/` in order

- `.venv/Scripts/python.exe -m unittest discover -s tests -t .` - Ran 346 tests,
  OK, 1 skipped (`pwsh` absent, reason stated).
- `node --test tests/plugin/agentschat.test.mjs` - tests 4, pass 4, fail 0.
- `.venv/Scripts/ruff.exe check` - All checks passed.
- `.venv/Scripts/ruff.exe format --check` - 35 files already formatted.

`room-helper.py` lives outside the bridge package, so it was checked with the same
ruff explicitly; it is clean. The three shell scripts were checked with `sh -n`
under Git Bash.