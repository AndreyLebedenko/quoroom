#!/bin/sh
set -eu

repo=/home/lab/repo
cd "$repo"

echo "репозиторий: $repo"
echo "файлов в копии: $(find . -type f | wc -l)"
echo "владелец: $(stat -c '%U' "$repo")"

for secret in bridge/config.yaml bridge/config.yaml.local docker/.env \
    docker/continuwuity/continuwuity.toml bridge/state bridge/.venv \
    docker/caddy/certs; do
    if [ -e "$secret" ]; then
        echo "СЕКРЕТ ПОПАЛ В КОПИЮ: $secret"
        exit 1
    fi
done
echo "игнорируемых секретов в копии нет"

for tracked in install.sh install.ps1 tools/linux-container/run.sh \
    tools/linux-container/room-helper.py; do
    [ -f "$tracked" ] || { echo "нет ожидаемого файла: $tracked"; exit 1; }
done
echo "файлы задачи на месте: install.sh, install.ps1, run.sh, room-helper.py"

if grep -q 'ЛАБОРАТОРНЫЙ МАРКЕР' README.md; then
    echo "незакоммиченная правка README.md видна в копии"
else
    echo "незакоммиченной правки README.md в копии нет"
fi

if grep -q "$(printf '\r')" bridge/sessionchat/kit/opencode/plugins/agentschat.js; then
    echo "CR ОСТАЛСЯ в файле, который git отдаёт как w/crlf"
    exit 1
fi
echo "в файле, который git отдаёт как w/crlf, нет ни одного CR"

id lab
if [ "$(id -u)" = 0 ]; then
    echo "СЦЕНАРИЙ ИДЁТ ОТ ROOT, А НЕ ОТ lab"
    exit 1
fi
echo "сценарий идёт от пользователя lab без sudo"
sudo -n true 2>/dev/null && { echo "У lab ЕСТЬ sudo"; exit 1; }
echo "у lab нет sudo"