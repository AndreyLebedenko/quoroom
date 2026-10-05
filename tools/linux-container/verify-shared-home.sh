#!/bin/sh
set -eu

probe=/home/lab/probe
marker="проверка общего тома"

rm -rf "$probe"
mkdir -p "$probe"
printf '%s\n' "$marker" > "$probe/файл.txt"

seen=$(docker run --rm -v "$probe:/p" ubuntu:24.04 cat "/p/файл.txt" 2>/dev/null || true)
if [ "$seen" != "$marker" ]; then
    echo "ДВИЖОК НЕ ВИДИТ КАТАЛОГ МАШИНЫ: виден '$seen'"
    exit 1
fi

rm -rf "$probe"
echo "каталог, записанный машиной, виден контейнеру, запущенному через движок"