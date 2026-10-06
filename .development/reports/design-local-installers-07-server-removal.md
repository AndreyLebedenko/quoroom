# Design sketch: task local-installers-07, server removal

**Status:** approved with decisions on 2026-10-04; the decisions below are part
of it. Stage 2 in progress on `task/local-installers-07-server-removal` from
`feat/local-installers`.
**Replaces:** the `--role server --remove` stub, which today raises "not
implemented" from `report()` (`server.py:1129-1134`) and exits 1.

Task 06 left removal out on purpose: its report says so
(`task-local-installers-06-server-install.md`). This card fills that hole, and
the card's own split is what the whole design follows:

- **remove** stops the stand, removes the containers and network, and removes
  `bridge/.venv` **only if the installer created it**. Volumes, configuration,
  credentials and certificates stay. Pulled images stay.
- **purge** additionally removes the stack's named volumes (the room history),
  `docker/.env`, `continuwuity.toml`, `config.yaml`, the broker state under
  `bridge/state/`, the saved bot passwords and the leaf certificates.
- The mkcert root CA and the hosts entry are never touched; the report says they
  remain and how to remove them by hand.

## What the existing machinery already gives us

The core was built for this card and is unchanged by it:

| Piece | Where | What it decides |
| --- | --- | --- |
| `OwnedStep(name, role, kind, delete=unlink)` | `steps.py:74-95` | targets come only from `of_kind(role)`, so **only recorded** resources are ever deleted; `apply` forgets each id as it deletes it |
| `FoundStep(name, role, kind, found)` | `steps.py:98-132` | targets are discovered minus anything in `run.records`; used for data nobody recorded (the participant's session tokens) |
| `approved()` / `unapproved()` | `steps.py:62-71` | without `--purge` every target is approved (plain `--remove` asks nothing); with `--purge` only what the human confirmed is deleted, and the rest is reported as kept |
| `Confirmation.ask` | `confirmation.py:17-23` | one typed word (`PURGE`), no flag skips it. It reads a line without asking for a tty, so a piped `PURGE` does confirm; only an empty line or EOF cancels. That is not a guarantee to write down anywhere |
| `Role.__post_init__` | `roles.py:51-62` | a purge step that does not declare targets is a `TypeError`; a **remove** step that is a `FoundStep` is a `TypeError` (a custom step that discovers something is not caught, which is why the stop step is its own class) |
| `steps_for` / `destructive` | `roles.py:64-79` | `--remove` yields `remove`; `--remove --purge` yields `remove + purge`, and the confirmation list is built from `remove + purge` of every selected role **before any step runs** (`main.py:54-56`, `main.py:95-101`). Under `--purge` the venv step is destructive too, so the venv appears in the PURGE question; plain `--remove` asks nothing |
| `REMOVE_ORDER = ("participant", "server")` | `roles.py:12`, applied by `roles.order` (`options.py:77`) | `--role both` removes the participant first; not a decision of either role |
| `Ownership.save` | `ownership.py:49-57` | an empty record deletes its own file, so forgetting the last entry removes `~/.quoroom/installer/server.json` by itself; the directories above it are pruned by the step that empties it |

`main.py` exit codes: 0 done, 1 failed, 2 usage, 3 human step, 4 cancelled. A
failed run prints `Failure.render` and **no report** (`main.py:63-66` returns
before `main.py:67-71`), so anything the human must read after a failure has to
be in the failing step's own text.

## Step 1. Decisions

1. **Stopping is two steps, because the project identity must stay in one
   place.** The broker is stopped by the human's own script -
   `stop.ps1 -KeepDocker` / `stop.sh --keep-docker` - run in file-output mode
   like `StartStep` (`stop.ps1` writes with `Write-Host` in the console code
   page, and a pipe is decoded strictly, so a file with `errors="replace"` is
   the safe shape), and its exit code is meaningful on Windows, where 1 means a
   terminating error such as access denied. Then the broker is polled on
   `/status` with the injected sleep until it is silent: `stop.sh` sends SIGTERM
   and does not wait (`stop.sh:20`), and aiohttp can answer for a moment after.
   The stack is taken down by `compose_argv(run, "down")` - no `-v`, the same
   identity `up` used, a real exit code and compose's own stderr through
   `compose_failure`. The earlier draft's premise ("delegating to the scripts
   keeps one definition of the project") was wrong: the installer already
   addresses the project through `compose_argv` for `up`, `restart`, `logs` and
   the volume snapshot, and a bare `docker compose down` inside `docker/` is
   exactly the second identity - it honours `COMPOSE_FILE` from the environment
   or `docker/.env`, which `-f` does not. Only the broker's stopping needs the
   script: the pid file plus the command-line fallback has no equivalent in the
   standard library. Its fallback kills any `sessionchat.broker` on the machine,
   which on one machine with a fixed port 8770 is the one we mean; the report does
   not claim more.
2. **A daemon that is down is reported, not a reason to refuse deleting files.**
   Plain `--remove` warns that the containers could not be checked and
   continues. `--purge` deletes everything it can and only then fails on the
   volumes, so the human's promise is never silently unkept - and **the volume
   step is last**, which is what makes that possible: the file steps run first,
   and `execute` stops at the first failure (`steps.py:211-216`). A test pins the
   order.
3. **When the daemon is down and the stack's containers were not removed, purge
   does not delete the files that the compose file mounts.** Containers carry
   `restart: unless-stopped` (`docker-compose.yml:7`, `:32`, `:43`), so they come
   back with the daemon, and Docker creates a missing bind source as a
   directory - `docker/continuwuity/continuvuity.toml` can come back as a
   directory and break the next install. So with the stack still up, `continuwuity.toml`,
   both certificates and everything else the compose file mounts stay;
   `config.yaml`, the saved passwords, the broker state and the venv still go.
   The failing step's text names what was kept, why, and that a repeat after
   starting Docker finishes the job. The core is not changed for this.
4. **A resource that is already gone counts as deleted.** A repeat, or a
   volume the human removed with `compose down -v` or a Docker Desktop reset,
   must not fail forever: the volume step asks `docker volume inspect` first,
   and the venv step skips `rmtree` when the directory is absent. Both forget
   the entry.
5. **The venv must not be held by the installer itself.** `install.ps1` tries
   `py -3` first (`install.ps1:36-39`), so with `bridge/.venv` activated and no
   py launcher the running interpreter is inside the directory we are asked to
   delete. The venv step refuses with a human step naming the cause (deactivate
   the venv and repeat); the entry stays recorded, so the repeat finishes it.
6. **Broker state is found, not recorded** - the orchestrator's decision. The
   broker creates `bridge/state/agentschat.db` and the start scripts write
   `bridge/state/broker.pid`; the installer never writes either, so it cannot
   honestly record them. It may delete them **only if `continuwuity.toml` is in
   the server's ownership record**: that file is written by the installer's
   `TomlFileStep`, so its presence proves this server was set up here. On a
   hand-built machine the discovery answers empty and the report names the files
   with that reason. This is gate item 4: what existed before the installer's
   first run is validated and reused, never adopted. Known limit, recorded and
   not fixed here: a regenerated `continuwuity.toml` over old volumes and an old
   database would pass the gate.
   Discovery is an **allow-list** of the broker's own files - `agentschat.db`
   with its `-wal`, `-shm` and `-journal` siblings, and `broker.pid` - minus
   `server-accounts.json` by name *and* by recorded path (the passwords are the
   last step's recorded target; listing them twice would delete them twice).
   `FoundStep` subtracts only the record **files** (`run.records`), not the
   entries inside them, so every exclusion is explicit inside `found`. A test
   pins that the broker-state step runs *before* the step that forgets
   `continuwuity.toml`: reordering them silently turns the gate off.
7. **`bridge/logs/` and `bridge/broker.log` stay.** The start step writes
   `bridge/logs/start.log` and the start scripts write `bridge/broker.log`;
   neither is in the card's lists, so neither is a target. The report names both
   with the command that removes them.
8. **On a hand-built machine the stack is still taken down.** The containers and
   the network are removed even when nothing is recorded: the card and story
   gate item 6 require it, they are not data, and `start` recreates them. This is
   a deliberate exception to "only recorded resources are removed", and the
   report says so, together with everything that was left and why:
   `continuwuity.toml`, the broker state (with decision 6's reason), the
   passwords file and the volumes.
9. **What the confirmation says.** Both roles' consequence text is a function of
   the run's own targets, so the question never promises what the run will not do.
   The server says the room history is destroyed only when a volume is among the
   targets, and otherwise says the files are gone and the room stays. The
   participant says the room history stays unless the server is being purged in
   the same run. `Role.purge_consequence` takes the target list and
   `consequence_of(roles, targets)` gets the targets already collected by
   `main._targets`; that is the one core change this card needed. The volume
   names in the report come from the compose file's declarations when the daemon
   is unreachable, not from `docker volume ls`.

## Step 2. The steps, in order

### remove (no confirmation is asked for any of these)

| # | Step | check says done when | apply does |
| --- | --- | --- | --- |
| 1 | "Остановить брокер и стенд" | the broker does not answer `/status` **and** either the daemon is unreachable (with a warning) or `docker compose ps -a -q` is empty | the platform stop script with the keep-docker flag, in file-output mode; a nonzero exit is a failure naming the script's last line; then poll `/status` until silent with the injected sleep (decision 1); then `compose_argv(run, "down")`; a daemon that is down is a warning, any other `down` failure is a failure; then verify `ps -a -q` is empty |
| 2 | "Убрать bridge/.venv" | the record has no `venv` entry, or the directory is gone | refuse as a human step when the running interpreter is inside it (decision 5); otherwise `shutil.rmtree` when present, then forget the entry |

**What remove deliberately leaves**, each named in the report with the command
that would purge it: the three volumes, `docker/.env`,
`continuwuity.toml`, `bridge/config.yaml`, the two leaf certificates, the saved
bot passwords, the broker state, `bridge/logs/start.log`, `bridge/broker.log`,
the mkcert root, the hosts line and the pulled images. That is the card's list,
and it is also what makes remove cheap enough to run twice.

### purge (each step's targets must be confirmed first)

| # | Step | check says done when | apply does |
| --- | --- | --- | --- |
| 3 | "Удалить состояние брокера" | discovery is empty | `FoundStep` over the allow-list, gated on `continuwity.toml` being recorded (decisions 6) |
| 4 | "Убрать конфигурацию стенда" | the record has no `file` entry | delete the recorded files of `FILE_KIND` - `.env`, `continuwuity.toml`, `config.yaml` - skipping the ones the stack still mounts while the daemon is down (decision 3), and forget those deleted |
| 5 | "Убрать сертификаты" | the record has no `cert` entry | same gate as step 4 for the two leaf files; the CA root is not ours and stays |
| 6 | "Убрать сохранённые пароли" | the record has no `passwords` entry | delete `bridge/state/server-accounts.json`; the accounts on the server go with the volumes of step 7, and the report says so |
| 7 | "Удалить тома стенда" | the record has no `volume` entry | `docker volume rm` per recorded id, an already absent one counting as done (decision 4); a daemon that is down or a volume still in use is a failure naming the returned line and what is kept |

After the last forget the record is empty and `Ownership.save` removes
`~/.quoroom/installer/server.json`; the step that empties it prunes
`~/.quoroom/installer` and `~/.quoroom` when they are empty, the way the
participant role does. No step forgets an id it did not delete.

### Why this order

- The stand is down before anything a container mounts is touched.
- The broker-state step runs before any step forgets `continuwity.toml`, because
  that record entry is the gate it reads (decision 6); a test pins the order.
- Volumes last: a file deletion never needs the daemon, so a daemon that is down
  costs the human the volumes and nothing else, and the failure text says what a
  repeat finishes. A test pins that the volume step is the last one.

## Step 3. Edge cases

| Situation | Behaviour |
| --- | --- |
| partial install (the run stopped at step 7 of 18) | every recorded entry is still removed; steps whose `check` finds nothing are "уже сделано". A venv created before the failure is recorded (step 6 records before pip) and goes with it |
| repeat of `--remove` | idempotent: the record is empty, the stop script reports "Брокер не запущен" and `down` is a no-op, both steps say "уже сделано", exit 0 |
| repeat of `--purge` | same, plus the confirmation is asked **only if** something is left; with an empty record the target list is empty and `Confirmation.ask` is never called |
| a volume or the venv was removed outside the installer | counts as deleted and forgotten (decision 4), so the record can still empty |
| the confirmation is refused | `Cancelled` before any step runs (`main.py:57-59`), exit 4, `Отменено человеком, ничего не изменено.`, and the record and every file byte-identical |
| the daemon is not running, `--remove` | step 1 warns that the containers could not be checked, continues; every other step is file work |
| the daemon is not running, `--purge` | steps 3 to 6 delete what they can, keeping the mounted files (decision 3); the volume step fails, exit 1, and its text names what was kept, why, and that a repeat after starting Docker finishes the job |
| the interpreter runs inside the venv being removed | human step, exit 3, the entry stays recorded, a repeat finishes it |
| `--role server --remove` on a machine with no record at all | nothing to delete, the stand is still stopped (decision 8), exit 0, and the report lists what it found *not* in the record as kept |
| a hand-built stand (files exist, record empty) | containers and network are removed (decision 8); nothing else is: `.env`, `continuwity.toml`, `config.yaml`, the certificates, the broker state, the passwords and the volumes are named with their reason |
| `docker/` directory missing | step 1's verify treats it as "no stack here"; the rest is unaffected |
| `--role both --remove` | participant first (core rule), then the server: the kit uninstall can still find `agentschat`, and the broker stops inside the server's step 1, after the participant's files are already away |
| `--role both --purge` | one confirmation, built from both roles' targets; the participant's text no longer promises the room history stays (decision 9) |

Cross-role isolation is structural, not a promise: every server step builds its
targets from `run.ownership_of(ROLE).of_kind(...)` or from the allow-list
discovery of the broker's own state files, and the participant's steps read only
their own record and `~/.agentschat`. The card's acceptance test - discovery
against a tree holding both roles' records, the passwords file and participant
data, targeting none of them - is the direct check.

## Step 4. The report

Two shapes, both required by the card. The participant role's `removal_lines`
(`participant.py:630-654`) is the model for the first: a header, one reason per
line, and the paths under the reason that produced it.

After `--remove`:

- the venv is gone (or: `bridge/.venv` was not ours, it stays);
- the stand is stopped, and what was kept: the three volumes, `docker/.env`,
  `continuwuity.toml`, `config.yaml`, both certificates, the saved bot
  passwords, `bridge/state/`, the installer's own logs, and why each stayed -
  "not in the ownership record" for a hand-built resource;
- the logs: `bridge/logs/start.log` and `bridge/broker.log` are the installer's
  own and are not in the card's purge list, with `rm -rf bridge/logs
  bridge/broker.log` for a human who wants them gone. On a machine that was
  installed by hand, only `start.log` is named as ours;
- the containers and the network `docker_agentschat` were removed although they
  were not recorded (decision 8);
- the mkcert root: `mkcert -CAROOT` path and the uninstall line - on Linux in the
  form `CAROOT=<path> mkcert -uninstall` run from root, with the warning that it
  breaks every other mkcert certificate on the machine and leaves the CAROOT
  files behind;
- the hosts line: `127.0.0.1 agentschat.local`, with the file per platform and
  the line to remove;
- the pulled images, named, and `docker image rm <image>` for each. The names
  come from the compose file's declarations, not from `docker image ls`, because
  the daemon may be down;
- how to put it back: `install.sh --role server` (or `install.ps1`).

After `--purge` the same block minus the kept data, plus, for every resource the
confirmation listed but the run did not delete (a volume the daemon refused, a
hand-built server's broker state), the reason under the resource's own line. A
purge that ends with "everything" and a purge that ends with three reasons must
both be true statements; the report never prints a bare "готово" over an
incomplete purge.

**A failed run prints no report.** `main.py:63-66` returns before `main.py:67-71`,
so `role.report` never runs after a failed step. Everything the human needs in
that case is in the step's own reason: which volumes were kept, that the daemon
was unreachable, and that a repeat after starting Docker finishes the job
(decision 3). Changing the core to print reports after a failure is out of this
card's boundary.

## Step 5. What is decided by the card, not here

- The mkcert root and the hosts entry stay (card).
- Images stay (card).
- Removal never asks for confirmation; only `--purge` does (core, task 02).
- `--role both` ordering (core, `roles.py:12`).
- The `PURGE` word and the exit codes (core).

## Step 6. Not decided here

The report and `docs/INSTALL.md` (task 08). A purge that is not run live on
Windows (story gate item 6) - one Docker engine holds one stack under fixed
names, and the stop scripts kill the broker machine-wide by command line, so a
live Windows verification needs the owner's stand to be down. The prepared run is
in step 7.

## Step 7. Verification plan for stage 2

- Every step: a test that its `check` is true after `apply`, and a mutant per
  step - targets from the record only; the toml gate on broker state; the volume
  step is the last one; the broker-state step runs before `continuwuity.toml` is
  forgotten; the daemon failure on purge keeps the mounted files and deletes the
  rest; an already absent volume and venv count as deleted; the venv step refuses
  while the interpreter is inside it; `ps -a`, not `ps`.
- The card's acceptance test: discovery over a tree with both records, the
  passwords file and participant data targets none of them.
- Live Docker on a throwaway project: what `down` without `-v` does to the
  volumes, what `ps -q` and `ps -a -q` each see after `stop`, and what
  `volume inspect` and `volume rm` return for a volume that is gone. Done on
  2026-10-04, recorded in `docs/VERIFICATION.md`.
- The lab, in `tools/linux-container` with its own `docker:dind`: install server
  and participant, `--role server --remove` with the data kept, a reinstall that
  picks the same data up, `--role both --remove --purge` with the typed word, a
  repeat of both, and a purge with the daemon down followed by its repeat after
  the daemon is back. Done on 2026-10-04; the report is
  `.development/reports/task-local-installers-07-server-removal.md`.

### Живой прогон на Windows, который остался за человеком

Полный цикл на Windows нельзя прогнать, не остановив живой стенд хоста: стоп-скрипт
останавливает брокер по командной строке машинно, а порт 443 и фиксированные имена
контейнеров не дают поднять второй стенд рядом. Последовательность для стенда
человека:

```
.\stop.ps1                                   # стенд хоста остановлен осознанно
docker compose -f docker/docker-compose.yml ps -a      # пусто
docker volume ls --format "{{.Name}}" | Select-String docker_
.\install.ps1 --role server --admin-user <человек> --room-id <комната>
docker volume ls --format "{{.Name}}" | Select-String docker_    # тома на месте
.\install.ps1 --role server --remove
docker compose -f docker/docker-compose.yml ps -a      # пусто: контейнеры сняты
Test-Path bridge\.venv                                  # False
docker volume ls --format "{{.Name}}" | Select-String docker_   # тома целы
Test-Path bridge\config.yaml, docker\continuwuity\continuwuity.toml, bridge\state\server-accounts.json
Test-Path bridge\state\agentschat.db                    # True: состояние пережило снятие
.\install.ps1 --role server --admin-user <человек> --room-id <комната>   # данные те же
.\install.ps1 --role both --remove --purge               # ввести PURGE
docker volume ls --format "{{.Name}}" | Select-String docker_   # пусто
Test-Path bridge\state\server-accounts.json              # False
Get-ChildItem $HOME\.agentschat\sessions | Measure-Object   # данные участника целы
.\install.ps1 --role both --remove --purge               # ввести PURGE: повтор должен закончиться без остатка
```

Секреты в отчёте - масками: токены, пароли и содержимое `config.yaml` не
переписывать, только факт наличия и размер.
