#!/usr/bin/env python3
"""
A small helper that registers an account on Continuwuity through the Matrix
Client-Server API (User-Interactive Auth, m.login.registration_token), so that
nobody has to assemble the two-step curl by hand.

Example:

    python register_account.py \\
        --homeserver https://agentschat.local \\
        --username claude-code \\
        --password "a-long-random-password" \\
        --registration-token "the REGISTRATION_TOKEN value from docker/.env"

The messages are English; `--lang ru` prints them in Russian.

About TLS: `mkcert -install` adds the root certificate to the Windows system
store, so browsers trust it. The `requests` library that this script uses does
not read the system store - it trusts only its own set of CAs (the certifi
package). So even after `mkcert -install` this script fails with
`CERTIFICATE_VERIFY_FAILED` unless it is told where the mkcert root is:

    --ca-bundle "$(mkcert -CAROOT)\\rootCA.pem"

(this is not a setup mistake but a property of requests/certifi - Continuwuity
itself and the bridge on aiohttp/matrix-nio read the Windows system store
normally). If you do not want to bother, the blunter --no-verify-ssl turns the
certificate check off completely (fit only for this one local call).

It prints user_id / access_token / device_id - paste them into
bridge/config.yaml for the matching agent (or keep them as your own observer
account, if the username is you and not a bot).
"""

import argparse
import json
import sys
from pathlib import Path

import requests

from sessionchat.i18n import DEFAULT_LANGUAGE, LANGUAGES, Catalogue

CATALOGUE = Catalogue.from_path(Path(__file__).resolve().parent / "register_messages")


def message(lang: str, key: str, **params: object) -> str:
    return CATALOGUE.text(lang, key, **params)


def fail(lang: str, key: str, **params: object) -> None:
    print(message(lang, key, **params), file=sys.stderr)
    sys.exit(1)


def register(
    homeserver: str,
    username: str,
    password: str,
    token: str,
    device_name: str,
    verify: "bool | str",
    lang: str = DEFAULT_LANGUAGE,
) -> dict:
    url = f"{homeserver.rstrip('/')}/_matrix/client/v3/register"

    r1 = requests.post(
        url,
        json={
            "username": username,
            "password": password,
            "initial_device_display_name": device_name,
        },
        verify=verify,
    )

    if r1.status_code == 200:
        return r1.json()

    if r1.status_code != 401:
        fail(lang, "unexpected_step_one", status=r1.status_code, text=r1.text)

    session = r1.json().get("session")
    if not session:
        fail(lang, "no_session", text=r1.text)

    r2 = requests.post(
        url,
        json={
            "username": username,
            "password": password,
            "initial_device_display_name": device_name,
            "auth": {
                "type": "m.login.registration_token",
                "token": token,
                "session": session,
            },
        },
        verify=verify,
    )

    if r2.status_code != 200:
        fail(lang, "registration_failed", status=r2.status_code, text=r2.text)

    return r2.json()


def chosen_language(argv: list[str] | None) -> str:
    probe = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    probe.add_argument("--lang", choices=LANGUAGES, default=DEFAULT_LANGUAGE)
    return probe.parse_known_args(argv)[0].lang


def build_parser(lang: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=message(lang, "description"))
    parser.add_argument(
        "--homeserver", required=True, help=message(lang, "homeserver_help")
    )
    parser.add_argument(
        "--username", required=True, help=message(lang, "username_help")
    )
    parser.add_argument("--password", required=True)
    parser.add_argument("--registration-token", required=True, dest="token")
    parser.add_argument("--device-name", default="agentschat-bridge")
    parser.add_argument(
        "--ca-bundle", default=None, help=message(lang, "ca_bundle_help")
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help=message(lang, "no_verify_ssl_help"),
    )
    parser.add_argument(
        "--lang",
        choices=LANGUAGES,
        default=DEFAULT_LANGUAGE,
        help=message(lang, "lang_help"),
    )
    return parser


def main(argv: list[str] | None = None):
    lang = chosen_language(argv)
    args = build_parser(lang).parse_args(argv)

    if args.no_verify_ssl:
        verify = False
    elif args.ca_bundle:
        verify = args.ca_bundle
    else:
        verify = True

    try:
        data = register(
            homeserver=args.homeserver,
            username=args.username,
            password=args.password,
            token=args.token,
            device_name=args.device_name,
            verify=verify,
            lang=lang,
        )
    except requests.exceptions.SSLError:
        fail(lang, "certificate_failed")

    print(json.dumps(data, indent=2, ensure_ascii=False))
    print(message(lang, "paste_heading"))
    print(f'user_id: "{data.get("user_id")}"')
    print(f'access_token: "{data.get("access_token")}"')
    print(f'device_id: "{data.get("device_id")}"')


if __name__ == "__main__":
    main()
