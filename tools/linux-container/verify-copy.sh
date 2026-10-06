#!/bin/sh
set -eu

repo=/home/lab/repo
cd "$repo"

echo "repository: $repo"
echo "files in the copy: $(find . -type f | wc -l)"
echo "owner: $(stat -c '%U' "$repo")"

for secret in bridge/config.yaml bridge/config.yaml.local docker/.env \
    docker/continuwuity/continuwuity.toml bridge/state bridge/.venv \
    docker/caddy/certs; do
    if [ -e "$secret" ]; then
        echo "A SECRET GOT INTO THE COPY: $secret"
        exit 1
    fi
done
echo "no ignored secret is in the copy"

for tracked in install.sh install.ps1 tools/linux-container/run.sh \
    tools/linux-container/room-helper.py; do
    [ -f "$tracked" ] || { echo "an expected file is missing: $tracked"; exit 1; }
done
echo "the files of the task are in place: install.sh, install.ps1, run.sh, room-helper.py"

if grep -q 'LAB MARKER' README.md; then
    echo "an uncommitted edit of README.md is visible in the copy"
else
    echo "there is no uncommitted edit of README.md in the copy"
fi

if grep -q "$(printf '\r')" bridge/sessionchat/kit/opencode/plugins/agentschat.js; then
    echo "A CR REMAINED in a file that git hands over as w/crlf"
    exit 1
fi
echo "the file that git hands over as w/crlf has no CR at all"

id lab
if [ "$(id -u)" = 0 ]; then
    echo "THE SCENARIO RUNS AS root, NOT AS lab"
    exit 1
fi
echo "the scenario runs as the lab user without sudo"
sudo -n true 2>/dev/null && { echo "lab HAS sudo"; exit 1; }
echo "lab has no sudo"
