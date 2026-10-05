#!/bin/sh
# Quoroom - install and remove one machine with one command:
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

language=en
previous=""
for argument in "$@"; do
    case "$argument" in
        --lang=*) language="${argument#--lang=}" ;;
        *) if [ "$previous" = "--lang" ]; then language="$argument"; fi ;;
    esac
    previous="$argument"
done

if [ "$language" = "ru" ]; then
    error_label="ОШИБКА"
    layer_missing="общий слой установщика не найден: %s. Запускайте скрипт из корня репозитория Quoroom."
    python_missing="подходящий Python не найден: нужен 3.10 или новее (bridge/pyproject.toml, requires-python). Установите его и повторите: sudo apt install python3"
else
    error_label="ERROR"
    layer_missing="the shared installer layer was not found: %s. Run the script from the root of the Quoroom repository."
    python_missing="no suitable Python found: 3.10 or newer is required (bridge/pyproject.toml, requires-python). Install it and run again: sudo apt install python3"
fi

fail() {
    printf '%s: ' "$error_label" >&2
    printf "$1\n" "${2-}" >&2
    exit "$missing_python"
}

[ -f "$layer" ] || fail "$layer_missing" "$layer"

probe='import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
python_bin=""
for candidate in python3 python; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -c "$probe" >/dev/null 2>&1; then
        python_bin="$candidate"
        break
    fi
done
[ -n "$python_bin" ] || fail "$python_missing"

PYTHONPATH="$bridge"
PYTHONIOENCODING=utf-8
PYTHONUTF8=1
export PYTHONPATH PYTHONIOENCODING PYTHONUTF8

exec "$python_bin" -X utf8 -m sessionchat.installer "$@"