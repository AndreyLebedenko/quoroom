import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request


def refuse(reason: str) -> None:
    sys.exit(
        f"{reason}\n"
        "This script works only inside the lab "
        "(tools/linux-container) and must not talk to a live stand."
    )


def call(
    url: str,
    method: str,
    token: str | None = None,
    payload: dict | None = None,
    context: ssl.SSLContext | None = None,
):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("content-type", "application/json")
    if token:
        request.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        sys.exit(f"HTTP {error.code} at {url}: {detail}")


def main() -> None:
    if os.environ.get("QUOROOM_LAB") != "1":
        refuse("outside the lab QUOROOM_LAB is not set")

    parser = argparse.ArgumentParser(description="the room for functional runs")
    parser.add_argument("--url", default="https://agentschat.local")
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--room-name", default="Quoroom")
    parser.add_argument("--invite", default="")
    parser.add_argument("--ca-file", default="")
    arguments = parser.parse_args()

    context = ssl.create_default_context(cafile=arguments.ca_file or None)
    base = arguments.url.rstrip("/")
    logged = call(
        f"{base}/_matrix/client/v3/login",
        "POST",
        payload={
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": arguments.user},
            "password": arguments.password,
        },
        context=context,
    )
    token = logged["access_token"]
    created = call(
        f"{base}/_matrix/client/v3/createRoom",
        "POST",
        token,
        {"name": arguments.room_name, "preset": "private_chat", "is_direct": False},
        context,
    )
    room = created["room_id"]
    for bot in [name.strip() for name in arguments.invite.split(",") if name.strip()]:
        call(
            f"{base}/_matrix/client/v3/rooms/{urllib.parse.quote(room)}/invite",
            "POST",
            token,
            {"user_id": f"@{bot}:agentschat.local"},
            context,
        )
        print(f"invited @{bot}")
    print(f"room {room} created, account: {arguments.user}")


if __name__ == "__main__":
    main()
