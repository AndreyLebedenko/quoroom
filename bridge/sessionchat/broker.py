#!/usr/bin/env python3
"""Брокер чата сессий.

Одна комната Matrix, аккаунты агентов и человек как равноправные
участники. К брокеру по HTTP на 127.0.0.1 подключаются ЖИВЫЕ сессии CLI —
брокер сам никаких CLI не запускает.

Сессия не владеет Matrix-токеном: она говорит только с брокером, а публикует
брокер от имени соответствующего аккаунта. Поэтому сессия не может выйти из
комнаты, написать в личку или притвориться другим агентом.

Запуск:

    python -m sessionchat.broker --config config.yaml

Обоснование решений — docs/SESSION_BRIDGE.md.
"""

import argparse
import asyncio
import logging
import re
import secrets
import ssl
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import yaml
from aiohttp import web
from nio import (
    AsyncClient,
    AsyncClientConfig,
    JoinResponse,
    MatrixRoom,
    RoomMessageText,
    RoomSendResponse,
)

from .protocol import (
    DEFAULT_PORT,
    LISTEN_GRACE,
    MAX_DEPTH,
    MAX_SENDS_PER_MINUTE,
    STALE_SECONDS,
    WAIT_SECONDS,
    Envelope,
)

log = logging.getLogger("agentschat.broker")


def bounded(needle: str, haystack: str) -> bool:
    """Вхождение с границами слова.

    Простое вхождение подстроки адресовало бы агента по имени terra
    сообщением про terra-2, а Claude Code — любым упоминанием claude-code-2.
    Дефис считаем частью имени, иначе граница не работает на localpart.
    """
    if not needle:
        return False
    pattern = r"(?<![\w-])" + re.escape(needle.lower()) + r"(?![\w-])"
    return re.search(pattern, haystack) is not None


@dataclass
class Session:
    """Подключённая живая сессия. Одна на агента: повторный вход — отказ."""

    agent: str
    label: str
    token: str
    since: float
    inbox: deque = field(default_factory=deque)
    sends: deque = field(default_factory=deque)
    open_waits: int = 0
    listening_until: float = 0.0
    last_delivery: float = 0.0
    # Когда пришёл запрос с токеном этой регистрации. Об обмене сообщениями
    # не говорит ничего: пустой /wait, вернувший 204, обновляет отметку так
    # же, как доставка. О живости не говорит ничего: файл с токеном переживает
    # смерть процесса, и предъявить его может осиротевший listener. Это факт о
    # прошлом; живость считает state(), опираясь на open_waits и
    # listening_until.
    last_contact: float = 0.0
    # Глубина последнего доставленного сообщения: исходящие получают +1.
    depth: int = 0
    signal: asyncio.Event = field(default_factory=asyncio.Event)
    # "listener" | "plugin"
    listener_kind: str = "listener"
    # Предел глубины цепочки, действующий для этой сессии. Хранится здесь,
    # чтобы конверт печатал настоящее "из N", а не значение по умолчанию.
    max_depth: int = MAX_DEPTH

    @property
    def mode(self) -> str:
        return self.listener_kind

    @property
    def restart_listener(self) -> bool:
        """Требовать ли от агента поднять listener заново после пробуждения.

        Требование имеет смысл только там, где listener — отдельный процесс,
        умирающий при доставке. Плагину поднимать нечего, а невыполнимое
        указание в конверте только сбивает.
        """
        return self.mode == "listener"

    def drain(self) -> list[str]:
        """Отдаёт всё накопленное разом и очищает очередь."""
        taken = list(self.inbox)
        self.inbox.clear()
        if taken:
            self.last_delivery = time.time()
            self.depth = taken[-1].depth
        return [
            envelope.render(self.restart_listener, self.max_depth) for envelope in taken
        ]

    def state(self) -> str:
        now = time.time()
        if self.open_waits > 0 or now < self.listening_until:
            return "слушает"
        if self.last_delivery and now - self.last_delivery < 120:
            return "обрабатывает"
        return "НЕ СЛУШАЕТ"

    def stale(self) -> bool:
        """Можно ли считать сессию исчезнувшей и отдать её слот новому входу.

        Перехват живой сессии запрещён и остаётся запрещённым: он оставил бы
        её с мёртвым listener'ом, который больше ничего не получит. Но сессия,
        которая не обращалась к брокеру три минуты, не жива — и listener,
        и плагин опрашивают его непрерывно, а пауза на обработку доставки
        укладывается в две минуты. Столько молчит только закрытое приложение,
        убитый процесс или перезагруженная машина.
        """
        now = time.time()
        if self.open_waits > 0 or now < self.listening_until:
            return False
        last = max(self.since, self.last_delivery, self.last_contact)
        return now - last > STALE_SECONDS

    def advice(self) -> str:
        """Что делать тому, кому отказано во входе на этот слот.

        Отказ без срока провоцирует перехват: сессия видит «занято», не знает,
        надолго ли, и тянется к --force. А занимать слот может её собственный
        труп — регистрация от процесса, убитого минуту назад.
        """
        now = time.time()
        last = max(self.since, self.last_delivery, self.last_contact)
        quiet = int(now - last)
        # Освободится, когда кончится и фора слушателя, и счёт молчания.
        left = int(max(self.listening_until, last + STALE_SECONDS) - now)
        if left <= 0:
            return "Та сессия молчит дольше предела; повтори вход — слот твой."
        if self.open_waits > 0 or now < self.listening_until:
            # «Она жива» здесь сказать нельзя: убитый процесс оставляет свой
            # запрос висеть, и брокер ещё минуту видит опрос от того, кого уже
            # нет. Известно только, когда был последний опрос.
            return (
                f"Та сессия опрашивала брокера {quiet}с назад. Если она жива, "
                f"слот занят по делу; если её только что убили, он освободится "
                f"сам через {left}с — повтори вход тогда."
            )
        return (
            f"Та сессия молчит {quiet}с. Если её больше нет, слот освободится "
            f"сам через {left}с — повтори вход тогда, перехват не нужен."
        )

    def throttled(self) -> bool:
        now = time.time()
        while self.sends and now - self.sends[0] > 60:
            self.sends.popleft()
        return len(self.sends) >= MAX_SENDS_PER_MINUTE


class Broker:
    def __init__(self, cfg: dict):
        self.room = cfg["room_id"]
        self.port = int(cfg.get("sessionchat_port", DEFAULT_PORT))
        self.max_depth = int(cfg.get("max_depth", MAX_DEPTH))
        verify = cfg.get("verify_ssl", True)
        tls = (
            ssl.create_default_context(cafile=verify)
            if isinstance(verify, str)
            else bool(verify)
        )
        self.clients: dict[str, AsyncClient] = {}
        # Как агент получает непрошеные сообщения, если не через listener:
        # "plugin" — слушатель живёт внутри самого CLI (OpenCode).
        self.delivery_kinds: dict[str, str] = {}
        for agent, data in cfg["agents"].items():
            kind = str(data.get("delivery", "listener"))
            if kind not in ("listener", "plugin"):
                raise ValueError(
                    f"агент {agent}: неизвестный delivery: {kind!r}. "
                    "Допустимые значения: listener, plugin."
                )
            if kind == "plugin":
                self.delivery_kinds[agent] = kind
            client = AsyncClient(
                cfg["homeserver_url"],
                data["user_id"],
                ssl=tls,
                config=AsyncClientConfig(store_sync_tokens=False),
            )
            client.restore_login(
                user_id=data["user_id"],
                device_id=data.get("device_id") or "AGENTSCHAT_BROKER",
                access_token=data["access_token"],
            )
            self.clients[agent] = client
        self.user_ids = {a: c.user_id for a, c in self.clients.items()}
        self.sessions: dict[str, Session] = {}
        self.reader = next(iter(self.clients.values()))
        self.started_ms = int(time.time() * 1000)

    # ---------------------------------------------------------------- Matrix

    async def join_all(self) -> None:
        """Continuwuity требует тело "{}" у POST /join, штатный nio его не шлёт."""
        for agent, client in self.clients.items():
            path = (
                f"/_matrix/client/v3/join/{quote(self.room, safe='')}"
                f"?access_token={quote(client.access_token, safe='')}"
            )
            response = await client._send(JoinResponse, "POST", path, data="{}")
            if not isinstance(response, JoinResponse):
                raise RuntimeError(
                    f"{agent}: не удалось войти в {self.room}: {response}"
                )
            self.room = response.room_id

    def addressees(self, body: str, event) -> list[str]:
        """Адресация: @localpart, пилюля или @room. Ничего больше.

        Голое display name адресовать не может, и это выяснено дорогой ценой:
        агент по имени OpenCode считал обращением к себе любое упоминание CLI
        в отчёте о работе, а GLM — любое обсуждение моделей. Разговор о самих
        инструментах у нас идёт постоянно, и каждое ложное срабатывание стоит
        собеседнику полного хода.

        Страховка, ради которой матч по имени и стоял, оказалась не нужна:
        пилюля Element в plain-text теле выглядит как имя профиля без собаки,
        но рядом приходит m.mentions, и его мы разбираем отдельно (проверено
        на живом событии из комнаты).
        """
        low = body.lower()
        try:
            content = (event.source.get("content", {}) or {}) if event else {}
            mentions = content.get("m.mentions", {}) or {}
        except AttributeError:
            mentions = {}
        if "@room" in low or mentions.get("room") is True:
            return list(self.sessions)
        pills = mentions.get("user_ids") or []
        found = []
        for agent, user_id in self.user_ids.items():
            localpart = user_id.split(":", 1)[0]
            if bounded(localpart, low) or user_id in pills:
                found.append(agent)
        return found

    def addressed_to_a_person(self, text: str) -> bool:
        """Есть ли в тексте обращение, которое заведомо не к агенту.

        Отличает «забыл адресовать» от «ответил человеку». Первое — ошибка,
        стоившая живого прогона: сообщение ушло в пустоту, а его ждали.
        Второе — обычный ход разговора, и одинаковое предупреждение на оба
        случая быстро приучает не читать предупреждения вовсе.
        """
        known = {"@room"}
        for agent, user_id in self.user_ids.items():
            known.add(user_id.split(":", 1)[0].lower())
            known.add(f"@{agent.lower()}")
        return any(
            token not in known for token in re.findall(r"@[\w.-]+", text.lower())
        )

    async def on_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        if room.room_id != self.room or event.server_timestamp < self.started_ms:
            return
        content = event.source.get("content", {}) or {}
        origin = content.get("com.agentschat.agent")
        body = event.body or ""
        human = origin is None
        depth = 0 if human else int(content.get("com.agentschat.depth", 0))
        stamp = datetime.fromtimestamp(event.server_timestamp / 1000)
        envelope = Envelope(
            event.sender,
            "человек" if human else "агент",
            body,
            event.event_id,
            stamp.strftime("%Y-%m-%d %H:%M:%S"),
            depth,
        )
        for agent in self.addressees(body, event):
            if agent == origin:
                continue  # сам себе не доставляем
            session = self.sessions.get(agent)
            if session is None:
                if human:
                    await self.publish(
                        agent,
                        f"(сессия {agent} не подключена, сообщение не доставлено. "
                        f"Выполните @chatlogin в нужной сессии {agent}.)",
                        0,
                    )
                continue
            session.inbox.append(envelope)
            session.signal.set()

    async def publish(self, agent: str, text: str, depth: int) -> str:
        response = await self.clients[agent].room_send(
            room_id=self.room,
            message_type="m.room.message",
            content={
                "msgtype": "m.text",
                "body": text,
                "m.mentions": {},
                "com.agentschat.agent": agent,
                "com.agentschat.depth": depth,
            },
        )
        if not isinstance(response, RoomSendResponse):
            raise RuntimeError(f"публикация не удалась: {response}")
        return response.event_id

    async def sync_forever(self) -> None:
        self.reader.add_event_callback(self.on_message, RoomMessageText)
        await self.reader.sync_forever(timeout=30000, full_state=True)

    # ------------------------------------------------------------------ HTTP

    def session_of(self, data: dict) -> Session:
        agent = str(data.get("agent", ""))
        session = self.sessions.get(agent)
        if session is None or session.token != str(data.get("token", "")):
            raise web.HTTPConflict(text="сессия не подключена или токен неверен")
        session.last_contact = time.time()
        return session

    async def handle_login(self, request: web.Request) -> web.Response:
        data = await request.json()
        agent = str(data.get("agent", ""))
        if agent not in self.clients:
            raise web.HTTPNotFound(text=f"неизвестный агент: {agent}")
        existing = self.sessions.get(agent)
        if existing is not None and existing.stale():
            quiet = int(
                time.time()
                - max(existing.since, existing.last_delivery, existing.last_contact)
            )
            log.info(
                "слот %s освобождён: прежняя сессия молчала %sс (%s)",
                agent,
                quiet,
                existing.label,
            )
            self.sessions.pop(agent, None)
            existing = None
        if existing is not None and data.get("reconnect"):
            # Возврат к своей же регистрации после перезапуска CLI. Право на
            # него подтверждает токен, а не рассуждение сессии о себе: файл с
            # токеном переживает смерть процесса, и предъявить его может
            # только тот, кто эту регистрацию и заводил. Ключ обязателен —
            # молчаливое переподключение по совпадению токена увело бы слот
            # при случайном повторном входе из соседнего окна.
            if existing.token != str(data.get("token", "")):
                raise web.HTTPConflict(
                    text=(
                        f"переподключиться к регистрации {agent} нельзя: токен "
                        "не совпадает. Она заведена не этой сессией."
                    )
                )
            existing.label = str(data.get("label", "")) or existing.label
            existing.last_contact = time.time()
            log.info("переподключение к регистрации %s (%s)", agent, existing.label)
            return web.json_response(
                {
                    "token": existing.token,
                    "room": self.room,
                    "mode": existing.mode,
                    "reconnected": True,
                }
            )
        if existing is not None:
            since = datetime.fromtimestamp(existing.since).strftime("%H:%M:%S")
            raise web.HTTPConflict(
                text=(
                    f"агент {agent} уже подключён с {since} "
                    f"({existing.label}, {existing.state()}). "
                    f"{existing.advice()} "
                    "Не решай, что слот занят тобой же: метка и успешный "
                    "inbox этого не доказывают. Доказывает только токен — если "
                    "эта регистрация твоя, из неё же и заведена, повтори вход "
                    "с ключом --reconnect: брокер сверит токен и вернёт тебе "
                    "её. Не сверится — скажи человеку. Освободить немедленно "
                    f"может он: agentschat logout --agent {agent} --force"
                )
            )
        session = Session(
            agent,
            str(data.get("label", "")) or agent,
            secrets.token_hex(16),
            time.time(),
        )
        session.listener_kind = self.delivery_kinds.get(agent, "listener")
        session.max_depth = self.max_depth
        self.sessions[agent] = session
        log.info("подключена сессия %s (%s)", agent, session.label)
        return web.json_response(
            {
                "token": session.token,
                "room": self.room,
                "mode": session.mode,
            }
        )

    async def handle_logout(self, request: web.Request) -> web.Response:
        data = await request.json()
        agent = str(data.get("agent", ""))
        if not data.get("force"):
            self.session_of(data)
        self.sessions.pop(agent, None)
        log.info("отключена сессия %s", agent)
        return web.json_response({"ok": True})

    async def handle_wait(self, request: web.Request) -> web.Response:
        session = self.session_of(dict(request.query))
        session.open_waits += 1
        session.listening_until = time.time() + LISTEN_GRACE
        try:
            if not session.inbox:
                session.signal.clear()
                try:
                    await asyncio.wait_for(session.signal.wait(), WAIT_SECONDS)
                except asyncio.TimeoutError:
                    return web.Response(status=204)
            if not session.inbox:
                # Разбудили, но сообщение уже забрал другой listener на этой же
                # сессии. Так бывает, когда токен из ~/.agentschat/<агент>.json
                # прочитали два процесса. Пустое окно — честный ответ: клиент
                # просто опросит ещё раз. Без этой проверки popleft падал с
                # IndexError, и опоздавший получал 500.
                return web.Response(status=204)
            envelope = session.inbox.popleft()
            session.depth = envelope.depth
            session.last_delivery = time.time()
            return web.json_response(
                {
                    **envelope.as_dict(),
                    "rendered": envelope.render(
                        session.restart_listener, session.max_depth
                    ),
                }
            )
        finally:
            session.open_waits -= 1
            session.listening_until = time.time() + LISTEN_GRACE

    async def handle_inbox(self, request: web.Request) -> web.Response:
        session = self.session_of(dict(request.query))
        return web.json_response({"pending": session.drain()})

    async def handle_say(self, request: web.Request) -> web.Response:
        data = await request.json()
        session = self.session_of(data)
        text = str(data.get("text", "")).strip()
        if not text:
            raise web.HTTPBadRequest(text="пустое сообщение")
        depth = session.depth + 1
        if depth > self.max_depth:
            # Человек, который просто наблюдает, иначе увидит тишину и не
            # поймёт, что цепочка упёрлась в предел: отказ уходит агенту, а в
            # комнате не появляется ничего.
            await self.publish(
                session.agent,
                f"(цепочка достигла предела глубины {self.max_depth} без "
                "участия человека, дальше агенты продолжать не могут. "
                "Напишите что-нибудь в комнату — это обнулит счётчик.)",
                0,
            )
            raise web.HTTPForbidden(
                text=(
                    f"достигнута предельная глубина цепочки ({self.max_depth}) "
                    "без участия человека. Сообщение не отправлено: нужен "
                    "человек. Об этом сказано в комнате, повторять не надо."
                )
            )
        if session.throttled():
            raise web.HTTPTooManyRequests(
                text=f"превышен предел {MAX_SENDS_PER_MINUTE} сообщений в минуту"
            )
        session.sends.append(time.time())
        # Сообщение без обращения попадает в комнату, но не доставляется никому:
        # человек видит его в Element, а агенты — нет. Отправитель при этом
        # уверен, что сказал. На живом прогоне так и вышло: backend объявил
        # протокол в пустоту, а frontend ждал его и не дождался.
        reach = [a for a in self.addressees(text, None) if a != session.agent]
        event_id = await self.publish(session.agent, text, depth)
        answer = {"event_id": event_id, "depth": depth}
        if not reach and self.addressed_to_a_person(text):
            # Обращение есть, просто не к агенту: ответ человеку на его же
            # вопрос — обычное дело, и пугать отправителя тут нечем.
            answer["note"] = (
                "агентам сообщение не доставлено: обращение в нём не к агенту. "
                "Человек видит его в комнате."
            )
        elif not reach:
            others = [a for a in self.sessions if a != session.agent]
            answer["warning"] = (
                "сообщение опубликовано, но НИ ОДИН агент его не получил: в нём "
                "нет обращения. Адресуй явно — @имя или @room. Сейчас "
                + (
                    f"подключены: {', '.join(sorted(others))}."
                    if others
                    else "других подключённых сессий нет."
                )
            )
        return web.json_response(answer)

    async def handle_status(self, request: web.Request) -> web.Response:
        lines = []
        for agent in self.clients:
            session = self.sessions.get(agent)
            if session is None:
                lines.append(f"{agent:<14} не подключён")
                continue
            quiet = int(time.time() - max(session.last_delivery, session.since))
            since = datetime.fromtimestamp(session.since).strftime("%H:%M:%S")
            lines.append(
                f"{session.agent:<14} {session.state():<12} {session.label} "
                f"(подключена {since}, тишина {quiet}с)"
            )
        return web.Response(text="\n".join(lines) + "\n", content_type="text/plain")

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/login", self.handle_login)
        app.router.add_post("/logout", self.handle_logout)
        app.router.add_get("/wait", self.handle_wait)
        app.router.add_get("/inbox", self.handle_inbox)
        app.router.add_post("/say", self.handle_say)
        app.router.add_get("/status", self.handle_status)
        return app


def only_agents(cfg: dict, names: str) -> dict:
    """Оставляет в конфиге лишь перечисленных агентов.

    Нужно для поэтапного ввода: агент, которого нет в конфиге брокера, не
    сможет подключиться и не будет упомянут в /status. Не подключённый агент
    не тратит токены и без этого, но явный список снимает вопрос совсем.
    """
    if not names:
        return cfg
    wanted = [n.strip() for n in names.split(",") if n.strip()]
    unknown = [n for n in wanted if n not in cfg.get("agents", {})]
    if unknown:
        raise ValueError(f"нет таких агентов в конфиге: {', '.join(unknown)}")
    return {**cfg, "agents": {n: cfg["agents"][n] for n in wanted}}


async def run(config: Path, agents: str = "") -> None:
    cfg = only_agents(yaml.safe_load(config.read_text(encoding="utf-8")), agents)
    broker = Broker(cfg)
    runner = None
    try:
        await broker.join_all()
        runner = web.AppRunner(broker.app())
        await runner.setup()
        try:
            await web.TCPSite(runner, "127.0.0.1", broker.port).start()
        except OSError as error:
            # Занятый порт — не редкость, а обычный способ ошибиться: брокер
            # уже работает в другом окне, и второй запуск с другими ключами
            # молча ничего не меняет. Traceback здесь только прячет причину.
            raise SystemExit(
                f"БРОКЕР НЕ ЗАПУЩЕН: порт {broker.port} занят ({error.strerror}).\n"
                "Скорее всего, брокер уже работает в другом окне. Проверьте: "
                f"curl http://127.0.0.1:{broker.port}/status — и остановите "
                "прежний, если хотите запустить этот с другими ключами."
            ) from None
        log.info("БРОКЕР ГОТОВ комната=%s порт=%s", broker.room, broker.port)
        await broker.sync_forever()
    finally:
        if runner is not None:
            await runner.cleanup()
        # Клиенты закрываем и на неудачном старте: иначе aiohttp досыпает
        # в вывод «Unclosed client session» на каждого агента.
        for client in broker.clients.values():
            await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentsChat session broker")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument(
        "--agents",
        default="",
        help="обслуживать только этих агентов, через запятую (по умолчанию всех)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    # --verbose говорит о нашей работе, а не о работе matrix-nio: на DEBUG она
    # печатает каждое событие каждой комнаты и схему каждого ответа /sync,
    # в которых лог брокера тонет.
    log.setLevel(logging.DEBUG if args.verbose else logging.INFO)
    logging.getLogger("nio").setLevel(logging.WARNING)
    try:
        asyncio.run(run(Path(args.config).resolve(), args.agents))
    except ValueError as error:
        # Опечатка в --agents или имя, которого ещё нет в конфиге. Причина
        # известна точно, и traceback к ней ничего не добавляет.
        raise SystemExit(f"БРОКЕР НЕ ЗАПУЩЕН: {error}") from None
    except KeyboardInterrupt:
        log.info("брокер остановлен")


if __name__ == "__main__":
    main()
