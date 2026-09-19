#!/bin/sh
# Quoroom - поднять весь локальный стенд (Docker + брокер). Аналог start.ps1.
# ВНИМАНИЕ: вариант для macOS/Linux; вживую на них не проверялся, как и
# bridge/agentschat. Первичная настройка - в docs/INSTALL.md.
set -eu

root=$(cd "$(dirname "$0")" && pwd)
docker_dir="$root/docker"
bridge_dir="$root/bridge"
log_file="$bridge_dir/broker.log"
pid_file="$bridge_dir/state/broker.pid"
broker_port=8770

if [ -x "$bridge_dir/.venv/bin/python" ]; then
    python="$bridge_dir/.venv/bin/python"
else
    python=python3
fi

command -v docker >/dev/null 2>&1 || { echo "ОШИБКА: docker не найден (docs/INSTALL.md, шаг 0)."; exit 1; }
docker info >/dev/null 2>&1 || { echo "ОШИБКА: Docker-демон не отвечает. Запустите Docker."; exit 1; }
[ -f "$docker_dir/.env" ] || { echo "ОШИБКА: нет docker/.env (docs/INSTALL.md, шаг 3)."; exit 1; }
[ -f "$bridge_dir/config.yaml" ] || { echo "ОШИБКА: нет bridge/config.yaml (docs/INSTALL.md, шаг 7)."; exit 1; }

echo "==> Поднимаю Docker-стек (Continuwuity, Element, Caddy)..."
( cd "$docker_dir" && docker compose up -d )

echo "==> Жду готовности Matrix-сервера (порт 443)..."
i=0
while [ "$i" -lt 30 ]; do
    if curl -k -s -o /dev/null https://agentschat.local 2>/dev/null; then break; fi
    i=$((i + 1))
    sleep 2
done

if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file" 2>/dev/null)" 2>/dev/null; then
    echo "==> Брокер уже работает (PID $(cat "$pid_file")) - второй не запускаю."
else
    mkdir -p "$(dirname "$pid_file")"
    echo "==> Запускаю брокер (лог: bridge/broker.log)..."
    (
        cd "$bridge_dir"
        PYTHONPATH="$bridge_dir" nohup "$python" -X utf8 -m sessionchat.broker \
            --config config.yaml --verbose >"$log_file" 2>&1 &
        echo $! >"$pid_file"
    )
    echo "==> Брокер запущен (PID $(cat "$pid_file"), порт $broker_port)."
fi

echo ""
echo "Готово. Element Web: https://agentschat.local"
echo "Дальше в каждой сессии CLI вызвать /chatlogin. Остановить всё: ./stop.sh"
