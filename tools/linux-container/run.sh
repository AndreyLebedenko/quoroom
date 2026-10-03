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
die() { echo "ОШИБКА: $1" >&2; exit 9; }

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
    echo "--- снимок хоста: контейнеры ---"
    docker ps -a --format '{{.Names}}|{{.Status}}|{{.Ports}}'
    echo "--- снимок хоста: тома ---"
    docker volume ls --format '{{.Name}}'
    echo "--- снимок хоста: сети ---"
    docker network ls --format '{{.Name}}'
}

teardown() {
    say "Убираю окружение $project вместе с томами."
    if ! dc down -v --remove-orphans >/tmp/quoroom-lab-down.log 2>&1; then
        echo "ВНИМАНИЕ: окружение убрать не удалось:" >&2
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
        die "порт 443 на хосте уже занят. Остановите стенд Windows (./stop.ps1) и повторите."
    fi
    files="$files -f compose.live.yaml"
    say "Публикую 443 движка на 443 хоста - только для живой проверки."
}

refuse_live_lab() {
    if [ -n "$(dc ps -q 2>/dev/null)" ]; then
        die "окружение $project уже поднято. Сначала ./run.sh down, иначе будет убрано чужое окружение."
    fi
}

wait_for_dind() {
    say "Жду движок Docker внутри окружения."
    i=0
    while [ "$i" -lt 60 ]; do
        if dc exec -T dind docker info >/dev/null 2>&1; then
            return 0
        fi
        i=$((i + 1))
        sleep 1
    done
    die "движок Docker в окружении не поднялся за 60с."
}

prepare_machine() {
    say "Готовлю машину: пользователь lab и его каталог на общем томе."
    dc exec -T --user root machine sh -c '
        set -eu
        id lab >/dev/null 2>&1 || useradd -m -s /bin/bash lab
        mkdir -p /home/lab
        chown lab:lab /home/lab'
}

install_prerequisites() {
    say "Ставлю prerequisites по процедуре Ubuntu 24.04 из гейта 1."
    dc exec -T --user root machine sh -c '
        apt-get update -qq &&
        apt-get install -y \
            python3 python3-venv pipx mkcert libnss3-tools \
            docker.io docker-compose-v2 curl procps git >/dev/null &&
        python3 -V && docker --version && docker compose version'
}

copy_repository() {
    say "Копирую репозиторий по списку git ls-files -co --exclude-standard."
    printf '%s\n' \
        "set -eu" \
        "rm -rf $repo_link '$repo_path'" \
        "mkdir -p $repo_link" \
        | as_lab sh -s
    # Пути, начинающиеся с "/", Git Bash переписывает в пути Windows, поэтому
    # MSYS_NO_PATHCONV на одном этом вызове: кириллица при этом проходит
    # как есть (проверено), а путь внутрь машины остаётся posix.
    git -C "$repo_root" ls-files -co --exclude-standard -z \
        | tar -C "$repo_root" --null -T - -cf - \
        | MSYS_NO_PATHCONV=1 dc exec -T --user lab machine tar -xf - -C "$repo_link"
    crlf_to_lf
    printf '%s\n' \
        "set -eu" \
        "mv $repo_link '$repo_path'" \
        "ln -s '$repo_path' $repo_link" \
        | as_lab sh -s
    say "Копия внутри машины: $repo_path (ссылка $repo_link)."
}

crlf_to_lf() {
    count=$(crlf_list | wc -l | tr -d ' ')
    say "Привожу к LF файлов, которые git отдаёт как w/crlf: $count"
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
            say "Сценарий install-help: install.sh --help внутри машины."
            in_machine './install.sh --help'
            ;;
        verify-copy)
            say "Сценарий verify-copy: что попало в копию репозитория."
            in_machine './tools/linux-container/verify-copy.sh'
            ;;
        verify-shared-home)
            say "Сценарий verify-shared-home: /home/lab один и тот же у машины и движка."
            in_machine './tools/linux-container/verify-shared-home.sh'
            ;;
        *)
            say "Сценарий $name: произвольная команда из скопированного репозитория."
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
    say "Окружение готово. Репозиторий внутри: $repo_path"
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
    if [ "$code" -eq 0 ]; then say "Сценарий $name закончился."; fi
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
                *) die "неизвестный ключ: $1" ;;
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
        [ -n "${1:-}" ] || die "команда: exec '<команда>'"
        [ -n "$(dc ps -q 2>/dev/null)" ] || die "окружение не поднято: сначала ./run.sh up"
        exec_in_machine "$1"
        ;;
    exec-root)
        shift
        [ -n "${1:-}" ] || die "команда: exec-root '<команда>'"
        [ -n "$(dc ps -q 2>/dev/null)" ] || die "окружение не поднято: сначала ./run.sh up"
        say "Команда от root: $*"
        exec_root_in_machine "$1"
        ;;
    shell)
        [ -n "$(dc ps -q 2>/dev/null)" ] || die "окружение не поднято: сначала ./run.sh up"
        say "Оболочка в машине от пользователя lab, репозиторий: $repo_link. Выход: exit."
        MSYS_NO_PATHCONV=1 dc exec --user lab machine sh -lc "cd $repo_link && exec bash"
        ;;
    down) teardown ;;
    *) die "команда: snapshot | up [--publish-443] | scenario [имя] [--publish-443] | exec '<команда>' | exec-root '<команда>' | shell | down" ;;
esac