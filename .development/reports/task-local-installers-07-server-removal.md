# Task local-installers-07: server removal

Status: implemented, reviewed twice, verified in the lab. Not committed, waiting
for the human's review. Branch `task/local-installers-07-server-removal` from
`feat/local-installers` (86d73e4). Design:
[design-local-installers-07-server-removal.md](design-local-installers-07-server-removal.md).

## What the card asked for

`--role server --remove` stops the stand and removes what the installer made,
`--purge` additionally destroys the data, and both are safe to repeat. It
replaces the stub that raised "not implemented" from `report()`.

## What was built

`bridge/sessionchat/installer/server.py`:

- `StopStandStep` - the broker through the human's own script
  (`stop.ps1 -KeepDocker` / `stop.sh --keep-docker`, file output mode), then a
  poll of `/status` with the injected sleep until it is silent (`stop.sh` sends
  SIGTERM and does not wait), then `compose_argv(run, "down")` without `-v`, with
  a real exit code and compose's own stderr through `compose_failure`. The
  project's identity stays in one place: `-f <abs>/docker/docker-compose.yml`.
- `VenvRemoveStep` - the recorded `bridge/.venv` with `shutil.rmtree`, a human
  step while the running interpreter is inside it, and a recorded-but-absent
  directory counts as deleted.
- `FoundStep` for the broker's own state files (`agentschat.db` with its
  `-wal`/`-shm`/`-journal` siblings and `broker.pid`), gated on
  `continuwuity.toml` being in the server's record, minus the recorded passwords.
- Two `MountedStep`s for the configuration files and the certificates: while the
  stand's containers are still up, the files the compose file mounts are kept and
  named as kept; everything else goes.
- `OwnedStep` for the saved passwords.
- `VolumeRemoveStep`, last: `docker volume inspect` before `docker volume rm`, so
  a volume removed outside counts as deleted, and a daemon that is down fails the
  step with the reason, the volumes it kept and the repeat command.

`Stand` is the one piece of state shared between the stop step and the file steps.
The prune of the empty `~/.quoroom/installer` runs once, in the removal report,
so every path that empties the record prunes it. `project_name` and
`project_volumes` were lifted out of `InfrastructureStep` without behaviour
change. New `bridge/sessionchat/installer/report.py` holds the `Left` shape both
roles use for "what is left and why"; the participant's report text did not
change. The core (`boundaries`, `steps`, `roles`, `main`, `options`,
`confirmation`) is untouched.

Two text changes outside the server role: the participant's purge consequence no
longer promises that the room history stays (the server deletes it in the same
run under `--role both`), and `prune_installer_home` moved to
`ownership.prune_record_home` for both roles.

## Review round 1 (design, 33 scenarios, APPROVE WITH DECISIONS)

All six decisions are in the design. The blocking items became: volumes last,
"already absent counts as deleted", the split of the stop into script plus
`compose down`, the failure text naming what a repeat finishes, and the
hand-built exception written down in one line.

## Review round 2 (code, RETURN)

The logic was accepted; the return was about tests. Fixed:

- The `Machine` fake now fails `docker volume rm` on an unknown volume with
  "no such volume", exactly like the engine, and honours `present["daemon"]`
  for `volume ls`, `ps` and `down`.
- `remove_steps` passes the role's `sleep` into `StopStandStep`; the suite no
  longer sleeps for real. The wait is asserted by the number of sleeps, the
  timeout is asserted by its message and by the platform's script name.
- The remove order is pinned by a test, as the purge order already was.
- The card's acceptance test: a tree with both records, the passwords file and
  participant data, where the real server discovery targets nothing of the
  participant, plus `--role both` ordering with the real roles and a server
  purge that leaves the participant's record and data.
- The prune runs after the record empties on every path, tested for a partial
  install, for volumes removed outside and for a bare record.
- A daemon that is down with a silent broker warns and reports "готово" instead
  of "already done"; the report drops items with nothing under them; the log
  removal command names absolute paths of exactly the installer's files;
  `docker/.env` is kept with the mounted files while the stand is up; the
  passwords exclusion is by recorded path and has its own test.

## Verification

`unittest discover` from `bridge/`: 796 tests, OK, 2 skipped. `ruff check` and
`ruff format --check` from `bridge/`: clean. `node --test
bridge/tests/plugin/agentschat.test.mjs`: 4/4.

27 mutants of `server.py` and `roles.py`, each killed by its own test: the toml
gate, the state allow-list and the recorded-passwords exclusion, both step
orders, the volume `inspect` (two ways), the absent venv, `ps -a`, both gate
switches, the env-file gate, the prune, the daemon warning and its "already
done" branch, the venv holder, the keep-docker flag, `down` without `-f`, the
`down` reason, the venv in the PURGE question, the daemon guard on purge, the
silence wait and its timeout, the remove order, `INSTALL_ORDER`, the hand-built
report items, the empty volume header, the log command.

## Lab: `tools/linux-container`, 2026-10-04

The lab has its own `docker:dind`, project `quoroom-linux-lab`, no host ports. The
copy inside carries the uncommitted working copy. The host's live stand was never
touched: `agentschat-caddy`, `agentschat-element` and `agentschat-continuwuity`
stayed up, 14 volumes and 7 networks before and after.

Every line below is from a run of the final code.

Install of the server, three runs (the human steps are the lab's):

```
Остановлено на шаге «Проверить доверие к сертификату»: это должен сделать человек.
Выпустить сертификат: готово.
Поднять инфраструктуру: готово.
Браузер и брокер должны доверять сертификату agentschat.local. Выполните от администратора: CAROOT="/home/lab/.local/share/mkcert" mkcert -install (от root). Сервер ответил: сертификат не подтверждён: unable to get local issuer certificate. После этого повторите ту же команду.
Остановлено на шаге «Записать комнату»: это должен сделать человек.
Не указан идентификатор комнаты.
Записать комнату: готово.
Запустить стенд: готово.
Брокер для участников: http://127.0.0.1:8770
Сервер Matrix и Element Web: https://agentschat.local
```

`--install.sh --role participant`: `Поставить пакет quoroom: готово.`,
`Обновить набор по CLI агентов: готово.`, `Брокер отвечает на
http://127.0.0.1:8770.`, exit 0.

`--install.sh --role server --remove`, exit 0:

```
Остановить брокер и стенд: готово.
Убрать bridge/.venv: готово.
Убрано не всё, осталось в системе:
    тома compose с данными сервера оставлены: их удалит --purge
        docker_caddy-config
        docker_caddy-data
        docker_continuwuity-data
    остались записи установщика: их удалит --purge
        /home/lab/Репо с пробелом/docker/.env
        /home/lab/Репо с пробелом/docker/continuwuity/continuwuity.toml
        /home/lab/Репо с пробелом/bridge/config.yaml
        /home/lab/Репо с пробелом/docker/caddy/certs/agentschat.local.pem
        /home/lab/Репо с пробелом/docker/caddy/certs/agentschat.local-key.pem
        /home/lab/Репо с пробелом/bridge/state/server-accounts.json
    логи установщика остались: карточка снятия не относит их к очистке
        /home/lab/Репо с пробелом/bridge/logs/start.log
        /home/lab/Репо с пробелом/bridge/broker.log
        /home/lab/Репо с пробелом/bridge/logs/stop.log
    удалить их: rm -f /home/lab/Репо с пробелом/bridge/logs/start.log /home/lab/Репо с пробелом/bridge/broker.log /home/lab/Репо с пробелом/bridge/logs/stop.log
Контейнеры стенда и его сеть сняты, хотя они и не записывались: это не данные, их создаёт и поднимает start.
Корень mkcert остался: /home/lab/.local/share/mkcert. Он общий для всех проектов машины, поэтому установщик его не трогает.
Убрать его вручную (CAROOT="/home/lab/.local/share/mkcert" mkcert -uninstall (от root)) можно, но это сломает все прочие сертификаты mkcert и оставит файлы в /home/lab/.local/share/mkcert.
Строка «127.0.0.1 agentschat.local» в /etc/hosts осталась: уберите её, если имя больше не нужно машине.
Образы стенда остались: ghcr.io/continuwuity/continuwuity:latest, vectorim/element-web:latest, caddy:2-alpine. Они общие для других проектов, поэтому установщик их не удаляет.
Убрать их: docker image rm ghcr.io/continuwuity/continuwuity:latest, docker image rm vectorim/element-web:latest, docker image rm caddy:2-alpine
Поставить обратно: install.sh --role server
```

State after the removal, measured in the lab: the broker's `/status` gives
`000`, `compose ps -a` is empty, the three volumes are there, `bridge/.venv` is
gone, `continuwuity.toml`, `config.yaml`, `server-accounts.json` and both
certificates are there, `md5sum -c` on all three recorded files is OK, and the
record keeps everything except the venv.

Reinstall, exit 0: `Создать bridge/.venv: готово.`, `Выпустить сертификат: уже
сделано.`, `Завести аккаунты ботов: уже сделано.`, `Запустить стенд: готово.` -
the same volumes, all three md5s unchanged, and a fresh password login as
`labadmin` against `https://agentschat.local` succeeded, so the server still had
the account from its volume.

`printf 'PURGE\n' | ./install.sh --role both --remove --purge`, exit 0:

```
Будет удалено безвозвратно:
    server: venv /home/lab/Репо с пробелом/bridge/.venv
    server: state /home/lab/Репо с пробелом/bridge/state/broker.pid
    server: file /home/lab/Репо с пробелом/docker/.env
    server: file /home/lab/Репо с пробелом/docker/continuwuity/continuwuity.toml
    server: file /home/lab/Репо с пробелом/bridge/config.yaml
    server: cert /home/lab/Репо с пробелом/docker/caddy/certs/agentschat.local.pem
    server: cert /home/lab/Репо с пробелом/docker/caddy/certs/agentschat.local-key.pem
    server: passwords /home/lab/Репо с пробелом/bridge/state/server-accounts.json
    server: volume docker_caddy-config
    server: volume docker_caddy-data
    server: volume docker_continuwuity-data
Последствие: файлы сессий исчезнут вместе с их токенами: вернуться в комнату получится только новым входом через agentschat login. тома compose с данными комнаты исчезнут: переписка будет удалена безвозвратно.
Чтобы продолжить, введите PURGE и нажмите Enter.
Убрать набор по CLI агентов: готово.
Убрать пакет quoroom: готово.
Удалить файлы сессий: уже сделано.
Остановить брокер и стенд: готово.
Убрать bridge/.venv: готово.
Удалить состояние брокера: уже сделано.
Убрать конфигурацию стенда: готово.
Убрать сертификаты: готово.
Убрать сохранённые пароли: готово.
Удалить тома стенда: готово.
Набор и пакет убраны.
Файлы сессий удалены из /home/lab/.agentschat.
```

Measured after the purge: no volumes, no containers, `.env`, `continuwuity.toml`,
`config.yaml` and both certificates gone, `bridge/state` empty,
`~/.quoroom` gone, `~/.agentschat` empty.

Repeats: `--role both --remove --purge` again and `--role server --remove` again,
both exit 0, every step "уже сделано", no question asked.

Purge with the daemon stopped (`docker compose stop dind`), exit 1:

```
Docker-демон не отвечает, контейнеры стенда не проверены: снять их и убедиться нечем, а брокер уже молчит.
Docker-демон не отвечает, контейнеры стенда остались поднятыми.
Убрать конфигурацию стенда: /home/lab/Репо с пробелом/docker/.env оставлен: контейнеры стенда подняты, а этот файл смонтирован внутрь контейнера.
Убрать конфигурацию стенда: /home/lab/Репо с пробелом/docker/continuwuity/continuwuity.toml оставлен: контейнеры стенда подняты, а этот файл смонтирован внутрь контейнера.
Убрать сертификаты: /home/lab/Репо с пробелом/docker/caddy/certs/agentschat.local.pem оставлен: контейнеры стенда подняты, а этот файл смонтирован внутрь контейнера.
Убрать сертификаты: /home/lab/Репо с пробелом/docker/caddy/certs/agentschat.local-key.pem оставлен: контейнеры стенда подняты, а этот файл смонтирован внутрь контейнера.
Остановить брокер и стенд: готово.
Убрать bridge/.venv: готово.
Удалить состояние брокера: готово.
Убрать конфигурацию стенда: готово.
Убрать сертификаты: готово.
Убрать сохранённые пароли: готово.
Сбой на шаге «Удалить тома стенда».
Причина: тома стенда не удалены (docker_caddy-config, docker_caddy-data, docker_continuwuity-data): Docker-демон не отвечает, и контейнеры остались поднятыми, поэтому файлы, смонтированные в них, тоже оставлены. Запустите Docker и повторите ту же команду: очистка доделает остальное.
Изменения этого запуска сохранены:
    Остановить брокер и стенд
Повторите ту же команду: она продолжит с места, где остановилась.
```

After the daemon came back, the same command finished with exit 0: `.env`,
`continuwuity.toml` and the certificates gone, no volumes, no containers,
`~/.quoroom` gone.

### Lab limits worth knowing

- The broker never created `agentschat.db` in the lab, because no session ever
  logged in; the store file is created on first use. So the state step's line
  was "уже сделано" (only `broker.pid` existed, and the stop script removes it).
  The `agentschat.db` branch is covered by tests only.
- `agentschat-lab` on the host engine was a rule breach on my side, before the
  orchestrator pointed it out: it left no trace (the volume and the network were
  removed, the host volumes and stand unchanged) and nothing else was created on
  the host engine since.
- The lab's machine shares dind's network namespace (`network_mode:
  "service:dind"`), so stopping and starting dind breaks `DOCKER_HOST` for the
  machine; bringing the daemon back needed the machine container to be
  recreated and its prerequisites reinstalled by hand. That is lab mechanics, not
  installer behaviour.

## The one core change

`Role.purge_consequence` is now `Callable[[Sequence[PurgeTarget]], str]`, and
`consequence_of(roles, targets)` passes the targets `main._targets` already
collected. `roles.py` and one call in `main.py`; nothing else in the core moved.
The server's text says the room history is destroyed only when a volume is among
the targets and otherwise says the files are gone while the room stays; the
participant keeps "the room history stays on the server" unless the server is in
the same purge. Tests: a server purge without volumes says nothing about the
destruction, a participant-only purge says the room stays, `--role both` with
volumes says it is destroyed and does not contradict itself, and `--role both`
without volumes keeps the room and destroys nothing. Seven mutants of the new
logic - both server branches, both participant branches, the core dropping the
targets and the core falling back to the default - are killed by these tests.

## Not verified live

- The Windows branch of the removal on the human's own stand (`stop.ps1
  -KeepDocker`, `PowerShell` output decoding, the Windows hosts and mkcert lines).
  Tests only; the live sequence is in the design.
- Element in a browser, a hand-built server, and a purge where a volume is
  genuinely in use against a live engine.

## Open for the orchestrator

Nothing is left open: both items about the purge text were resolved by the
target-aware consequence described above.
