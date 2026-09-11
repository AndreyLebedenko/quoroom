#!/usr/bin/env python3
"""
Небольшой помощник для регистрации аккаунта на Continuwuity через
Matrix Client-Server API (User-Interactive Auth, m.login.registration_token),
чтобы не собирать вручную двухшаговый curl.

Пример:

    python register_account.py \\
        --homeserver https://agentschat.local \\
        --username claude-code \\
        --password "длинный-случайный-пароль" \\
        --registration-token "значение REGISTRATION_TOKEN из docker/.env"

ВАЖНО про TLS: `mkcert -install` добавляет корневой сертификат в системное
хранилище Windows, поэтому браузеры ему доверяют. Библиотека `requests`,
которую использует этот скрипт, системное хранилище НЕ читает — она
доверяет только своему собственному набору CA (пакет certifi). Поэтому даже
после `mkcert -install` этот скрипт будет падать с
`CERTIFICATE_VERIFY_FAILED`, если явно не указать ему путь к корню mkcert:

    --ca-bundle "$(mkcert -CAROOT)\rootCA.pem"

(это не баг настройки, а особенность requests/certifi — сам Continuwuity и
мост на aiohttp/matrix-nio системное хранилище Windows читают нормально).
Если совсем не хочется возиться — есть более грубый --no-verify-ssl
(полностью отключает проверку сертификата, годится только для этого
локального разового вызова).

Выводит user_id / access_token / device_id — их нужно вставить в
bridge/config.yaml для соответствующего агента (или сохранить как ваш личный
аккаунт-наблюдатель, если username — это вы, а не бот).
"""

import argparse
import json
import sys

import requests


def register(
    homeserver: str,
    username: str,
    password: str,
    token: str,
    device_name: str,
    verify: "bool | str",
) -> dict:
    """verify: True (обычная проверка), False (без проверки) или путь к
    файлу CA-бандла (например, к rootCA.pem от mkcert)."""
    url = f"{homeserver.rstrip('/')}/_matrix/client/v3/register"

    # Шаг 1: сервер должен ответить 401 со списком доступных auth-flow и session id.
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
        # Некоторые серверы при выключенной UIA могут зарегистрировать сразу.
        return r1.json()

    if r1.status_code != 401:
        print(
            f"Неожиданный ответ на шаге 1: {r1.status_code} {r1.text}", file=sys.stderr
        )
        sys.exit(1)

    session = r1.json().get("session")
    if not session:
        print(f"В ответе сервера нет session: {r1.text}", file=sys.stderr)
        sys.exit(1)

    # Шаг 2: повторяем запрос с указанием auth.
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
        print(f"Регистрация не удалась: {r2.status_code} {r2.text}", file=sys.stderr)
        sys.exit(1)

    return r2.json()


def main():
    parser = argparse.ArgumentParser(description="Регистрация аккаунта на Continuwuity")
    parser.add_argument(
        "--homeserver", required=True, help="например https://agentschat.local"
    )
    parser.add_argument(
        "--username", required=True, help="localpart, например claude-code"
    )
    parser.add_argument("--password", required=True)
    parser.add_argument("--registration-token", required=True, dest="token")
    parser.add_argument("--device-name", default="agentschat-bridge")
    parser.add_argument(
        "--ca-bundle",
        default=None,
        help=r'путь к rootCA.pem из mkcert, например "$(mkcert -CAROOT)\rootCA.pem"',
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="полностью отключить проверку сертификата (грубее, чем --ca-bundle)",
    )
    args = parser.parse_args()

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
        )
    except requests.exceptions.SSLError:
        print(
            "\nОшибка проверки сертификата. requests не читает системное хранилище "
            "Windows, куда mkcert -install кладёт свой корень. Добавьте:\n"
            r'    --ca-bundle "$(mkcert -CAROOT)\rootCA.pem"'
            "\n"
            "к этой же команде и запустите заново.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("\n--- вставить в bridge/config.yaml ---")
    print(f'user_id: "{data.get("user_id")}"')
    print(f'access_token: "{data.get("access_token")}"')
    print(f'device_id: "{data.get("device_id")}"')


if __name__ == "__main__":
    main()
