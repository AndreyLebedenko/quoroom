# Disposable Linux environment

An `ubuntu:24.04` machine with its own Docker engine (`docker:dind`) in which
`install.sh` runs for real. The environment does not touch the stand of the
human on the host: its own compose project has the explicit name
`quoroom-linux-lab`, the Docker socket of the host is not mounted, `down -v`
works only on its own project, and it takes no host port.

The environment is disposable: `./run.sh scenario` removes it together with its
volumes, even if the scenario or the preparation fell over.

## What it needs

Docker on the machine that runs it. The images `ubuntu:24.04` and `docker:dind`
are pulled on the first run; inside the machine `apt` installs the prerequisites
by the Ubuntu 24.04 procedure of gate 1 of the story:

```
python3 python3-venv pipx mkcert libnss3-tools docker.io docker-compose-v2 curl procps git
```

Scenarios and `exec` go as the user `lab` without `sudo`: that is how the lab
catches an installer that must not take privileged steps itself. `apt` and the
creation of the user are done as `root` before any scenario starts.

## How to run it

Started from `sh` - Git Bash on Windows or any Linux. It does not work from
PowerShell directly.

```sh
./run.sh snapshot               # what the host has before a run
./run.sh scenario install-help   # bring it up, run install.sh --help, remove it
./run.sh up                     # bring it up and leave it running (needed for exec and shell)
./run.sh exec 'command'          # a command in the live machine, the exit code is that of the command
./run.sh shell                  # a shell in the machine
./run.sh down                   # remove the environment together with its volumes
```

The state of the host (containers, volumes, networks) is printed before and after
every run. Any scenario runs as a command in the copied repository:

```sh
./run.sh scenario './install.sh --role both'
./run.sh scenario verify-copy
./run.sh scenario verify-shared-home
```

## Human steps: exec-root

The steps that the installer only checks are done in the lab by the human - the
same way as on their own machine, otherwise the check proves nothing. There is
no `sudo` inside the machine, and there are two such steps: a line in hosts and
`mkcert -install`. `exec-root` runs a command as root:

```sh
./run.sh up
printf '127.0.0.1 agentschat.local\n' | ./run.sh exec-root \
    'grep -q agentschat.local /etc/hosts || cat >> /etc/hosts'
./run.sh exec 'cd /home/lab/repo && QUOROOM_ADMIN_PASSWORD=<password> ./install.sh --role server --admin-user <name>'
CAROOT=$(./run.sh exec 'mkcert -CAROOT')
./run.sh exec-root "CAROOT=$CAROOT mkcert -install"
./run.sh exec 'cd /home/lab/repo && QUOROOM_ADMIN_PASSWORD=<password> ./install.sh --role server --admin-user <name>'
```

The order matters and repeats the installer. The line in hosts is needed first:
without it `agentschat.local` does not resolve in the machine. The first run of
the installer stops on the certificate trust, because the CA does not exist yet:
the certificate is issued by the installer itself as the user `lab`, and only
after that `mkcert -install` as root with the same `CAROOT` trusts exactly that
one. If the certificate were issued in advance and as root, the CA would belong
to root, and `lab` could not issue its own certificate with it: its key file is
not accessible to `lab`.

The second run continues where it stopped and carries the installation to the
next human step - the room: a human creates it in Element, in the lab
`room-helper.py` under `exec` does it instead (a human step, R4). The third run
with `--room-id` finishes the installation and prints the report.

`CAROOT` is read as the user `lab` (`/home/lab/.local/share/mkcert`): the CA
appears at the first issuance, not on the `-CAROOT` call. The name `CAROOT` in
the command is mandatory: as root it would install its own CA
(`/root/.local/share/mkcert`), which is not the one that signed the issued
certificate, and there would be no trust.

The human issues no certificate of their own: that is a step of the installer,
and `mkcert -install` trusts the one already issued. `exec-root` needs a
brought-up environment (`./run.sh up` above) and, unlike `scenario`, leaves it
running.

`exec` works with input too, so confirmations can be piped in:

```sh
printf 'PURGE\n' | ./run.sh exec './install.sh --role both --remove --purge'
```

If the environment is already up, `scenario` and a new `up` refuse: a foreign
live environment must not be removed. Run `./run.sh down` first.

Under mintty (the Git Bash window without winpty) an interactive `shell` may not
show the prompt: then either `winpty ./run.sh shell`, or `./run.sh exec 'command'`.

## The shared volume and the bind mount

`/home/lab` is the named volume `quoroom-linux-lab_lab-home`, mounted both into
the machine and into the engine. A directory written by the machine is visible to
a container started through the engine with `-v /home/lab/...`, and that is what
the server role needs: its compose mounts `continuwuity.toml`, the Caddyfile and
the certificates by the paths that resolve on the engine side. The scenario
`verify-shared-home` checks this:

```sh
./run.sh scenario verify-shared-home
```

`down -v` removes the volume together with the environment.

## The copy of the repository

The repository is copied by the list of `git ls-files -co --exclude-standard`: the
uncommitted code of the task gets inside, the ignored files
(`bridge/config.yaml`, `docker/.env`,
`docker/continuwuity/continuwuity.toml`, `docker/caddy/certs/`,
`bridge/state/`, `bridge/.venv/`) are never copied.

The copy lives at a path with spaces and Cyrillic; its exact value is
`repo_path` in `run.sh`. Next to it there is the symlink `/home/lab/repo`, which
is what one enters through without typing Cyrillic. A repeated `up` removes the
previous copy entirely, so old files do not survive.

The files that git hands over on the host as `w/crlf` (a consequence of
`core.autocrlf`) are converted to LF: a native Linux clone must not differ from
the lab. The scenario `verify-copy` checks this.

## A shell in the machine

```sh
./run.sh up
./run.sh shell
```

Inside the machine `DOCKER_HOST` points at the engine of the environment, the
stand of the host is not visible from there. The environment lives until it is
removed with `./run.sh down`.

## Live check: Element in a browser on Windows

The Linux scenario is checked like this: the human stops the Windows stand
(`./stop.ps1`), publishes the 443 of the engine on the 443 of the host and opens
Element in a Windows browser at `https://agentschat.local`, accepting the
certificate warning (Windows does not trust the container's CA).

```sh
./stop.ps1                  # in the root of the repository
cd tools/linux-container
./run.sh up --publish-443   # refuses if the 443 of the host is already taken
./run.sh shell              # installing the roles and entering the CLI inside the machine
```

The published 443 is the only thing the environment does with the resources of the
host, and only under that option. The occupancy check looks both at the ports
published by containers and at the listeners on the host itself. By default no
port is published.

## The room for functional runs

A live human creates a room in Element and invites the bots. For runs this step
is replaced by `room-helper.py`: it logs in by password, creates a room and
invites the bots through the client-server API. The script refuses to work
outside the lab (the `QUOROOM_LAB` variable) and verifies the certificate with the
system store; the CA of the machine can be given by the `--ca-file` option.

```sh
./run.sh shell
python3 tools/linux-container/room-helper.py --url https://agentschat.local \
    --user admin --password ... --room-name Quoroom --invite claude-code,opencode
```

## What the environment does not do

- It does not mount the Docker socket of the host and does not see its stand.
- It does not run `docker compose` in the `docker/` directory of the repository on
  the host.
- It does not delete the volumes and containers of other projects: `down -v` is
  called with `-p quoroom-linux-lab`.
- It does not publish ports without `--publish-443`, and then only 443, and only
  when it is free.
- It does not bind-mount the directory of the repository: a copy, not a bind
  mount, otherwise the installer would write into the human's working copy.

## Implementation details worth knowing

- The paths inside the machine, and the Cyrillic in them, travel on stdin: as a
  command-line argument they are mangled at the Windows to `docker.exe` boundary.
- The copy arrives as the stream `git ls-files | tar` into `docker compose exec`;
  no temporary archive is left in the working copy.
- The tests and checks of this directory are not part of `unittest` and of CI:
  everything here is checked by functional runs.
