#!/bin/sh
# Quoroom - start the whole local stand (Docker + broker). The counterpart of
# start.ps1. The macOS/Linux variant, not verified live on either, like
# bridge/agentschat. First-time setup is in docs/INSTALL.md.
#
#   ./start.sh
#   ./start.sh --lang ru
#
# Messages are printed in the room language: --lang en|ru if given, otherwise
# the language key of bridge/config.yaml, otherwise English.
set -eu

root=$(cd "$(dirname "$0")" && pwd)
docker_dir="$root/docker"
bridge_dir="$root/bridge"
config_file="$bridge_dir/config.yaml"
log_file="$bridge_dir/broker.log"
pid_file="$bridge_dir/state/broker.pid"
broker_port=8770

language=""
asked=0
previous=""
for argument in "$@"; do
    case "$argument" in
        --lang=*) language="${argument#--lang=}"; asked=1 ;;
        --lang) language=""; asked=1 ;;
        *) if [ "$previous" = "--lang" ]; then language="$argument"; fi ;;
    esac
    previous="$argument"
done
if [ "$asked" -eq 0 ] && [ -f "$config_file" ]; then
    language=$(sed -n '/^language:/{s/^language:[[:space:]]*//p;q;}' "$config_file" |
        sed -e 's/[[:space:]]*#.*$//' -e 's/[[:space:]]*$//' \
            -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/")
fi

if [ "$language" = "ru" ]; then
    error_label="ОШИБКА"
    docker_missing="docker не найден (docs/INSTALL.md, шаг 0)."
    docker_down="Docker-демон не отвечает. Запустите Docker."
    no_env="нет docker/.env (docs/INSTALL.md, шаг 3)."
    no_config="нет bridge/config.yaml (docs/INSTALL.md, шаг 7)."
    stack_up="==> Поднимаю Docker-стек (Continuwuity, Element, Caddy)..."
    waiting="==> Жду готовности Matrix-сервера (порт 443)..."
    already_running="==> Брокер уже работает (PID %s) - второй не запускаю."
    starting="==> Запускаю брокер (лог: bridge/broker.log)..."
    started="==> Брокер запущен (PID %s, порт %s)."
    all_done="Готово. Element Web: https://agentschat.local"
    next_step="Дальше в каждой сессии CLI вызвать /chatlogin. Остановить всё: ./stop.sh"
else
    error_label="ERROR"
    docker_missing="docker was not found (docs/INSTALL.md, step 0)."
    docker_down="The Docker daemon is not responding. Start Docker."
    no_env="docker/.env is missing (docs/INSTALL.md, step 3)."
    no_config="bridge/config.yaml is missing (docs/INSTALL.md, step 7)."
    stack_up="==> Starting the Docker stack (Continuwuity, Element, Caddy)..."
    waiting="==> Waiting for the Matrix server (port 443)..."
    already_running="==> The broker is already running (PID %s) - not starting a second one."
    starting="==> Starting the broker (log: bridge/broker.log)..."
    started="==> The broker has been started (PID %s, port %s)."
    all_done="Done. Element Web: https://agentschat.local"
    next_step="Next, call /chatlogin in each CLI session. To stop everything: ./stop.sh"
fi

fail() {
    printf '%s: %s\n' "$error_label" "$1"
    exit 1
}

if [ -x "$bridge_dir/.venv/bin/python" ]; then
    python="$bridge_dir/.venv/bin/python"
else
    python=python3
fi

command -v docker >/dev/null 2>&1 || fail "$docker_missing"
docker info >/dev/null 2>&1 || fail "$docker_down"
[ -f "$docker_dir/.env" ] || fail "$no_env"
[ -f "$config_file" ] || fail "$no_config"

printf '%s\n' "$stack_up"
( cd "$docker_dir" && docker compose up -d )

printf '%s\n' "$waiting"
i=0
while [ "$i" -lt 30 ]; do
    if curl -k -s -o /dev/null https://agentschat.local 2>/dev/null; then break; fi
    i=$((i + 1))
    sleep 2
done

if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file" 2>/dev/null)" 2>/dev/null; then
    printf "$already_running\n" "$(cat "$pid_file")"
else
    mkdir -p "$(dirname "$pid_file")"
    printf '%s\n' "$starting"
    (
        cd "$bridge_dir"
        PYTHONPATH="$bridge_dir" nohup "$python" -X utf8 -m sessionchat.broker \
            --config config.yaml --verbose >"$log_file" 2>&1 &
        echo $! >"$pid_file"
    )
    printf "$started\n" "$(cat "$pid_file")" "$broker_port"
fi

echo ""
printf '%s\n' "$all_done"
printf '%s\n' "$next_step"
