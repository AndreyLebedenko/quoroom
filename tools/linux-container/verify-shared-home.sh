#!/bin/sh
set -eu

probe=/home/lab/probe
marker="проверка общего тома"

rm -rf "$probe"
mkdir -p "$probe"
printf '%s\n' "$marker" > "$probe/файл.txt"

seen=$(docker run --rm -v "$probe:/p" ubuntu:24.04 cat "/p/файл.txt" 2>/dev/null || true)
if [ "$seen" != "$marker" ]; then
    echo "THE ENGINE DOES NOT SEE THE MACHINE DIRECTORY: it sees '$seen'"
    exit 1
fi

rm -rf "$probe"
echo "a directory written by the machine is visible to a container started through the engine"
