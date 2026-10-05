#!/usr/bin/env python3
"""Клиент чата сессий: этим CLI пользуется сам агент изнутри своей сессии.

Ключевая команда — wait. Она блокируется до входящего сообщения, печатает
конверт и ВЫХОДИТ. Выход фонового процесса будит сессию средствами самого
CLI-агента: именно так доставляются непрошеные сообщения.

Второе назначение wait — сторожить себя. Если брокер недоступен дольше
DEAF_SECONDS, процесс жив, но глух, а значит бесполезен: он завершается с
кодом 1, чем будит сессию и вынуждает поднять себя заново.

    agentschat login  --agent claude-code --label "рефакторинг авторизации"
    agentschat wait   --agent claude-code      # в фоне
    agentschat say    --agent claude-code "однострочный текст"
    agentschat say    --agent claude-code --file письмо.md   # многострочный
    agentschat ask    --agent claude-code --timeout 300 "вопрос"
    agentschat inbox  --agent claude-code     # забрать очередь
    agentschat status
    agentschat logout --agent claude-code [--force]
    agentschat install   [--claude] [--opencode] [--force] [--json]
    agentschat uninstall [--claude] [--opencode] [--force] [--json]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

from . import kit
from .client_language import RoomLanguage
from .i18n import Catalogue
from .protocol import DEAF_SECONDS, DEFAULT_URL, WAIT_SECONDS, Envelope

STORE = Path.home() / ".agentschat"
CATALOGUE = Catalogue("sessionchat", "client_messages")
ROOM_LANGUAGE = RoomLanguage()
FAILURE = 1
REFUSED = 5
JSON_HELP = "отчёт кодом, без предложений"


def base() -> str:
    return (os.environ.get("AGENTSCHAT_URL") or DEFAULT_URL).rstrip("/")


def credentials(agent: str) -> dict:
    path = STORE / f"{agent}.json"
    if not path.is_file():
        fail(
            f"сессия {agent} не подключена к чату. Сначала выполните: "
            f"agentschat login --agent {agent}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def speak(key: str, **params: object) -> str:
    return CATALOGUE.text(ROOM_LANGUAGE.current(STORE), key, **params)


def learn_language(answer: object) -> None:
    if isinstance(answer, dict):
        ROOM_LANGUAGE.learn(STORE, answer.get("language"))


def fail(message: str) -> None:
    print(speak("failure_line", message=message), file=sys.stderr)
    raise SystemExit(FAILURE)


def explain(response: requests.Response) -> str:
    try:
        message = response.json().get("message")
    except (ValueError, AttributeError):
        message = None
    if isinstance(message, str) and message.strip():
        return message.strip()
    return response.text.strip() or f"HTTP {response.status_code}"


def stored_token(agent: str) -> str:
    """Токен прежней регистрации, если он ещё лежит на диске."""
    path = STORE / f"{agent}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("token", "")
    except (OSError, ValueError):
        return ""


def do_login(args: argparse.Namespace) -> None:
    payload = {"agent": args.agent, "label": args.label}
    if args.reconnect:
        # Возврат к своей же регистрации после перезапуска CLI: право на неё
        # подтверждает токен с диска, а не слова сессии о себе.
        payload["reconnect"] = True
        payload["token"] = stored_token(args.agent)
    try:
        response = requests.post(
            f"{base()}/login",
            json=payload,
            timeout=15,
        )
    except requests.RequestException as error:
        fail(f"брокер недоступен на {base()}: {error}")
    if response.status_code != 200:
        fail(explain(response))
    data = response.json()
    learn_language(data)
    if data.get("reconnected"):
        # Фразу «подключена к комнате» ниже читает плагин OpenCode, поэтому
        # она должна остаться и здесь: по ней он привязывает сессию.
        print(
            f"AGENTSCHAT: это твоя прежняя регистрация, токен сверился — "
            f"сессия {args.agent} подключена к комнате {data['room']}.\n"
            "Новой регистрации не заводилось, слот остался за тобой."
        )
    STORE.mkdir(parents=True, exist_ok=True)
    path = STORE / f"{args.agent}.json"
    path.write_text(
        json.dumps({"agent": args.agent, "token": data["token"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    if data.get("reconnected"):
        if data.get("mode") == "listener":
            print(
                "Listener прежнего запуска умер вместе с процессом — подними "
                f"его заново ФОНОВОЙ командой: agentschat wait --agent "
                f"{args.agent}"
            )
        return
    if data.get("mode") == "plugin":
        print(
            f"AGENTSCHAT: сессия {args.agent} подключена к комнате {data['room']}.\n"
            "Связь держит плагин Quoroom внутри самого OpenCode: он уже "
            "опрашивает брокера и вложит входящее сообщение прямо в эту сессию.\n"
            "Listener запускать НЕ надо — его роль исполняет плагин."
        )
        return
    if data.get("mode") == "push":
        print(
            f"AGENTSCHAT: сессия {args.agent} подключена к комнате {data['room']}.\n"
            "Доставку берёт на себя брокер: входящие сообщения будут приходить "
            "тебе как обычные запросы, помеченные конвертом AGENTSCHAT.\n"
            "Listener запускать НЕ надо — он тебе не нужен и работать не будет."
        )
        return
    print(
        f"AGENTSCHAT: сессия {args.agent} подключена к комнате {data['room']}.\n"
        "Теперь запусти listener ФОНОВОЙ командой и не жди её завершения:\n"
        f"    agentschat wait --agent {args.agent}\n"
        "Когда listener завершится, ты будешь разбужен его выводом. Первым "
        "действием после пробуждения подними listener заново."
    )


def do_logout(args: argparse.Namespace) -> None:
    payload = {"agent": args.agent, "force": bool(args.force)}
    if not args.force:
        payload["token"] = credentials(args.agent)["token"]
    try:
        response = requests.post(f"{base()}/logout", json=payload, timeout=15)
    except requests.RequestException as error:
        fail(f"брокер недоступен: {error}")
    if response.status_code != 200:
        fail(explain(response))
    if not args.force:
        # Свои учётные данные убираем за собой. Чужие — нет: --force выселяет
        # сессию, которая может быть ещё жива, и удалённый файл лишил бы её
        # даже возможности понять, что произошло. Токен и так уже недействителен:
        # брокер ответит ей 409, и она это увидит.
        (STORE / f"{args.agent}.json").unlink(missing_ok=True)
    print(f"AGENTSCHAT: сессия {args.agent} отключена.")


def poll_once(agent: str, token: str) -> str | None:
    """Один long-poll. None означает, что за окно ничего не пришло.

    Возвращает готовый текст конверта. Его собирает брокер: он один знает,
    какой у сессии режим доставки, а значит и надо ли требовать поднять
    listener заново.
    """
    response = requests.get(
        f"{base()}/wait",
        params={"agent": agent, "token": token},
        timeout=WAIT_SECONDS + 10,
    )
    if response.status_code == 204:
        return None
    if response.status_code == 200:
        data = response.json()
        learn_language(data)
        return str(data.get("rendered") or Envelope.from_dict(data).render())
    raise RuntimeError(explain(response))


def do_wait(args: argparse.Namespace) -> None:
    token = credentials(args.agent)["token"]
    deaf_since = 0.0
    while True:
        try:
            rendered = poll_once(args.agent, token)
        except requests.RequestException as error:
            # Процесс жив, но связи нет. Ждём восстановления, а по истечении
            # запаса выходим: смерть listener будит сессию и чинит связь.
            now = time.time()
            deaf_since = deaf_since or now
            if now - deaf_since >= DEAF_SECONDS:
                print(
                    "=== AGENTSCHAT: связь с брокером потеряна ===\n"
                    f"Брокер {base()} недоступен уже "
                    f"{int(now - deaf_since)}с: {error}\n"
                    "Listener завершился, чтобы не изображать работу вслепую.\n"
                    "Проверь, запущен ли брокер, и подними listener заново."
                )
                raise SystemExit(1) from None
            time.sleep(3)
            continue
        except RuntimeError as error:
            print(f"=== AGENTSCHAT: listener остановлен ===\n{error}")
            raise SystemExit(1) from None
        deaf_since = 0.0
        if rendered is not None:
            print(rendered)
            return


def show_pending(pending: list) -> None:
    """Печатает очередь, накопленную для агента без непрошеной доставки."""
    if not pending:
        return
    print(f"\nAGENTSCHAT: пока тебя не было, пришло сообщений: {len(pending)}.")
    for item in pending:
        print()
        print(item)


def do_inbox(args: argparse.Namespace) -> None:
    token = credentials(args.agent)["token"]
    try:
        response = requests.get(
            f"{base()}/inbox",
            params={"agent": args.agent, "token": token},
            timeout=30,
        )
    except requests.RequestException as error:
        fail(f"брокер недоступен: {error}")
    if response.status_code != 200:
        fail(explain(response))
    answer = response.json()
    learn_language(answer)
    pending = answer.get("pending") or []
    if not pending:
        print("AGENTSCHAT: новых сообщений нет.")
        return
    show_pending(pending)


def message_text(args: argparse.Namespace) -> str:
    """Текст сообщения: из аргумента, из файла или со стандартного ввода.

    Многострочный текст НЕЛЬЗЯ передавать аргументом командной строки: под
    Windows вызов идёт через cmd.exe, а тот обрывает командную строку на первом
    переводе строки. На живом прогоне так пропали четыре абзаца из пяти, и обе
    стороны ждали друг друга. Поэтому всё длиннее одной строки — файлом.
    """
    if args.file:
        # utf-8-sig, а не utf-8: редакторы под Windows ставят BOM, и он
        # уезжает в комнату видимым мусором в начале сообщения.
        return Path(args.file).read_text(encoding="utf-8-sig").strip()
    text = args.text or ""
    if text == "-":
        return sys.stdin.read().strip()
    if not text:
        fail("нечего отправлять: укажите текст, --file или - для стандартного ввода")
    return text


def do_say(args: argparse.Namespace) -> None:
    args.text = message_text(args)
    token = credentials(args.agent)["token"]
    try:
        response = requests.post(
            f"{base()}/say",
            json={"agent": args.agent, "token": token, "text": args.text},
            timeout=30,
        )
    except requests.RequestException as error:
        fail(f"брокер недоступен: {error}")
    if response.status_code != 200:
        fail(explain(response))
    data = response.json()
    learn_language(data)
    print(f"AGENTSCHAT: отправлено ({data['event_id']}).")
    if data.get("warning"):
        print(f"AGENTSCHAT: ВНИМАНИЕ — {data['warning']}")
    if data.get("note"):
        print(f"AGENTSCHAT: {data['note']}")


def do_ask(args: argparse.Namespace) -> None:
    do_say(args)
    token = credentials(args.agent)["token"]
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        try:
            rendered = poll_once(args.agent, token)
        except (requests.RequestException, RuntimeError) as error:
            fail(f"ожидание ответа прервано: {error}")
        if rendered is not None:
            print(rendered)
            return
    print(
        f"AGENTSCHAT: за {args.timeout}с ответа не пришло. Сообщение доставлено; "
        "не жди дальше в этом ходе — ответ придёт через listener."
    )


def status_text(response: requests.Response) -> str:
    if "application/json" not in response.headers.get("Content-Type", ""):
        return response.text
    answer = response.json()
    learn_language(answer)
    sessions = answer.get("sessions") if isinstance(answer, dict) else None
    return "\n".join(
        str(session.get("line", ""))
        for session in sessions or []
        if isinstance(session, dict)
    )


def do_status(args: argparse.Namespace) -> None:
    try:
        response = requests.get(f"{base()}/status", timeout=15)
    except requests.RequestException as error:
        fail(f"брокер недоступен на {base()}: {error}")
    print(status_text(response).rstrip())


def do_install(args: argparse.Namespace) -> None:
    clis = kit.chosen_clis(args.claude, args.opencode)
    roots = kit.target_roots(clis, args.claude_dir, args.opencode_dir)
    try:
        steps = kit.install(STORE / "kit.json", roots, force=args.force)
    except kit.KitConflict as refusal:
        refuse(args, kit.COMMAND_INSTALL, refusal)
    reported(args, kit.COMMAND_INSTALL, steps, kit.install_summary(steps))


def do_uninstall(args: argparse.Namespace) -> None:
    clis = kit.chosen_clis(args.claude, args.opencode)
    steps = kit.uninstall(STORE / "kit.json", kit.DEFAULT_ROOTS, clis, args.force)
    reported(args, kit.COMMAND_UNINSTALL, steps, kit.uninstall_summary(steps))


def refuse(args: argparse.Namespace, command: str, conflict: kit.KitConflict) -> None:
    if not args.json:
        fail(str(conflict))
    print(kit.Report(command, kit.CODE_CONFLICT, tuple(conflict.steps)).as_json())
    raise SystemExit(REFUSED)


def reported(
    args: argparse.Namespace, command: str, steps: list[kit.Step], summary: str
) -> None:
    if args.json:
        print(kit.Report(command, kit.CODE_NONE, tuple(steps)).as_json())
        return
    for step in steps:
        print(step.line())
    print(summary)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agentschat", description="Quoroom session client"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="подключить эту сессию к чату")
    login.add_argument("--agent", required=True)
    login.add_argument("--label", default="", help="чем занята сессия")
    login.add_argument(
        "--reconnect",
        action="store_true",
        help=(
            "вернуться к своей же регистрации после перезапуска CLI; "
            "получится, только если совпадёт токен с диска"
        ),
    )
    login.set_defaults(run=do_login)

    wait = sub.add_parser("wait", help="listener: ждать сообщение и выйти")
    wait.add_argument("--agent", required=True)
    wait.set_defaults(run=do_wait)

    say = sub.add_parser("say", help="отправить сообщение в чат")
    say.add_argument("--agent", required=True)
    say.add_argument("text", nargs="?", help="текст; - читать со stdin")
    say.add_argument("--file", help="взять текст из файла (для многострочного)")
    say.set_defaults(run=do_say)

    ask = sub.add_parser("ask", help="отправить и подождать ответ")
    ask.add_argument("--agent", required=True)
    ask.add_argument("--timeout", type=float, default=300.0)
    ask.add_argument("text", nargs="?", help="текст; - читать со stdin")
    ask.add_argument("--file", help="взять текст из файла (для многострочного)")
    ask.set_defaults(run=do_ask)

    inbox = sub.add_parser("inbox", help="забрать накопленные сообщения")
    inbox.add_argument("--agent", required=True)
    inbox.set_defaults(run=do_inbox)

    status = sub.add_parser("status", help="кто подключён и кто слушает")
    status.set_defaults(run=do_status)

    logout = sub.add_parser("logout", help="отключить сессию")
    logout.add_argument("--agent", required=True)
    logout.add_argument("--force", action="store_true", help="освободить чужой слот")
    logout.set_defaults(run=do_logout)

    install = sub.add_parser(
        "install", help="разложить набор Quoroom в каталоги Claude Code и OpenCode"
    )
    install.add_argument("--claude", action="store_true", help="только Claude Code")
    install.add_argument("--opencode", action="store_true", help="только OpenCode")
    install.add_argument("--claude-dir", help=f"вместо {kit.DEFAULT_ROOTS['claude']}")
    install.add_argument(
        "--opencode-dir", help=f"вместо {kit.DEFAULT_ROOTS['opencode']}"
    )
    install.add_argument(
        "--force", action="store_true", help="перезаписать чужие файлы"
    )
    install.add_argument("--json", action="store_true", help=JSON_HELP)
    install.set_defaults(run=do_install)

    uninstall = sub.add_parser("uninstall", help="убрать установленный набор Quoroom")
    uninstall.add_argument("--claude", action="store_true", help="только Claude Code")
    uninstall.add_argument("--opencode", action="store_true", help="только OpenCode")
    uninstall.add_argument(
        "--force", action="store_true", help="удалить и изменённые вручную файлы"
    )
    uninstall.add_argument("--json", action="store_true", help=JSON_HELP)
    uninstall.set_defaults(run=do_uninstall)

    args = parser.parse_args()
    ROOM_LANGUAGE.insist(getattr(args, "lang", None))
    args.run(args)


if __name__ == "__main__":
    main()
