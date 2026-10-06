# Design sketch: task local-installers-06, server role install

Revision 2, for re-review. Nothing below is written yet; the shared-layer
changes named here are proposals approved in principle by the orchestrator, not
edits. Revision 1 is superseded: ten places in it could not be built as written
and are corrected below, each with the review item that forced the change.

## What the role has to produce

`docs/INSTALL.md` steps 0-8, automated as far as existing mechanisms allow: a
Docker stack with a trusted TLS name, a homeserver whose registration is closed
after the accounts exist, a human account and bot accounts, a room, a broker on
8770, and a report naming the broker address. Human-only steps stay human: the
hosts entry, the mkcert root CA, and creating the room.

## Verified facts this design stands on

All of them were run in the task 04 lab on 2026-10-04: Ubuntu 24.04 container,
its own `docker:dind` engine, `pipx` and `mkcert` from the Ubuntu procedure, HOME
`/home/lab`, host ports untouched (`docker volume ls` 14 -> 14, `docker network
ls` 7 -> 7, the three `agentschat-*` containers up, no `quoroom-linux-lab`
remainder after `down`). The image is
`ghcr.io/continuwuity/continuwuity:latest`, which reports itself as conduwuit
26.9.1.

1. **`GET /_matrix/client/v3/register/available?username=<u>` works** (B2's
   proposed signal). Free name: `200 {"available":true}`. Taken name:
   `400 {"errcode":"M_USER_IN_USE","error":"Username is not available."}`.
   Unauthenticated, no password. Confirmed in both directions by registering
   `probe-one` and `probe-two` and re-querying both.
2. **Login cannot be trusted to tell existence from a wrong password, but this
   version does distinguish them anyway.** Existing user with the right password:
   `200` with a token. Existing user, wrong password: `403 M_FORBIDDEN`. Unknown
   user: `404 M_NOT_FOUND`. So a 404 is a second signal, weaker than
   `available` because it is an error path; the design uses `available` and notes
   this.
3. **A configured `registration_token` does not work for the first account.** The
   server issues its own token at every start and prints it:
   `Open your Matrix client of choice and register an account on agentschat.local
   using the registration token <issued-token>`, followed by "The registration
   token you set in your configuration will not function until you create an
   account using the token above." Observed order: the configured token is
   refused, the issued token registers the first account, and the configured
   token then registers the second. This contradicts `docs/INSTALL.md` step 3a and
   the comment in `continuwuity.toml.example`; written up as
   `.development/bugreports/registration-token-first-account.md`, not fixed here.
   The issued token is a lab value that expires with its start; it is written here
   as `<issued-token>` and is never printed again.
4. **`allow_registration = false` really closes registration.** In-place edit,
   `docker compose restart continuwuity`, then a registration with a valid token
   is refused: `403 M_FORBIDDEN "This server is not accepting registrations at
   this time."` Logins keep working. The flow list and `available` do *not*
   change, so neither is a usable check for closure.
5. **The mounted TOML is read, and only in-place writes reach it.** A file with
   invalid TOML stops the container with a parse error naming
   `/etc/continuwuity/continuwuity.toml`. `sed -i` (write to a temporary file, then
   rename) leaves the container on the old inode and the change is invisible -
   this cost an hour of the lab run before it was noticed. Truncate-and-write
   keeps the inode and is seen (N7).
6. **Keys must stay inside `[global]`.** A flat file without the section fails to
   parse, which is what the example says.
7. **Windows PowerShell 5.1 does not hang the installer** (B7's premise, checked
   rather than assumed). A fake with `start.ps1`'s exact shape -
   `Start-Process` with `-RedirectStandardError` only, `-WindowStyle Hidden`, child
   outliving the script - run under `subprocess.run(capture_output=True)`,
   returned immediately, stdout `started 17068`. The same with `-NoNewWindow`:
   0.3s. PowerShell 7 is not installed here, so that combination stays unverified.
   The file-output mode is still the launch path, for output separation rather
   than for a hang that was not observed.
8. **`mkcert -CAROOT` proves nothing** (N8): it prints a path and creates
   nothing. The CA appears on the first issued certificate. In the lab
   `mkcert -CAROOT` as root returns `/root/.local/share/mkcert` with no
   `rootCA.pem`, and the user's CA appears at `/home/lab/.local/share/mkcert`
   after the leaf is issued.

Three more facts came out of the functional run of 2026-10-04, after the design
was approved, and the design follows them:

9. **A fresh Continuwuity mints room ids without a domain.** The room created
   for the run is `!sA9OkuYMoPu9zQG6qZ-S7Gba8HNS2JbfGoAZmgqwXy8` - no
   `:agentschat.local`, while the Windows stand's room id (created on an older
   server) has none either. The host's `bridge/config.yaml` holds a bare
   `!fwDrch...` id of length 44, which is the same legacy form. The rule that
   an id must end with `:{SERVER_NAME}` was therefore wrong and is replaced: the
   domain is optional, and when it is present it must be `agentschat.local`.
   Joining `!id:agentschat.local` on this server goes down the federation path
   and fails with `M_UNKNOWN No server available to assist in joining`, even for
   a room the requesting user is already in - the broker could not start with
   the invented suffix.
10. **Caddy answers `502` while the homeserver restarts.** `wait_for_server`
    must not accept a gateway status as "the server is up", or the installer
    warns that the closure was not confirmed right after closing it. The check
    and the wait agree: a status outside 502/503/504 means the server is up.
11. **The certificate expiry must be read from the validity, not scanned.**
    The first UTCTime in a certificate is `notBefore`, and extensions can carry
    later ones; scanning for "the newest timestamp" printed the issue date as
    the expiry date (`04.10.2026` for a certificate that `openssl x509 -enddate`
    reports as `Jan 4 13:08:14 2029`). The parser walks the DER structure now
    and agrees with openssl: `04.01.2029`.

## Modules

| Module | Responsibility |
| --- | --- |
| `bridge/sessionchat/installer/server.py` | the role: steps, checks, ownership, wording |
| `bridge/installer_host.py` | the venv-side helper, run by `bridge/.venv` |

The helper lives at `bridge/`, not inside the package (B1). Two reasons, both
verified: `tests/test_packaging.py` fails any non-stdlib import in
`installer/**/*.py`, and running a file by path puts its own directory at
`sys.path[0]`, where `installer/secrets.py` shadows the standard library's
`secrets` for the helper and everything it imports. At `bridge/`, `sys.path[0]`
is the directory that holds `register_account.py`, so the helper imports it with
no path surgery, and `sessionchat.installer`'s packaging tests do not see it.

Nothing in the package imports the helper: `__init__` stays empty, and
`test_importing_the_installer_pulls_in_only_the_standard_library` still passes
because nothing loads a top-level `installer_host`.

```python
def host_python(run: Run) -> Path: ...            # bridge/.venv[+Scripts]/python[.exe]
def host_call(run: Run, subcommand: str, payload: dict) -> dict:
    done = run.boundaries.run(
        [str(host_python(run)), str(run.boundaries.repo / "bridge" / "installer_host.py"),
         subcommand],
        stdin=json.dumps(payload, ensure_ascii=True),
    )
    answer = json.loads(done.stdout or "{}")
    if done.returncode != 0 or answer.get("error"):
        raise HostRefused(subcommand, answer)
    return answer
```

`bridge/installer_host.py` sits next to `requirements.txt`, not inside the
package: it is a script of its own, the installer core never imports it, and a
test runs `sessionchat.installer.server` in a fresh interpreter and asserts that
`yaml` and `requests` are absent from `sys.modules` afterwards.

Subcommands, JSON in on stdin and JSON out on stdout, so no secret travels in
`argv` where a process list could show it:

| Subcommand | Does | Returns |
| --- | --- | --- |
| `imports` | `importlib.util.find_spec` over yaml, aiohttp, nio, requests | exit 0, or exit 1 naming the missing library |
| `available` | `GET /register/available` | `available: bool` |
| `whoami` | reads `config.yaml`, calls `GET /account/whoami` per bot | per agent `valid \| placeholder \| invalid \| absent` |
| `login` | `m.login.password` | `user_id`, `access_token`, `device_id` |
| `register` | the two-step UIA of `register_account.register`, reimplemented because that script prints and exits | `user_id`, `access_token`, `device_id` |
| `probe-closed` | the same two steps with a throwaway token | `status`, `errcode` |
| `read-yaml` | parse and return requested keys | values |
| `write-yaml` | replace or insert values line-wise, parse the result before writing | `written`, `conflicts` |

Three rules the helper lives by (B4):

- **Errors carry the file name and the line number, never source text.** A PyYAML
  error quotes the offending line, and in a hand-edited `config.yaml` that line
  can be `access_token: "syt_..."`; a token the parent never registered cannot be
  scrubbed. Same for the line-wise TOML reader refusing a file.
- **The helper validates tokens itself and returns status, not values** (B4). The
  parent receives `valid`, `placeholder`, `invalid` or `absent` per agent and
  never holds a token it only wanted to check.
- **`ensure_ascii=True`, and `NO_PROXY=<SERVER_NAME>` inside the helper** (N2):
  both entry points already export `PYTHONUTF8=1`, so the encoding matches, but
  ASCII costs nothing; and `requests` honours `HTTP(S)_PROXY` while
  `boundaries.answers` disables proxies, so without this the helper could take a
  proxy path the broker never would.

## The shared-layer delta, in one place

Five additions, all in `boundaries.py`, approved in principle by the
orchestrator (N1 wants them presented together):

| Addition | Why |
| --- | --- |
| `run(argv, *, stdin: str | None = None, output: Path | None = None)` | secrets must not go through `argv` or a temp file (a crash leaves the file); the start script's own output belongs in a file (B7). Typed with a `Protocol`, so `installer_fakes.boundaries` grows `**kwargs` |
| `resolve(name) -> tuple[str, ...]` | the hosts check needs resolution; `socket` may not be touched outside `boundaries.py`, and `ping`/`getent` are not on both platforms. `()` on `gaierror`; the role tests loopback with `ipaddress.ip_address(a).is_loopback`, which covers `::1` and `127/8` |
| `secret(prompt) -> str` | the card asks for a no-echo password read; `input()` outside `boundaries.py` is forbidden (B10). Real implementation `getpass.getpass`, asked twice and compared |
| `Probe.untrusted: bool` | step 11 must accept "TLS answered, certificate not trusted" as readiness (B5); the role must not match Russian error text |
| nothing for waiting | polls and timeouts are injected into `server_role(sleep=time.sleep)`, tests pass a no-op (B5). `Boundaries` stays a description of the outside world, not of time |

The `resolve`-in-the-helper fallback is rejected: it exists only after the venv
step and puts network code outside `boundaries.py` (N1).

## Steps, in order

`check` learns the state without changing anything; `apply` does the work and
raises `NeedsHuman` when only the human can. "records" is written only when this
run created the resource; "ours" in the text means recorded, which is what makes
a resumed run able to continue (N5). All compose calls are
`docker compose -f <repo>/docker/docker-compose.yml ...` with absolute paths and
never `-p`, so the project directory is `docker/` exactly as the start scripts
make it, and no other stack on the machine is in reach (B6).

| # | Step | check | apply | records | human |
| --- | --- | --- | --- | --- | --- |
| 1 | Найти Docker | `docker --version` exits 0 | `NeedsHuman` with the platform's install command | - | yes |
| 2 | Проверить Docker-демон | `docker info` exits 0 | `NeedsHuman`: start Docker Desktop; on Linux also `usermod -aG docker` and log in again, because a user outside the `docker` group fails here too (N10) | - | yes |
| 3 | Проверить Compose v2 | `docker compose version` exits 0 | `NeedsHuman` with `apt install docker-compose-v2` | - | yes |
| 4 | Найти mkcert | `mkcert -version` exits 0 | `NeedsHuman` with the platform's install command | - | yes |
| 5 | Проверить имя сервера | `resolve(agentschat.local)` is non-empty and every address is loopback | `NeedsHuman` printing the exact hosts line and file per platform | - | yes |
| 6 | Создать bridge/.venv | the venv exists and `imports` exits 0 | `<running interpreter> -m venv .venv`, record, then `.venv python -m pip install -r requirements.txt` | `venv`, right after `-m venv`, so a pip failure does not lose it (N4) | no |
| 7 | Выпустить сертификат | both files in `docker/caddy/certs/` exist | `ca_bundle()` (which requires `<CAROOT>/rootCA.pem`, so step 4's `-CAROOT` alone is not enough, N8), create the directory, `mkcert -cert-file ... -key-file ... agentschat.local` | `cert` for each of the two files | no |
| 8 | Создать docker/.env | the file exists and its `SERVER_NAME` is `agentschat.local` | copy `.env.example` when absent | `file` = `.env` when created | no |
| 9 | Создать continuwuity.toml | the file has exactly one `allow_registration` and one `registration_token` line, and the token is not the example's placeholder | render the example with a generated token in memory and write once (B8) | `file` = `continuwuity.toml` when created | no |
| 10 | Поднять инфраструктуру | the three services are up and `probe(<homeserver>/_matrix/client/versions)` returns a status **or** `untrusted` | snapshot volumes, `up -d`, poll with a bounded wait; record the new volumes in a `finally` | `volume` per new one | no |
| 11 | Проверить доверие к сертификату | the same probe returns a status, not `untrusted` | `NeedsHuman`: `mkcert -install`, administrator rights, and on Linux the explicit `CAROOT="<path>"` the human step printed (N8) | - | yes |
| 12 | Создать config.yaml | the file parses | copy `config.example.yaml` when absent; the tokens of every agent are written afterwards, under the agent's own block | `file` = `config.yaml` when created | no |
| 13 | Завести аккаунт человека | `available` says the name is taken | only when `continuwuity.toml` is ours: register with the configured token and the password from `QUOROOM_ADMIN_PASSWORD`, else from a no-echo prompt, else `NeedsHuman`. On `401 M_FORBIDDEN` only (the "Invalid registration token" of verified fact 3), read the issued token out of `docker compose logs continuwuity` and retry this account once; any other refusal, including the `403` of a closed registration, is a `NeedsHuman` | nothing | no (the human supplies the password) |
| 14 | Завести аккаунты ботов | `whoami` says `valid` for every agent key in `config.yaml` | per bot, in the order below | `passwords` = `bridge/state/server-accounts.json` when created | no |
| 15 | Проверить адрес брокера | `sessionchat_port` (8770 when absent) equals the start scripts' 8770, and `homeserver_url` names the same server | report the mismatch as a conflict naming both sides; never edit the scripts | - | no |
| 16 | Закрыть регистрацию | `allow_registration` is `false` **and** a registration attempt with a throwaway token gets `403` | truncate-and-write `false` into the file, `restart continuwuity`, poll with a bounded wait, probe again. If the file is not ours: `NeedsHuman` with the exact line and `docker compose -f "<repo>/docker/docker-compose.yml" restart continuwuity`. If the probe after the write is still not `403`, the step fails: a run that could not confirm the closure does not report success | nothing | yes, on a machine set up by hand |
| 17 | Записать комнату | `room_id` starts with `!` or `#`, has no space, has a non-empty name, is not the example's placeholder, and its domain, if written, is `agentschat.local` | print what to create and whom to invite, take `--room-id` as is or a prompt answer, write it into `config.yaml`. A stored valid room wins over `--room-id`, with a warning naming both | nothing | the room is |
| 18 | Запустить стенд | `probe(http://127.0.0.1:8770/status)` answers | run the platform start script with its output to `bridge/logs/`, then poll `/status`. Warn about a manual restart only when the broker was already answering when the step started **and** this run wrote bot tokens | nothing | no |
| 19 | Отчёт | - | broker address, server name, certificate expiry and the renewal command, what stayed human | - | - |

Registration closes at 16, right after the accounts at 13 and 14 and before the
room step, because the room step is the likely `NeedsHuman` stop and leaving
registration open between runs would leave it open while Caddy publishes 443 on
all interfaces (N6). Nothing needs the open window after 14.

Verified fact 3 is handled inside step 13, not by a step of its own: the
installer registers the human's account with the configured token, and only when
the server answers `M_FORBIDDEN` does it read the token the server issued out of
`docker compose logs continuwuity` (ANSI stripped, both streams, last match) and
retry that one account. The bots never fall back: by then the first account
exists, and the configured token works.

## Accounts

Order is fixed by the card: the human first, then the bots. The human is first
because the first account a Continuwuity server accepts becomes its
administrator, and the installer has no way to promote an account afterwards
through the public API it uses. Closing registration without a human account
leaves the human unable to log in to Element, and the bots are useless without
the room the human creates.

**No account ownership records at all** (B3). They had no consumer - task 07
deletes volumes and files, and the volume purge takes the accounts with it - and
they contradicted gate item 4, because recording on a login adopts an account the
installer did not create. State comes from the server and from `config.yaml`:

- human: `available` says the name is taken;
- bot: `whoami` on the token in `config.yaml` returns the expected `user_id`.

**The installer creates accounts only on a homeserver whose `continuwuity.toml`
is in the server ownership record** (B3, N5). "Ours" means recorded, not "created
by this run": after a stop at the room step, run two did not create the file and
must still be able to close registration on it. On a machine set up by hand -
including the owner's live Windows stack - a missing account and open
registration both become `NeedsHuman` with the exact `register_account.py`
command, so no `@admin` ever lands on a server nobody asked to change. This is
also what makes the review's B3 consequence disappear.

Bot order inside step 15:

1. `whoami` says `valid` - nothing to do;
2. a saved password exists - log in. If `available` says the name is free, the
   volume was recreated, so register with that same password;
3. the name is free - generate a password, save it, register;
4. the name is taken and no password was saved - `NeedsHuman`, never a reset.

Bot passwords are generated with `secrets.token_urlsafe` and written to
`bridge/state/server-accounts.json` **before** the registration call, mode 0600
on Linux (N12). That file is the recovery material: an interrupted run finds the
password, logs in, gets a fresh token and finishes, instead of registering a
second time.

Every secret is registered with `Secrets.register(...)` the moment it exists: the
registration token, the issued token from the log, each bot password, each access
token, each device id - including values read from files this run did not create.
`Run.say` and `Run.warn` scrub, so a token cannot reach the report, a step failure
or a `docker compose` message. The human's password is registered too, even
though the installer never prints it: a homeserver error that quotes the submitted
body must not leak it.

`register_account.py` is used as a function, not as a script: the script prints
`user_id` / `access_token` / `device_id` to stdout, which is exactly what the
installer must not do. Used as a library it reports `M_USER_IN_USE` only through
`SystemExit` and stderr text, so the helper catches `SystemExit`, prints nothing
itself, and reports the failure as a status (B2).

## Writing into existing files

`config.yaml` is edited line-wise, in place (B9):

- only where the current value is an example placeholder, or the key is absent
  under an agent block the human declared - decided by the orchestrator on
  2026-10-04, see "Changed by the code review";
- a key absent under an agent is *inserted*, never overwritten: `user_id`,
  `access_token` and `device_id` land inside that agent's block, with the
  indent the block already uses;
- a value that is neither the example's nor a `PASTE_` placeholder is a
  reported conflict, never a write;
- comment lines are skipped - `config.example.yaml` carries a commented
  `access_token` placeholder;
- the result is parsed with PyYAML *before* it is written, so a form the
  line-wise writer cannot express (a flow mapping on one line, a quoted key) is
  refused as a conflict with a message that says to write the values by hand,
  and the file on disk stays untouched;
- nothing else in the file is touched: `homeserver_url`, `verify_ssl`,
  `sessionchat_port` and `max_depth` are read, never written.

No `yaml.safe_dump` anywhere: it would drop every comment in the example, and on
the owner's `config.yaml` it would rewrite a file the card says is never
overwritten without confirmation.

`continuwuity.toml` is read and written line-wise too, matching only
`^\s*key\s*=` outside comments, because the example's comments mention both keys
(N7). Writes are truncate-and-write: the file is a single-file bind mount, and an
in-place write is the case `docker compose restart` is documented to pick up.
Verified fact 5 says the alternative is silently invisible.

## Closing registration

The file value is the check, because the server reads the same file (verified
fact 4). The verification is the server's own acknowledgement after the restart:

```
The registration token you set in your configuration will not be usable because
you have disabled registration in your configuration.
```

Neither the UIA flow list nor `/register/available` changes when registration
closes, so neither can be the check (verified fact 4). See open question 2 for
the alternative.

## What this run owns and what it found

Gate item 4: a resource that existed before this run is validated and reused,
never recorded, so `--remove` and `--purge` report and keep it.

| Resource | Recorded when |
| --- | --- |
| `bridge/.venv` | the directory did not exist before this run's apply |
| `docker/caddy/certs/agentschat.local{,-key}.pem` | this run ran `mkcert` |
| `docker/.env`, `docker/continuwuity/continuwuity.toml`, `bridge/config.yaml` | this run copied them from the examples |
| compose volumes | they appeared between the snapshot before `up` and the one after it, carry the label `com.docker.compose.project=<name>` and are among `config --volumes` (N4). The after-snapshot is taken in a `finally`, so a failed `up` still records what it created. `<name>` comes from `config --format json`, not from re-deriving it, so `COMPOSE_PROJECT_NAME` in `.env` is honoured |
| `bridge/state/server-accounts.json` | this run wrote it |
| accounts | never (B3) |

A `docker/.env` with another `SERVER_NAME` is a conflict, not a value to
propagate (N3): the Caddyfile, `element/config.json`, both start scripts and
`room-helper.py` all hard-code `agentschat.local`.

The ownership record goes to `<home>/.quoroom/installer/server.json`, with
absolute paths as ids. The reason is task 07's explicit requirement that the
record live outside `bridge/state/`, plus symmetry with the participant's
`record_path`; revision 1's rationale was wrong, because
`FoundStep.is_record` already excludes any role's record wherever it lives (N4).

Like the participant role, `server_role()` takes what it cannot know from the
outside as arguments: the interpreter that runs it and the sleep function.

## Port and TLS

The start scripts fix the broker at 8770 (`$brokerPort` in `start.ps1`,
`broker_port` in `start.sh`), `config.yaml` carries `sessionchat_port`, and the
broker reads it with `DEFAULT_PORT` as the fallback. So step 16 compares one
number against a constant the scripts own, and a mismatch is a conflict naming
both sides. The scripts and the config are not edited.

Trust is confirmed after the stack is up by `probe` against
`https://agentschat.local/_matrix/client/versions`, which uses the system's
default trust exactly like a browser. Step 10 accepts `untrusted` as "the server
answered TLS", step 11 does not, so a fresh machine reaches the human instruction
instead of failing the infrastructure step (B5). The registration calls pass the
CA bundle from `ca_bundle()` (verified fact 8), which works whether or not the CA
is installed - that is what `requests` needs, since it does not read the system
store.

The start script is launched as `powershell.exe -NoProfile -ExecutionPolicy
Bypass -File <abs>\start.ps1` on Windows and `sh <abs>/start.sh` on Linux, never
with `-Logs` (it would block on `Get-Content -Wait`), with its output going to a
file under `bridge/logs/` that the installer reads and scrubs on failure.
Verified fact 7: the hang B7 predicted does not occur on PowerShell 5.1 in either
window mode, so this is output separation, not a deadlock workaround; the first
test of the slice is that same fake, skipped when PowerShell 7 is absent, in the
shape `test_entry_points.py` already uses for `pwsh`.

If this run wrote `config.yaml` while a broker already answers `/status`, the
broker still serves the old configuration: step 19 reports "restart the broker"
and does not restart it (N11). `start.ps1` also exits 0 with only a warning when
the port stays closed, so the `/status` poll is the real check and its failure
points at `bridge/broker.log`.

## Review map

| Item | Closed by |
| --- | --- |
| B1 helper location | `bridge/installer_host.py`; `Modules` above |
| B2 existence signal | verified fact 1 (`available`); verified fact 2 records what login actually returns; `SystemExit` handling in `Accounts` |
| B3 account checks, records, adoption | no account records; state from `available` and `whoami`; create only when `continuwuity.toml` is recorded |
| B4 secrets through parser errors | the three helper rules; `whoami` returns status |
| B5 readiness before trust, waiting | step 10 accepts `untrusted`, step 11 requires trust; `sleep` injected into `server_role` |
| B6 compose working directory | every compose call carries `-f <repo>/docker/docker-compose.yml`, no `-p`, absolute paths |
| B7 start script under `capture_output` | verified fact 7; file-output launch; never `-Logs` |
| B8 example placeholders passing | steps 9, 13 and 18 reject the example's own values, read from the example files |
| B9 missing `config.yaml` step, write mechanism | step 13 added; line-wise writes, no `safe_dump` |
| B10 no-echo password | `secret` boundary; step 14 |
| N1 core extensions | `The shared-layer delta`, one table |
| N2 encoding and proxy | third helper rule |
| N3 `SERVER_NAME` | conflict, not propagated |
| N4 ownership details | ownership table; venv recorded right after `-m venv`; volume `finally` plus label filter; record-location rationale corrected |
| N5 "ours" means recorded | step 17 and the accounts section |
| N6 step order | registration closes at 17, before the room |
| N7 line-wise TOML | `Writing into existing files` |
| N8 mkcert on Linux and in the lab | verified fact 8; `ca_bundle()` requires `rootCA.pem`; step 11 prints `CAROOT`; `tools/linux-container/README.md` documents `exec-root` |
| N9 trust instruction at step 12 | it is step 11 here, and stays a step |
| N10 Linux docker group | step 2 |
| N11 running broker, changed config | step 19 |
| N12 password file mode | `Accounts`, mode 0600 |
| N13 Windows repeat run | expected: on the owner's machine steps 14 and 17 are `NeedsHuman`, so the live repeat run stops there with exit 3. The task 08 handoff should either close registration by hand first or expect that stop |

## Decisions taken by the orchestrator, applied above

`--admin-user` with no default, asked when the run is interactive (Q1); bots are
the `agents` keys of `config.yaml`, no `--bot` flag (Q2); trust is checked by the
handshake alone, with `CAROOT` named on Linux (Q3); the human password comes from
the environment variable, then a no-echo prompt, then `NeedsHuman` (Q4);
`RENEWAL.md` is not written, the expiry and renewal command go to the report
(Q5); closing registration follows the ownership rule and is confirmed by a
probe (Q6); the record lives at `<home>/.quoroom/installer/server.json` (Q7).
Then, after the design review:

- **The issued token is read lazily, in the account step (R1).** No separate
  "get the issued token" step, and no fallback for the bots: the configured
  token is tried first, the log is read only on `M_FORBIDDEN`, and only that one
  account is retried.
- **Closure is confirmed by a probe (R2).** After the in-place write and the
  restart, a registration attempt with a deliberately wrong token must get `403`
  ("not accepting registrations"), not `401` ("invalid token"). Verified in the
  lab on a server that already has accounts, which is the state the installer
  closes registration in.
- **The misleading comment in `continuwuity.toml.example` is not touched here
  (R3).** It belongs to task 08; the bugreport carries the evidence.
- **`room-helper.py` under `exec` counts as the human's room step in the lab
  (R4).**
- **The installer issues the certificate; the human only installs the root
  (R5, R6).** The lab README must not show the operator issuing certs, and
  `exec-root` exists for the hosts file and `mkcert -install` with an explicit
  `CAROOT`, not to bring the environment up.

## Open questions

1. **The issued registration token - resolved (R1).** Verified fact 3 says the
   configured token cannot register the first account. The installer tries the
   configured token, reads the issued token from the log only on `M_FORBIDDEN`,
   and retries that account once. The lab contradicted the card here; the
   implementation follows the server, and the bugreport records why.
2. **How closure is verified - resolved (R2).** A registration attempt with a
   throwaway token expecting `403`, not the log line. The account risk is gone:
   the server refuses the wrong token with `401` whether or not the change took
   effect, so a broken change cannot create anything, and the state the
   installer verifies always has accounts already.
3. **Should the example's comment be corrected now?** One line in
   `docker/continuwuity/continuwuity.toml.example` would stop the next reader from
   losing an hour. It is a secret-adjacent example file, outside this card's
   boundary, and the wording belongs to task 08. Recommendation: leave it, the
   bugreport carries it.
4. **Room creation in the lab - resolved (R4), and it worked.** The functional
   flow needs a room. The card says the human steps go through `exec-root`, but a
   room is created by logging in, so `room-helper.py` under `exec` is the way -
   the human's account exists by then. The run confirmed it counts as the human
   performing the step, and it is what produced the bare room id of verified
   fact 9.

## Changed by the code review of 2026-10-04

The review returned the slice and the following rows changed; nothing else in
the approved design did.

| Row | Was | Now | Why |
| --- | --- | --- | --- |
| 13 (account) | fall back to the log on any `M_FORBIDDEN` | fall back only on `401 M_FORBIDDEN`; a `403` is a `NeedsHuman` that says registration is closed | Continuwuity uses the same errcode for both, and the fallback on a closed server read a stale banner token from an old container log |
| 16 (closure) | the probe ran inside `apply` and an unconfirmed answer was a warning | the probe is part of the check; an unconfirmed answer after the write fails the step | "the value in the file and the probe" was the approved rule, and a run that cannot confirm the closure must not exit 0 |
| 6 (venv) | `imports` answering anything but ok means the step is done | a refusal from `imports` means the step is not done, and `apply` re-runs pip | the helper reports a missing library as a failure with exit 1, so an interrupted pip could never be repaired |
| 17 (room) | an id must end with `:{SERVER_NAME}` | the domain is optional; when written it must be `agentschat.local`, and an alias always needs one | verified fact 9 |
| 12 (config) | an absent key is written only in a file the installer created | a key absent under an agent block the human declared is inserted there, even in a `config.yaml` the installer did not create | decided by the orchestrator on 2026-10-04: it is an insertion, never an overwrite; a real value is still a conflict |

## Decided by the orchestrator on 2026-10-04, after round 2

**Filling an agent block the human declared, in a `config.yaml` the installer
did not create.** Allowed for `user_id`, `access_token` and `device_id` only,
only when the key is absent, and only inside the block of the agent the human
declared - that block exists because the human put it there. It is an
insertion: any existing value that is neither the example's nor a `PASTE_`
placeholder stays a conflict, and nothing else in the file is touched.
Everything else about the ownership rules is unchanged.

## Not decided here

Server removal and purge (task 07), `docs/INSTALL.md` (task 08), and the live
handoff.
