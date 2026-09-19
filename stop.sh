#!/bin/sh
# Quoroom - остановить весь стенд (брокер + Docker). Аналог stop.ps1.
# Именованные Docker-тома сохраняются - данные не теряются.
# ВНИМАНИЕ: вариант для macOS/Linux; вживую не проверялся.
#
#   ./stop.sh                # остановить брокер и опустить контейнеры
#   ./stop.sh --keep-docker  # остановить только брокер
set -u

root=$(cd "$(dirname "$0")" && pwd)
docker_dir="$root/docker"
bridge_dir="$root/bridge"
pid_file="$bridge_dir/state/broker.pid"

stopped=0
if [ -f "$pid_file" ]; then
    bpid=$(cat "$pid_file" 2>/dev/null || true)
    if [ -n "${bpid:-}" ] && kill -0 "$bpid" 2>/dev/null; then
        echo "==> Останавливаю брокер (PID $bpid)..."
        kill "$bpid" 2>/dev/null || true
        stopped=1
    fi
    rm -f "$pid_file"
fi

if [ "$stopped" -eq 0 ]; then
    pids=$(pgrep -f 'sessionchat\.broker' 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "==> Останавливаю брокер по командной строке: $pids"
        # shellcheck disable=SC2086
        kill $pids 2>/dev/null || true
        stopped=1
    fi
fi
[ "$stopped" -eq 0 ] && echo "==> Брокер не запущен."

if [ "${1:-}" = "--keep-docker" ]; then
    echo "==> Docker оставлен поднятым."
else
    echo "==> Опускаю Docker-стек (тома с данными сохраняются)..."
    ( cd "$docker_dir" && docker compose down ) || \
        echo "ПРЕДУПРЕЖДЕНИЕ: docker compose down вернул ошибку (возможно, демон не запущен)."
fi

echo "Готово."
