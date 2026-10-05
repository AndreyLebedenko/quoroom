#!/bin/sh
# Quoroom - stop the whole stand (broker + Docker). The counterpart of
# stop.ps1. The named Docker volumes are kept, so no data is lost.
# The macOS/Linux variant, not verified live.
#
#   ./stop.sh                # stop the broker and bring the containers down
#   ./stop.sh --keep-docker  # stop only the broker
#   ./stop.sh --lang ru
#
# Messages are printed in the room language: --lang en|ru if given, otherwise
# the language key of bridge/config.yaml, otherwise English.
set -u

root=$(cd "$(dirname "$0")" && pwd)
docker_dir="$root/docker"
bridge_dir="$root/bridge"
config_file="$bridge_dir/config.yaml"
pid_file="$bridge_dir/state/broker.pid"

language=""
asked=0
keep_docker=0
previous=""
for argument in "$@"; do
    case "$argument" in
        --keep-docker) keep_docker=1 ;;
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
    stopping_broker="==> Останавливаю брокер (PID %s)..."
    stopping_found="==> Останавливаю брокер по командной строке: %s"
    not_running="==> Брокер не запущен."
    docker_kept="==> Docker оставлен поднятым."
    stopping_docker="==> Опускаю Docker-стек (тома с данными сохраняются)..."
    down_failed="ПРЕДУПРЕЖДЕНИЕ: docker compose down вернул ошибку (возможно, демон не запущен)."
    all_done="Готово."
else
    stopping_broker="==> Stopping the broker (PID %s)..."
    stopping_found="==> Stopping the broker found by its command line: %s"
    not_running="==> The broker is not running."
    docker_kept="==> Docker is left running."
    stopping_docker="==> Bringing the Docker stack down (the data volumes are kept)..."
    down_failed="WARNING: docker compose down returned an error (the daemon may not be running)."
    all_done="Done."
fi

stopped=0
if [ -f "$pid_file" ]; then
    bpid=$(cat "$pid_file" 2>/dev/null || true)
    if [ -n "${bpid:-}" ] && kill -0 "$bpid" 2>/dev/null; then
        printf "$stopping_broker\n" "$bpid"
        kill "$bpid" 2>/dev/null || true
        stopped=1
    fi
    rm -f "$pid_file"
fi

if [ "$stopped" -eq 0 ]; then
    pids=$(pgrep -f 'sessionchat\.broker' 2>/dev/null || true)
    if [ -n "$pids" ]; then
        printf "$stopping_found\n" "$pids"
        kill $pids 2>/dev/null || true
        stopped=1
    fi
fi
[ "$stopped" -eq 0 ] && printf '%s\n' "$not_running"

if [ "$keep_docker" -eq 1 ]; then
    printf '%s\n' "$docker_kept"
else
    printf '%s\n' "$stopping_docker"
    ( cd "$docker_dir" && docker compose down ) || printf '%s\n' "$down_failed"
fi

printf '%s\n' "$all_done"
