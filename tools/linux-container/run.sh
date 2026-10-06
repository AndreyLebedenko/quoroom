#!/bin/sh
set -eu

here=$(cd "$(dirname "$0")" && pwd)
cd "$here"
repo_root=$(cd "$here/../.." && pwd)

project=quoroom-linux-lab
repo_path='/home/lab/Репо с пробелом'
repo_link=/home/lab/repo
files="-p $project -f compose.yaml"
publish_443=0

say() { echo "==> $*"; }
die() { echo "ERROR: $1" >&2; exit 9; }

dc() { docker compose $files "$@"; }

as_lab() { dc exec -T --user lab machine "$@"; }

in_machine() {
    printf '%s\n' "set -eu" "cd $repo_link" "$1" | as_lab sh -s
}

host_listens_443() {
    if command -v netstat >/dev/null 2>&1 \
        && netstat -an 2>/dev/null | grep -Eq ':443[[:space:]].*LISTEN'; then
        return 0
    fi
    if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -Eq ':443[[:space:]]'; then
        return 0
    fi
    docker ps --format '{{.Ports}}' 2>/dev/null | grep -q ':443->'
}

snapshot() {
    echo "--- host snapshot: containers ---"
    docker ps -a --format '{{.Names}}|{{.Status}}|{{.Ports}}'
    echo "--- host snapshot: volumes ---"
    docker volume ls --format '{{.Name}}'
    echo "--- host snapshot: networks ---"
    docker network ls --format '{{.Name}}'
}

teardown() {
    say "Removing the environment $project together with its volumes."
    if ! dc down -v --remove-orphans >/tmp/quoroom-lab-down.log 2>&1; then
        echo "WARNING: the environment could not be removed:" >&2
        cat /tmp/quoroom-lab-down.log >&2
        dc ps -a >&2 || true
        docker volume ls --filter "label=com.docker.compose.project=$project" >&2 || true
        docker network ls --filter "label=com.docker.compose.project=$project" >&2 || true
    fi
    rm -f /tmp/quoroom-lab-down.log
}

arm_teardown() {
    trap 'rc=$?; trap - EXIT INT TERM; teardown; snapshot; exit $rc' EXIT
    trap 'exit 130' INT TERM
}

disarm_teardown() {
    trap - EXIT INT TERM
}

want_publish_443() {
    if host_listens_443; then
        die "port 443 on the host is already taken. Stop the Windows stand (./stop.ps1) and repeat."
    fi
    files="$files -f compose.live.yaml"
    say "Publishing the engine 443 on the host 443 - only for the live check."
}

refuse_live_lab() {
    if [ -n "$(dc ps -q 2>/dev/null)" ]; then
        die "the environment $project is already up. Run ./run.sh down first, otherwise a foreign environment is removed."
    fi
}

wait_for_dind() {
    say "Waiting for the Docker engine inside the environment."
    i=0
    while [ "$i" -lt 60 ]; do
        if dc exec -T dind docker info >/dev/null 2>&1; then
            return 0
        fi
        i=$((i + 1))
        sleep 1
    done
    die "the Docker engine in the environment did not come up in 60s."
}

prepare_machine() {
    say "Preparing the machine: the lab user and its home on the shared volume."
    dc exec -T --user root machine sh -c '
        set -eu
        id lab >/dev/null 2>&1 || useradd -m -s /bin/bash lab
        mkdir -p /home/lab
        chown lab:lab /home/lab'
}

install_prerequisites() {
    say "Installing the prerequisites by the Ubuntu 24.04 procedure of gate 1."
    dc exec -T --user root machine sh -c '
        apt-get update -qq &&
        apt-get install -y \
            python3 python3-venv pipx mkcert libnss3-tools \
            docker.io docker-compose-v2 curl procps git >/dev/null &&
        python3 -V && docker --version && docker compose version'
}

copy_repository() {
    say "Copying the repository by the list of git ls-files -co --exclude-standard."
    printf '%s\n' \
        "set -eu" \
        "rm -rf $repo_link '$repo_path'" \
        "mkdir -p $repo_link" \
        | as_lab sh -s
    # Paths that start with "/" are rewritten by Git Bash into Windows paths, so
    # MSYS_NO_PATHCONV on this one call: the Cyrillic of the copy path passes
    # through as is (verified), and the path inside the machine stays posix.
    git -C "$repo_root" ls-files -co --exclude-standard -z \
        | tar -C "$repo_root" --null -T - -cf - \
        | MSYS_NO_PATHCONV=1 dc exec -T --user lab machine tar -xf - -C "$repo_link"
    crlf_to_lf
    printf '%s\n' \
        "set -eu" \
        "mv $repo_link '$repo_path'" \
        "ln -s '$repo_path' $repo_link" \
        | as_lab sh -s
    say "The copy inside the machine: $repo_path (link $repo_link)."
}

crlf_to_lf() {
    count=$(crlf_list | wc -l | tr -d ' ')
    say "Converting to LF the files that git hands over as w/crlf: $count"
    crlf_list | as_lab sh -c '
        set -eu
        cd /home/lab/repo
        while IFS= read -r file; do
            [ -n "$file" ] || continue
            tr -d "\r" < "$file" > "$file.lf"
            mv "$file.lf" "$file"
        done'
}

crlf_list() {
    git -C "$repo_root" ls-files --eol \
        | awk '$2 == "w/crlf" && $3 !~ /-text/ {print}' \
        | cut -f2-
}

run_command() {
    name=$1
    command=$2
    case "$name" in
        install-help)
            say "Scenario install-help: install.sh --help inside the machine."
            in_machine './install.sh --help'
            ;;
        verify-copy)
            say "Scenario verify-copy: what got into the repository copy."
            in_machine './tools/linux-container/verify-copy.sh'
            ;;
        verify-shared-home)
            say "Scenario verify-shared-home: /home/lab is one and the same for the machine and the engine."
            in_machine './tools/linux-container/verify-shared-home.sh'
            ;;
        *)
            say "Scenario $name: an arbitrary command from the copied repository."
            in_machine "${command:-$name}"
            ;;
    esac
}

up() {
    refuse_live_lab
    if [ "$publish_443" = 1 ]; then
        want_publish_443
    fi
    snapshot
    arm_teardown
    dc up -d
    wait_for_dind
    prepare_machine
    install_prerequisites
    copy_repository
    say "The environment is ready. The repository inside: $repo_path"
    snapshot
    disarm_teardown
}

scenario() {
    name=${1:-install-help}
    command=${2:-}
    refuse_live_lab
    if [ "$publish_443" = 1 ]; then
        want_publish_443
    fi
    snapshot
    arm_teardown
    dc up -d
    wait_for_dind
    prepare_machine
    install_prerequisites
    copy_repository
    set +e
    run_command "$name" "$command"
    code=$?
    set -e
    if [ "$code" -eq 0 ]; then say "Scenario $name finished."; fi
    exit "$code"
}

exec_in_machine() {
    MSYS_NO_PATHCONV=1 dc exec -T -e LAB_COMMAND="$1" --user lab machine \
        sh -lc 'cd /home/lab/repo && exec sh -c "$LAB_COMMAND"'
}

exec_root_in_machine() {
    MSYS_NO_PATHCONV=1 dc exec -T -e LAB_COMMAND="$1" --user root machine \
        sh -lc 'cd /home/lab/repo && exec sh -c "$LAB_COMMAND"'
}

case "${1:-}" in
    snapshot) snapshot ;;
    up) shift; while [ $# -gt 0 ]; do
            case "$1" in
                --publish-443) publish_443=1 ;;
                *) die "unknown option: $1" ;;
            esac
            shift
        done
        up ;;
    scenario) shift; while [ $# -gt 0 ]; do
            case "$1" in
                --publish-443) publish_443=1 ;;
                *) scenario_name=$1 ;;
            esac
            shift
        done
        scenario "${scenario_name:-install-help}" ;;
    exec)
        shift
        [ -n "${1:-}" ] || die "command: exec '<command>'"
        [ -n "$(dc ps -q 2>/dev/null)" ] || die "the environment is not up: run ./run.sh up first"
        exec_in_machine "$1"
        ;;
    exec-root)
        shift
        [ -n "${1:-}" ] || die "command: exec-root '<command>'"
        [ -n "$(dc ps -q 2>/dev/null)" ] || die "the environment is not up: run ./run.sh up first"
        say "Command from root: $*"
        exec_root_in_machine "$1"
        ;;
    shell)
        [ -n "$(dc ps -q 2>/dev/null)" ] || die "the environment is not up: run ./run.sh up first"
        say "A shell in the machine as the lab user, the repository: $repo_link. To leave: exit."
        MSYS_NO_PATHCONV=1 dc exec --user lab machine sh -lc "cd $repo_link && exec bash"
        ;;
    down) teardown ;;
    *) die "command: snapshot | up [--publish-443] | scenario [name] [--publish-443] | exec '<command>' | exec-root '<command>' | shell | down" ;;
esac
