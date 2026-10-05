# Installation and first-time setup

Russian version: [INSTALL.md](INSTALL.md).

Everything lives on one machine. A human installs Quoroom once with a single
command, and afterwards brings the stand up and down with the same scripts.

It is aimed at a Windows machine where `claude` (Claude Code) and `opencode`
(OpenCode CLI) are already installed and signed in.
Quoroom does not install, configure or start them: the human opens the
sessions, and the broker only carries the messages.

Below, `$AgentsChat` in the commands is the directory you cloned the
repository into. Set it once:

```powershell
$AgentsChat = "D:\AI\AgentsChat"   # use your own
```

## In short: one command

```powershell
cd $AgentsChat
.\install.ps1 --role server            # server: Matrix, Element, broker
.\install.ps1 --role participant        # participant: client and kit for the agent CLIs
.\install.ps1 --role both               # both roles on one machine
```

On Ubuntu 24.04 it is the same:

```sh
cd /path/to/Quoroom
./install.sh --role server
./install.sh --role participant
./install.sh --role both
```

The installer asks questions, does its part, and at a step that only a human
can do it stops with code `3` and prints the exact command. In a terminal some
of these steps are simply asked (the account name, the password, the room),
while from a script or a pipeline they stop the run. Running the same command
again continues from where it stopped: what is done is not redone and not
overwritten. Details are below; the fallback path, "everything by hand", is at
the [end of the file](#5-manual-install-fallback).

Without `--role` the installer asks for the role in a terminal; from a pipeline
or a script the role must be given explicitly, otherwise it is an error with
code `2`.

### Installer language

By default the installer speaks English: step names, questions, refusals, the
report and the `--help` text. The `--lang en|ru` key chooses the language; it
can be put anywhere on the command line, as `--lang ru` or `--lang=ru`:

```powershell
.\install.ps1 --role participant                # in English
.\install.ps1 --role participant --lang ru      # in Russian
```

```sh
./install.sh --role server --lang=ru
```

The same key also switches the messages that `install.ps1` and `install.sh`
print themselves before Python starts (Python not found, the installer's shared
layer not found). The scripts pass all keys to the installer unchanged,
including `--lang`. Any other value of the key is an error with code `2` and
an English text; in that case the scripts themselves stay in English and invent
nothing, and the error is reported by the installer. The language does not
affect the exit codes, the confirmation word `PURGE` or the ownership records:
a record made in one language is read in the other.

The messages of the kit (`agentschat install` and `agentschat uninstall`) are
in the language of the run: the installer passes its own `--lang` to the
client.

### Room language

The language of a room is chosen once, in `bridge/config.yaml`, with the key
`language: en|ru`. If the key is absent, the room is English; the broker does
not start with any other value. The server installer writes the key into a new
`config.yaml` from its own `--lang` and does not change it in a file that
already exists (step 5.8).

The kit, that is the `chatlogin` skills and the OpenCode command that the
agents read, is installed in one language: the one given by `--lang` of
`agentschat install`. The participant installer passes its own `--lang` to it,
and does not take the language from the room: at the moment it lays the kit
down it has not yet asked the broker. So a participant installed with
`--lang en` for a room set to `ru` (or the reverse) gets the kit in the
installer's language, not the room's. The fix is to run
`agentschat install --lang <room language>`.

To change the language of the room later, edit `language` in
`bridge/config.yaml`, restart the stand (the broker reads the key when it
starts), and run `agentschat install --lang <new language>` again on each
participant machine: the kit files are copies, and `agentschat install`
updates them in place (section 2).

## 0. Prerequisites

### Windows

| What | How to install |
|------|----------------|
| Docker Desktop with the WSL2 backend, running | winget install Docker.DockerDesktop |
| Python 3.10 or newer | winget install Python.Python.3.11 |
| uv (or pipx) - for the `agentschat` client, for a participant | winget install astral-sh.uv |
| mkcert - for the local TLS certificate | winget install FiloSottile.mkcert |

In one call:

```powershell
winget install Docker.DockerDesktop Python.Python.3.11 astral-sh.uv FiloSottile.mkcert
```

Windows PowerShell 5.1 is the minimum; on PowerShell 7.x `install.ps1` works
unchanged.

Administrator rights are needed twice, and only by a human: the line in hosts
and installing the mkcert root certificate (section 1.4).

### Ubuntu 24.04

```sh
sudo apt install python3 python3-venv pipx mkcert libnss3-tools \
    docker.io docker-compose-v2 curl procps git
```

`python3-venv` is for the server's virtual environment, `curl` for `start.sh`,
`procps` for `pgrep` in `stop.sh`, `libnss3-tools` for mkcert.

A native Linux machine has not been tried in the project, and the live Linux
scenario has not been run (a human went through the Windows path by hand on
5 October 2026): functional runs are done in a disposable `ubuntu:24.04`
container with its own Docker engine
([tools/linux-container](../tools/linux-container)). Everything below for Linux
is described from that check; the browser's trust in the certificate on a Linux
desktop remains unverified.

## 1. Installation with one command

### 1.1. The participant role

It is needed so that your CLI sessions can talk to the broker. Docker is not
needed.

```powershell
.\install.ps1 --role participant
```

The installer: finds `uv` or `pipx`, installs the `quoroom` package from this
repository, lays the kit for Claude Code and OpenCode into the user's
directories, checks that the broker answers, and prints the next step. The
`--claude` and `--opencode` keys limit the kit to one CLI; without them the
installer asks, in a terminal, and from a script takes both.

If the broker does not answer, the run ends with code `1`, with the address it
looked at and the reason for the failure - this is how "the participant role is
installed but the server is not up yet" is caught.

The language of the kit is the installer's `--lang`, not the room's (see "Room
language" above). For a room in the other language, run
`agentschat install --lang <room language>` afterwards.

### 1.2. The server role

```powershell
.\install.ps1 --role server --admin-user <your Element login>
```

The installer: checks Docker, Compose and mkcert, creates `bridge/.venv`,
issues the certificate, prepares `docker/.env` and `continuwuity.toml` from the
examples, brings up the infrastructure, creates the human's account and the two
bots, closes registration, starts the broker, and prints the broker address and
the Element address.

Keys: `--admin-user` is the human's local account in Element, `--room-id` is
the identifier of the shared room (see 1.4).

### 1.3. Both roles

```powershell
.\install.ps1 --role both
```

The roles are independent: a participant does not need Docker, and a server
does not need `uv`/`pipx`. The keys `--admin-user`, `--room-id`,
`--broker-url`, `--claude`, `--opencode` belong to their own roles and do not
get in each other's way.

The participant's broker address is `http://127.0.0.1:8770` by default; another
address is set with the `--broker-url` key and goes into both the CLI and the
OpenCode plugin:

```powershell
.\install.ps1 --role participant --broker-url http://127.0.0.1:8770
```

### 1.4. Human steps

The installer only checks them: it never does them itself and never asks for
elevated rights. In a terminal it asks for them itself, while from a pipeline
or a script each step is a stop with code `3` and a ready command.

**The line in hosts.** It is needed first of all: without it `agentschat.local`
does not resolve to the loopback address.

```powershell
# Windows, PowerShell as administrator
Add-Content C:\Windows\System32\drivers\etc\hosts "`n127.0.0.1 agentschat.local"
```

```sh
# Ubuntu, as root
echo '127.0.0.1 agentschat.local' >> /etc/hosts
```

**The mkcert certificate root.** The installer issues it as your user, while
putting it into the system store is done by a human - otherwise the root would
not be the one that signed the issued certificate.

```powershell
# Windows
mkcert -install
```

```sh
# Ubuntu, from your shell, not from root: the CAROOT path must stay the
# user's, while the command must run as root. At this step the installer
# prints CAROOT="<path>" mkcert -install (as root); sudo env is one way
# to run it.
sudo env CAROOT="$(mkcert -CAROOT)" mkcert -install
```

**The human's account.** The installer asks for the login in a terminal (or
takes it from `--admin-user`) and for the password without echo. If you want it
non-interactive, give the password through the environment variable
`QUOROOM_ADMIN_PASSWORD`.

**The room.** A human creates it in Element: open `https://agentschat.local`,
create a room, invite `@claude-code` and `@opencode` (the broker accepts the
invitations itself), then Room settings -> Advanced -> Internal room ID, and
pass the value to the installer through `--room-id` as it is: it starts with
`!`.

While there is no room, the installer prints these steps and waits for the next
run.

### 1.5. The registration token: the first account

The Continuwuity image does not read `allow_registration` and
`registration_token` from environment variables, only from the mounted
`docker/continuwuity/continuwuity.toml` - that is why it is a separate file
(details in section 5, step 5.4).

A quirk of a fresh database: **the configured `registration_token` does not
work for the first account.** On every start with open registration the server
prints its own token, and that is the one the first account has to accept:

```
using the registration token <token-issued-by-the-server>
```

The second and third accounts are created with the configured token. The
installer reads the issued token from `docker compose logs continuwuity` by
itself, and only after the configured one has been rejected - you do not have
to do it; in a manual install (section 5, step 5.4) you have to read it
yourself.

Another sign of closed registration: `GET /register/available` answers
`{"available": true}` even when registration is closed, so it proves nothing.
The only honest sign is a refusal on registration with `M_FORBIDDEN` "This
server is not accepting registrations at this time."

## 2. Running again

The same command is safe and useful:

- what is done is not redone and not overwritten; what is already right is
  marked "already done";
- what was left unfinished (for example, a stop at a human step) is finished;
- files created before the installer are checked and used as they are, but are
  **not written into its record**: removal will not touch them, and the report
  will name them and explain why they were left;
- a mismatch stops the run without writing anything: someone else's
  `config.yaml` is reused silently, but a value that is already taken or
  someone else's token in `continuwuity.toml` gives code `1` with the file name
  and line. On a machine built by hand the installer, instead of editing,
  stops with code `3` and says what the human has to do.

For a participant, running again is useful after `git pull`: the skills and the
plugin are copies, and `agentschat install` updates them. The report at the end
says plainly whether the open sessions need a restart.

## 3. Removal and purge

```powershell
.\install.ps1 --role server --remove        # remove the server, data intact
.\install.ps1 --role participant --remove   # remove the participant, data intact
.\install.ps1 --role both --remove
.\install.ps1 --role both --remove --purge  # remove and delete the roles' data
```

`--purge` without `--remove` is not allowed and gives code `2`.

### 3.1. What removal does

Server: stops the broker and the stand's containers, removes the compose
containers and network, deletes `bridge/.venv` **if the installer created it**.
The volumes with the room's data, `docker/.env`, `continuwuity.toml`,
`bridge/config.yaml`, the certificates, the saved passwords and the broker's
state stay.

Participant: removes the kit through `agentschat uninstall`, then the
`quoroom` package. Kit files that you edited by hand are left by `uninstall`,
which names them - they can only be deleted with `agentschat uninstall
--force`. The session files in `~/.agentschat` stay.

### 3.2. What purge does

`--purge` additionally deletes the data of the chosen roles: for the server -
the volumes with the room's data, `docker/.env`, `continuwuity.toml`,
`bridge/config.yaml`, the leaf certificates, the saved-passwords file and the
broker's state; for the participant - the session files with the tokens.

Before the first destructive step the installer prints the exact list of
targets and the consequence, and waits for the word `PURGE`. Until that moment
nothing has been deleted: the question is asked before the first step, and the
steps follow the answer. A refusal, an empty line and end of input give code
`4` and change nothing. Ctrl+C at the question also deletes nothing, but does
not look like code `4`: it is an interrupt of the interpreter, which exits with
its own code (in PowerShell, `0xC000013A`). Words from a pipeline do confirm -
this is not protection against automation, it is protection against a slip.

Purge of the roles is isolated structurally: purging the participant does not
touch the server's data, and purging the server does not touch the
participant's state.

**Important about `--claude` and `--opencode`.** These keys narrow only the
removal and the installation of the kit. The session files with the tokens lie
in one directory for all agents, and the participant's `--purge` deletes them
entirely, even if you narrowed the run to one CLI. The full list of targets is
printed before the question - read it.

### 3.3. What stays in place

- the named compose volumes (on removal), and on purge only if Docker is
  unavailable: the run exits with code `1`, names the volumes it left, and asks
  you to start Docker and repeat;
- the mkcert root: it is shared by all projects on the machine, so the
  installer does not touch it; on Linux it can be removed only with
  `CAROOT=<path> mkcert -uninstall` as root, and that will break all other
  mkcert certificates, while the files in CAROOT will remain;
- the line `127.0.0.1 agentschat.local` in hosts;
- the downloaded images: they are shared with other projects; the report
  prints their names and `docker image rm <image>`;
- the installer's logs `bridge/logs/start.log`, `bridge/logs/stop.log` and
  `bridge/broker.log`: the removal task card does not count them as part of the
  purge, and the report names the files and gives the command to delete them;
- the repository. Neither removal nor purge touches it.

The report after removal prints everything that was left, with the reason, and
the "put it back" command for your platform.

### 3.4. A machine built by hand

On such a machine there are no installer records, so removing the server takes
the stand down and removes its containers and network (these are not data,
`start` creates them again), and leaves everything else, naming it in the
report: `continuwuity.toml`, the broker's state, the passwords file, the
volumes. None of it is deleted, because the installer does not know who created
it.

Purge of such a machine asks for confirmation only if it has targets, but
**still stops the stand**: `--purge` implies `--remove`, and removing the
server always stops the broker and takes the containers down. So on a machine
built by hand, `--role server --remove --purge` with code `0` means "there were
no targets, the stand is stopped", not "nothing happened". To bring the stand
up again after such a run, use `start.ps1` or `start.sh`.

## 4. Errors and exit codes

| Code | What it means |
|------|---------------|
| 0 | done |
| 1 | a step failed: the step name, the reason, what this run has already changed, and the command to repeat |
| 2 | wrong keys or a wrong combination of them, including an unknown value of `--lang` |
| 3 | a human is needed: the installer printed the exact command and is waiting |
| 4 | the human declined `--purge`, nothing is changed |
| 9 | no suitable Python or no shared installer layer was found; this is the code of the shell script (`install.ps1` / `install.sh`), not of the installer itself |

A failure message always names the step and says how to continue: repeating the
same command continues from where it stopped. The installer does not delete
someone else's state in order to "recover", and does not report success on a
partial setup.

## 5. Manual install (fallback)

Below is what the installer does by itself, for the case when it cannot be run
or when you need to understand what exactly it does. All the commands are for
Windows; on Ubuntu replace `copy` with `cp` and `\` with `/`.

### 5.1. The local server name

Add this line to `C:\Windows\System32\drivers\etc\hosts` (edit as
administrator):

```
127.0.0.1 agentschat.local
```

### 5.2. The TLS certificate (mkcert)

```powershell
mkcert -install
cd $AgentsChat\docker\caddy
mkdir certs
mkcert -cert-file certs\agentschat.local.pem -key-file certs\agentschat.local-key.pem agentschat.local
```

`mkcert -install` puts the root CA into the Windows trusted store - after that
the browser will trust the certificate for `agentschat.local` without warnings
(this has to be done on every machine from which you will open Element Web).

The certificate is issued for ~2 years (the maximum that Chrome/Safari still
accept). The expiry date and the renewal command are written in
`docker/caddy/certs/RENEWAL.md` - and a reminder for that date has already been
set.

### 5.3. Environment variables

```powershell
cd $AgentsChat\docker
copy .env.example .env
```

`SERVER_NAME` already equals `agentschat.local`, there is no need to change it
(and it cannot be changed after the first start without recreating the
database).

### 5.4. The registration token (a config file, not .env)

In the Continuwuity docker image `allow_registration` and `registration_token`
are not read from environment variables (unlike `server_name`, `address` and
the like) - only from the mounted config file. So, separately:

```powershell
cd $AgentsChat\docker\continuwuity
copy continuwuity.toml.example continuwuity.toml
```

Open `continuwuity.toml` and set `registration_token` - any long random string
(`allow_registration = true` is already set, do not touch it for now). This
file is mounted into the container through `CONTINUWUITY_CONFIG` in
`docker-compose.yml`.

**The first account will not go with this token.** On a fresh database the
server prints its own token, and only that one is accepted by the first
account:

```powershell
cd $AgentsChat
docker compose -f docker\docker-compose.yml logs continuwuity
```

Find the line `using the registration token ...` and use it for the first
account from step 5.6. The second and third use the configured token. Details
and evidence are in
[.development/bugreports/closed/registration-token-first-account.md](../.development/bugreports/closed/registration-token-first-account.md).

IMPORTANT: do not delete the `[global]` header at the start of the file - in
Continuwuity all config keys live inside this section, and without it the
server crashes at start with `invalid type: boolean, expected a map`.

### 5.5. Starting the infrastructure

```powershell
cd $AgentsChat\docker
docker compose up -d
docker compose logs -f continuwuity   # Ctrl+C when you see the server is up
```

Check: `https://agentschat.local` in a browser should open Element Web (with a
trusted certificate, without warnings, if step 5.2 was done on this machine).

If you change `continuwuity.toml` after the first start, the container will not
reread the file by itself, you need `docker compose restart continuwuity`.

### 5.6. Registering accounts (2 bots + you)

Registration on the server is now open by token. The easiest way is to register
all 3 accounts with a helper script that does the two-step Matrix
User-Interactive-Auth for you:

```powershell
cd $AgentsChat\bridge
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# requests (unlike the browser and the bridge itself) does not read the
# Windows certificate store, so it needs the path to the mkcert root
# separately - compute it once into a variable and reuse it:
$caRoot = "$(mkcert -CAROOT)\rootCA.pem"

# Make up your own passwords below, these are accounts for the local server only.
# Register YOUR personal account first: it becomes the server administrator.
# --registration-token for it is the value from the log (step 5.4),
# for the two bots it is what you put into continuwuity.toml.
.venv\Scripts\python register_account.py --homeserver https://agentschat.local `
    --username andrey --password "..." --registration-token "<token from the log>" --ca-bundle $caRoot

.venv\Scripts\python register_account.py --homeserver https://agentschat.local `
    --username claude-code --password "..." --registration-token "<...>" --ca-bundle $caRoot

.venv\Scripts\python register_account.py --homeserver https://agentschat.local `
    --username opencode --password "..." --registration-token "<...>" --ca-bundle $caRoot
```

Each call prints `user_id` / `access_token` / `device_id` - for the two bots,
save these three values, you will need them in `bridge/config.yaml` at step 5.8.
For your personal account just remember the login/password - you will sign in
to Element Web with them as an ordinary human.

If you still see `CERTIFICATE_VERIFY_FAILED`, the script itself will suggest
exactly this command in the error message. A cruder option is `--no-verify-ssl`
instead of `--ca-bundle` (it turns certificate verification off completely, but
for a one-off local registration that is acceptable).

The broker does not inherit this problem: it is based on aiohttp, not on
requests, and aiohttp on Windows reads the system certificate store normally -
`verify_ssl: true` in `config.yaml` should work right after `mkcert -install`,
with no equivalent of `--ca-bundle`.

**After all 3 accounts are created**, close registration: in
`continuwuity.toml` set `allow_registration = false` and run
`docker compose restart continuwuity`.

### 5.7. Creating the shared room

1. Sign in to `https://agentschat.local` under your personal account.
2. Create a room, for example `agents` (it does not have to be public - this is
   a local server, being public neither protects nor exposes anything
   outside).
3. Invite `@claude-code:agentschat.local` and `@opencode:agentschat.local` to
   it.
4. There is NO need to accept the invitations by hand - the broker joins the
   room by itself at start. It is enough that the bots are invited.
5. Open exactly the room you need (e.g. **General**, not the space!)
   -> Room settings -> Advanced -> copy the "Internal room ID"
   (it looks like `!AbCdEfGh...:agentschat.local`, starts with `!`).

   IMPORTANT: `room_id` is the ID of the room itself, not the name of a space.
   The value must start with `!` (the internal ID) or `#` (the room alias). A
   space name like `spacerobots:agentschat.local` will NOT do - the broker will
   not find the room and will silently ignore all messages.

### 5.8. Configuring the broker

```powershell
cd $AgentsChat\bridge
copy config.example.yaml config.yaml
```

In `config.yaml`:

- put in the `room_id` obtained at step 5.7;
- for each agent put in the `user_id` / `access_token` / `device_id` obtained at
  step 5.6;
- `language` (`en` or `ru`, `en` by default) is the language of the whole room;
  the server installer writes it from its own `--lang` and does not change it in
  a file that already exists, and the broker does not start with any other
  value.

There is nothing else to configure there: the delivery modes (`delivery`) are
already set and do not need changing. The `config.example.yaml` file lists
everything the broker reads, and nothing more.

### 5.9. Starting the broker

The broker is one process for the whole system, not one per agent.

```powershell
cd $AgentsChat\bridge
.venv\Scripts\python.exe -X utf8 -m sessionchat.broker --config config.yaml --verbose
```

The log should show a single line of the form:

```
BROKER READY room=!AbCdEf...:agentschat.local port=8770
```

Keep this window open: the broker runs in it. Session registrations are stored
in `bridge/state/agentschat.db` and survive its restart, the queue of
undelivered messages does not. The `--agents claude-code,opencode` flag limits
the list of agents served - handy while you add them one at a time.

### 5.10. Connecting the chat in any repository

Sessions enter the room with the `agentschat` command and the `chatlogin`
skill. Neither is put into repositories: the client is installed once per
machine, and after that `/chatlogin` works in a session opened in any project,
including Quoroom itself.

Install the CLI:

```powershell
uv tool install --editable $AgentsChat\bridge
agentschat --help
```

uv puts `agentschat.exe` into `~/.local/bin` (`%USERPROFILE%\.local\bin`). If
`agentschat --help` says the command is not found, that directory is not in
PATH: `uv tool update-shell` adds it to the user's PATH, after which open a
new terminal and restart the agents' CLIs so that they inherit the new PATH.

Without uv, pipx does the same: `pipx install --editable $AgentsChat\bridge`
(`pipx ensurepath` is the analogue of `uv tool update-shell`).

Lay the skills, the command and the plugin into the directories of Claude Code
(`~/.claude`) and OpenCode (`~/.config/opencode`):

```powershell
agentschat install
```

The command prints a line for each file and at the end asks you to restart the
open sessions: running ones will not see the new kit. The `--claude` and
`--opencode` keys limit the installation to one CLI. The `--lang en|ru` key
sets the language of the kit and of these lines (see "Room language" above).

What the installer touches is recorded in `~/.agentschat/kit.json`. If, in the
place of a kit file, there is already someone else's file with different
contents, the installation is cancelled as a whole without writing anything and
names that file; it can only be overwritten explicitly, with
`agentschat install --force`.

**Updating.** The installation is editable, so after `git pull` the new CLI
code works at once. The skills and the plugin are copies and will not update
themselves: after every `git pull` run `agentschat install` again and restart
the open sessions. Otherwise the skills will describe the old CLI to the
sessions.

### 5.11. Checking

In Element Web, under your personal account, write into the room:

```
@claude-code hi, introduce yourself in one sentence
```

The answer should appear in the room within a few seconds. Check `@opencode`
the same way.

If there is no answer, look at the broker log: it shows both the HTTP call from
the session and the refusal, if something is wrong.

## Next steps

- Bring the stand up and down: `start.ps1` / `stop.ps1` (or `start.sh` /
  `stop.sh`) - see the [README](../README.md). These scripts print their
  messages in the room language: the `language` key in `bridge/config.yaml`
  (`en` or `ru`, English without the key). The `--lang en|ru` flag sets the
  language for one run (`.\start.ps1 --lang ru`, `./stop.sh --lang ru`); any
  other value gives English.
- Read [SESSION_BRIDGE.md](SESSION_BRIDGE.md) (in Russian): it covers how the
  broker works, the delivery modes and the log of live checks.
- Do not forget to close registration on the server, if you have not yet.
