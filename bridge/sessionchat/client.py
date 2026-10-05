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
from . import client_result
from .client_language import RoomLanguage
from .i18n import Catalogue
from .protocol import DEAF_SECONDS, DEFAULT_URL, WAIT_SECONDS

STORE = Path.home() / ".agentschat"
CATALOGUE = Catalogue("sessionchat", "client_messages")
ROOM_LANGUAGE = RoomLanguage()
FAILURE = 1
REFUSED = 5
JSON_HELP = "отчёт кодом, без предложений"
ENVELOPE_WITHOUT_TEXT = "envelope_without_text"
BROKER_UNREACHABLE = "broker_unreachable"
BROKER_REFUSED = "broker_refused"
NOT_LOGGED_IN = "not_logged_in"
UNEXPECTED_ANSWER = "unexpected_answer"


class ContractError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def base() -> str:
    return (os.environ.get("AGENTSCHAT_URL") or DEFAULT_URL).rstrip("/")


def saved_credentials(agent: str) -> dict | None:
    path = STORE / f"{agent}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def not_logged_in_message(agent: str) -> str:
    return " ".join(
        (
            speak("not_logged_in", agent=agent),
            speak("not_logged_in_login", agent=agent),
        )
    )


def credentials(agent: str) -> dict:
    saved = saved_credentials(agent)
    if saved is None:
        fail(not_logged_in_message(agent))
    return saved


def speak(key: str, **params: object) -> str:
    return CATALOGUE.text(ROOM_LANGUAGE.current(STORE), key, **params)


def learn_language(answer: object) -> None:
    if isinstance(answer, dict):
        ROOM_LANGUAGE.learn(STORE, answer.get("language"))


def fail(message: str) -> None:
    print(speak("failure_line", message=message), file=sys.stderr)
    raise SystemExit(FAILURE)


def report(command: str, ok: bool, **fields: object) -> None:
    print(client_result.line(command, ok, **fields), flush=True)


def fail_with_result(command: str, code: str, message: str, **fields: object) -> None:
    try:
        fail(message)
    finally:
        report(command, False, **fields, code=code)


def refusal_code(response: requests.Response, default: str = BROKER_REFUSED) -> str:
    try:
        code = response.json().get("code")
    except (ValueError, AttributeError):
        return default
    return code if isinstance(code, str) and code else default


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
        fail_with_result(
            "login",
            BROKER_UNREACHABLE,
            speak("login_broker_unreachable", url=base(), error=error),
            agent=args.agent,
        )
    if response.status_code != 200:
        fail_with_result(
            "login", refusal_code(response), explain(response), agent=args.agent
        )
    data = response.json()
    learn_language(data)
    STORE.mkdir(parents=True, exist_ok=True)
    path = STORE / f"{args.agent}.json"
    path.write_text(
        json.dumps({"agent": args.agent, "token": data["token"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    print("\n".join(login_sentences(args.agent, data)))
    report(
        "login",
        True,
        agent=args.agent,
        mode=data.get("mode"),
        reconnected=bool(data.get("reconnected")),
    )


def login_sentences(agent: str, data: dict) -> list[str]:
    room = data["room"]
    if data.get("reconnected"):
        lines = [
            speak("login_reconnected", agent=agent, room=room),
            speak("login_reconnected_slot_kept"),
        ]
        if data.get("mode") == "listener":
            lines.append(speak("login_reconnected_listener", agent=agent))
        return lines
    connected = speak("login_connected", agent=agent, room=room)
    if data.get("mode") == "plugin":
        return [
            connected,
            speak("login_plugin_holds"),
            speak("login_plugin_no_listener"),
        ]
    if data.get("mode") == "push":
        return [
            connected,
            speak("login_push_delivery"),
            speak("login_push_no_listener"),
        ]
    return [
        connected,
        speak("login_listener_start"),
        f"    agentschat wait --agent {agent}",
        " ".join((speak("login_listener_woken"), speak("login_listener_restart"))),
    ]


def do_logout(args: argparse.Namespace) -> None:
    payload = {"agent": args.agent, "force": bool(args.force)}
    if not args.force:
        saved = saved_credentials(args.agent)
        if saved is None:
            fail_with_result(
                "logout",
                NOT_LOGGED_IN,
                not_logged_in_message(args.agent),
                agent=args.agent,
            )
        payload["token"] = saved["token"]
    try:
        response = requests.post(f"{base()}/logout", json=payload, timeout=15)
    except requests.RequestException as error:
        fail_with_result(
            "logout",
            BROKER_UNREACHABLE,
            speak("logout_broker_unreachable", error=error),
            agent=args.agent,
        )
    if response.status_code != 200:
        fail_with_result(
            "logout", refusal_code(response), explain(response), agent=args.agent
        )
    if not args.force:
        # Свои учётные данные убираем за собой. Чужие — нет: --force выселяет
        # сессию, которая может быть ещё жива, и удалённый файл лишил бы её
        # даже возможности понять, что произошло. Токен и так уже недействителен:
        # брокер ответит ей 409, и она это увидит.
        (STORE / f"{args.agent}.json").unlink(missing_ok=True)
    print(speak("logout_done", agent=args.agent))
    report("logout", True, agent=args.agent)


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
        rendered = data.get("rendered") if isinstance(data, dict) else None
        if not isinstance(rendered, str) or not rendered:
            raise ContractError(
                ENVELOPE_WITHOUT_TEXT,
                speak("envelope_without_text", code=ENVELOPE_WITHOUT_TEXT),
            )
        return rendered
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


def status_answer(response: requests.Response) -> dict | None:
    if "application/json" not in response.headers.get("Content-Type", ""):
        return None
    answer = response.json()
    learn_language(answer)
    return answer if isinstance(answer, dict) else {}


def status_sessions(answer: dict | None) -> list[dict] | None:
    sessions = (answer or {}).get("sessions")
    if not isinstance(sessions, list):
        return None
    return [session for session in sessions if isinstance(session, dict)]


def unreadable_status(response: requests.Response, answer: dict | None) -> str:
    if answer is None:
        return response.text.rstrip()
    message = answer.get("message")
    return message.strip() if isinstance(message, str) else ""


def do_status(args: argparse.Namespace) -> None:
    try:
        response = requests.get(f"{base()}/status", timeout=15)
    except requests.RequestException as error:
        fail_with_result(
            "status",
            BROKER_UNREACHABLE,
            speak("status_broker_unreachable", url=base(), error=error),
        )
    answer = status_answer(response)
    sessions = status_sessions(answer)
    if sessions is None:
        print(unreadable_status(response, answer))
        report("status", False, code=refusal_code(response, UNEXPECTED_ANSWER))
        return
    print("\n".join(str(session.get("line", "")) for session in sessions).rstrip())
    report(
        "status",
        True,
        language=answer.get("language"),
        sessions=[
            {key: value for key, value in session.items() if key != "line"}
            for session in sessions
        ],
    )


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

    login = sub.add_parser("login", help=speak("login_help"))
    login.add_argument("--agent", required=True)
    login.add_argument("--label", default="", help=speak("login_label_help"))
    login.add_argument(
        "--reconnect", action="store_true", help=speak("login_reconnect_help")
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

    status = sub.add_parser("status", help=speak("status_help"))
    status.set_defaults(run=do_status)

    logout = sub.add_parser("logout", help=speak("logout_help"))
    logout.add_argument("--agent", required=True)
    logout.add_argument("--force", action="store_true", help=speak("logout_force_help"))
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
