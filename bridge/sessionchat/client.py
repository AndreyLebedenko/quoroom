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
    agentschat install   [--claude] [--opencode] [--force] [--json] [--lang en|ru]
    agentschat uninstall [--claude] [--opencode] [--force] [--json] [--lang en|ru]
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
from .i18n import LANGUAGES, Catalogue
from .protocol import DEAF_SECONDS, DEFAULT_URL, WAIT_SECONDS

STORE = Path.home() / ".agentschat"
CATALOGUE = Catalogue("sessionchat", "client_messages")
ROOM_LANGUAGE = RoomLanguage()
FAILURE = 1
REFUSED = 5
LANGUAGE_FLAG = "--lang"
ENVELOPE_WITHOUT_TEXT = "envelope_without_text"
BROKER_UNREACHABLE = "broker_unreachable"
BROKER_REFUSED = "broker_refused"
NOT_LOGGED_IN = "not_logged_in"
UNEXPECTED_ANSWER = "unexpected_answer"
NOTHING_TO_SEND = "nothing_to_send"
FRAME = "=== AGENTSCHAT: {title} ==="


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


def credentials(agent: str, command: str | None = None) -> dict:
    saved = saved_credentials(agent)
    if saved is not None:
        return saved
    message = not_logged_in_message(agent)
    if command is None:
        fail(message)
    fail_with_result(command, NOT_LOGGED_IN, message, agent=agent)


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
    raise ContractError(refusal_code(response), explain(response))


def frame(title_key: str) -> str:
    return FRAME.format(title=speak(title_key))


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
                    "\n".join(
                        (
                            frame("wait_broker_lost_title"),
                            speak(
                                "wait_broker_lost_unreachable",
                                url=base(),
                                seconds=int(now - deaf_since),
                                error=error,
                            ),
                            speak("wait_broker_lost_exited"),
                            speak("wait_broker_lost_restart"),
                        )
                    )
                )
                raise SystemExit(1) from None
            time.sleep(3)
            continue
        except RuntimeError as error:
            print(frame("wait_listener_stopped_title"))
            print(error)
            raise SystemExit(1) from None
        deaf_since = 0.0
        if rendered is not None:
            print(rendered)
            return


def show_pending(pending: list) -> None:
    """Печатает очередь, накопленную для агента без непрошеной доставки."""
    if not pending:
        return
    print()
    print(speak("inbox_pending", count=len(pending)))
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
        fail(speak("inbox_broker_unreachable", error=error))
    if response.status_code != 200:
        fail(explain(response))
    answer = response.json()
    learn_language(answer)
    pending = answer.get("pending") or []
    if not pending:
        print(speak("inbox_empty"))
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
        fail(speak("usage_nothing_to_send"))
    return text


def outgoing_text(command: str, args: argparse.Namespace) -> str:
    try:
        return message_text(args)
    except SystemExit:
        report(command, False, agent=args.agent, code=NOTHING_TO_SEND)
        raise


def deliver(command: str, args: argparse.Namespace) -> dict:
    text = outgoing_text(command, args)
    token = credentials(args.agent, command)["token"]
    try:
        response = requests.post(
            f"{base()}/say",
            json={"agent": args.agent, "token": token, "text": text},
            timeout=30,
        )
    except requests.RequestException as error:
        fail_with_result(
            command,
            BROKER_UNREACHABLE,
            speak("say_broker_unreachable", error=error),
            agent=args.agent,
        )
    if response.status_code != 200:
        fail_with_result(
            command, refusal_code(response), explain(response), agent=args.agent
        )
    data = response.json()
    learn_language(data)
    print(speak("say_sent", event_id=data["event_id"]))
    if data.get("warning"):
        print(speak("say_warning", warning=data["warning"]))
    if data.get("note"):
        print(speak("say_note", note=data["note"]))
    return data


def delivered_fields(data: dict) -> dict:
    fields = {"event_id": data["event_id"]}
    if data.get("warning_code"):
        fields["warning"] = data["warning_code"]
    if data.get("note_code"):
        fields["note"] = data["note_code"]
    return fields


def wait_failure_code(error: Exception) -> str:
    if isinstance(error, ContractError):
        return error.code
    if isinstance(error, requests.RequestException):
        return BROKER_UNREACHABLE
    return BROKER_REFUSED


def do_say(args: argparse.Namespace) -> None:
    data = deliver("say", args)
    report("say", True, agent=args.agent, **delivered_fields(data))


def do_ask(args: argparse.Namespace) -> None:
    fields = {"agent": args.agent, **delivered_fields(deliver("ask", args))}
    token = credentials(args.agent, "ask")["token"]
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        try:
            rendered = poll_once(args.agent, token)
        except (requests.RequestException, RuntimeError) as error:
            fail_with_result(
                "ask",
                wait_failure_code(error),
                speak("ask_interrupted", error=error),
                **fields,
            )
        if rendered is not None:
            print(rendered)
            report("ask", True, **fields, answered=True)
            return
    print(
        " ".join(
            (
                speak("ask_timeout", timeout=args.timeout),
                speak("ask_timeout_delivered"),
            )
        )
    )
    report("ask", True, **fields, answered=False)


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
    lang = ROOM_LANGUAGE.current(STORE)
    clis = kit.chosen_clis(args.claude, args.opencode)
    roots = kit.target_roots(clis, args.claude_dir, args.opencode_dir)
    try:
        steps = kit.install(STORE / "kit.json", roots, force=args.force, lang=lang)
    except kit.KitConflict as refusal:
        refuse(args, refusal)
    reported(args, kit.COMMAND_INSTALL, steps, lang, kit.install_summary(steps, lang))


def do_uninstall(args: argparse.Namespace) -> None:
    lang = ROOM_LANGUAGE.current(STORE)
    clis = kit.chosen_clis(args.claude, args.opencode)
    steps = kit.uninstall(STORE / "kit.json", kit.DEFAULT_ROOTS, clis, args.force)
    reported(
        args, kit.COMMAND_UNINSTALL, steps, lang, kit.uninstall_summary(steps, lang)
    )


def refuse(args: argparse.Namespace, conflict: kit.KitConflict) -> None:
    if not args.json:
        fail(str(conflict))
    print(
        kit.Report(
            kit.COMMAND_INSTALL, kit.CODE_CONFLICT, tuple(conflict.steps)
        ).as_json()
    )
    raise SystemExit(REFUSED)


def reported(
    args: argparse.Namespace,
    command: str,
    steps: list[kit.Step],
    lang: str,
    summary: str,
) -> None:
    if args.json:
        print(kit.Report(command, kit.CODE_NONE, tuple(steps)).as_json())
        return
    for step in steps:
        print(step.line(lang))
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

    wait = sub.add_parser("wait", help=speak("wait_help"))
    wait.add_argument("--agent", required=True)
    wait.set_defaults(run=do_wait)

    say = sub.add_parser("say", help=speak("say_help"))
    say.add_argument("--agent", required=True)
    say.add_argument("text", nargs="?", help=speak("say_text_help"))
    say.add_argument("--file", help=speak("say_file_help"))
    say.set_defaults(run=do_say)

    ask = sub.add_parser("ask", help=speak("ask_help"))
    ask.add_argument("--agent", required=True)
    ask.add_argument("--timeout", type=float, default=300.0)
    ask.add_argument("text", nargs="?", help=speak("say_text_help"))
    ask.add_argument("--file", help=speak("say_file_help"))
    ask.set_defaults(run=do_ask)

    inbox = sub.add_parser("inbox", help=speak("inbox_help"))
    inbox.add_argument("--agent", required=True)
    inbox.set_defaults(run=do_inbox)

    status = sub.add_parser("status", help=speak("status_help"))
    status.set_defaults(run=do_status)

    logout = sub.add_parser("logout", help=speak("logout_help"))
    logout.add_argument("--agent", required=True)
    logout.add_argument("--force", action="store_true", help=speak("logout_force_help"))
    logout.set_defaults(run=do_logout)

    install = sub.add_parser("install", help=speak("kit.help_install"))
    install.add_argument(
        "--claude", action="store_true", help=speak("kit.help_claude_only")
    )
    install.add_argument(
        "--opencode", action="store_true", help=speak("kit.help_opencode_only")
    )
    install.add_argument(
        "--claude-dir",
        help=speak("kit.help_dir", default=kit.DEFAULT_ROOTS["claude"]),
    )
    install.add_argument(
        "--opencode-dir",
        help=speak("kit.help_dir", default=kit.DEFAULT_ROOTS["opencode"]),
    )
    install.add_argument(
        "--force", action="store_true", help=speak("kit.help_force_install")
    )
    install.add_argument("--json", action="store_true", help=speak("kit.help_json"))
    add_language(install)
    install.set_defaults(run=do_install)

    uninstall = sub.add_parser("uninstall", help=speak("kit.help_uninstall"))
    uninstall.add_argument(
        "--claude", action="store_true", help=speak("kit.help_claude_only")
    )
    uninstall.add_argument(
        "--opencode", action="store_true", help=speak("kit.help_opencode_only")
    )
    uninstall.add_argument(
        "--force", action="store_true", help=speak("kit.help_force_uninstall")
    )
    uninstall.add_argument("--json", action="store_true", help=speak("kit.help_json"))
    add_language(uninstall)
    uninstall.set_defaults(run=do_uninstall)

    args = parser.parse_args()
    ROOM_LANGUAGE.insist(getattr(args, "lang", None))
    args.run(args)


def add_language(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        LANGUAGE_FLAG,
        choices=LANGUAGES,
        default=None,
        help=speak("kit.help_lang"),
    )


if __name__ == "__main__":
    main()
