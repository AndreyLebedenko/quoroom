#!/bin/sh
# Quoroom - установка и удаление одной машиной одной командой:
#
#     ./install.sh
#     ./install.sh --role both
#     ./install.sh --role participant --remove
#     ./install.sh --role server --remove --purge
set -eu

root=$(cd "$(dirname "$0")" && pwd)
bridge="$root/bridge"
layer="$bridge/sessionchat/installer/__main__.py"
missing_python=9

fail() {
    echo "ОШИБКА: $1" >&2
    exit "$missing_python"
}

[ -f "$layer" ] || fail "общий слой установщика не найден: $layer. Запускайте скрипт из корня репозитория Quoroom."

probe='import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
python_bin=""
for candidate in python3 python; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -c "$probe" >/dev/null 2>&1; then
        python_bin="$candidate"
        break
    fi
done
[ -n "$python_bin" ] || fail "подходящий Python не найден: нужен 3.10 или новее (bridge/pyproject.toml, requires-python). Установите его и повторите: sudo apt install python3"

PYTHONPATH="$bridge"
PYTHONIOENCODING=utf-8
PYTHONUTF8=1
export PYTHONPATH PYTHONIOENCODING PYTHONUTF8

exec "$python_bin" -X utf8 -m sessionchat.installer "$@"