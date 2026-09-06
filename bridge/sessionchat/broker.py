#!/usr/bin/env python3
"""Брокер чата сессий.

Одна комната Matrix, три аккаунта агентов и человек как равноправный
участник. К брокеру по HTTP на 127.0.0.1 подключаются ЖИВЫЕ сессии CLI —
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
from aiohttp import ClientSession, ClientTimeout, web
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
    WAIT_SECONDS,
    Envelope,
)

log = logging.getLogger("agentschat.broker")


def bounded(needle: str, haystack: str) -> bool:
    """Вхождение с границами слова.

    Простое вхождение подстроки адресовало бы codex сообщением про
    @codex-extra, а Claude Code — любым упоминанием claude-code-2.
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
    # Глубина последнего доставленного сообщения: исходящие получают +1.
    depth: int = 0
    signal: asyncio.Event = field(default_factory=asyncio.Event)
    # Для агентов с push-доставкой: их собственный HTTP-сервер и id сессии.
    push_url: str = ""
    push_session: str = ""

    @property
    def push(self) -> bool:
        return bool(self.push_url and self.push_session)

    def state(self) -> str:
        now = time.time()
        if self.push:
            # Слушать нечего: брокер сам кладёт сообщение в сессию.
            return "push"
        if self.open_waits > 0 or now < self.listening_until:
            return "слушает"
        if self.last_delivery and now - self.last_delivery < 120:
            return "обрабатывает"
        return "НЕ СЛУШАЕТ"

    def throttled(self) -> bool:
        now = time.time()
        while self.sends and now - self.sends[0] > 60:
            self.sends.popleft()
        return len(self.sends) >= MAX_SENDS_PER_MINUTE


class Broker:
    def __init__(self, cfg: dict):
        self.room = cfg["room_id"]
        self.port = int(cfg.get("sessionchat_port", DEFAULT_PORT))
        verify = cfg.get("verify_ssl", True)
        tls = (
            ssl.create_default_context(cafile=verify)
            if isinstance(verify, str)
            else bool(verify)
        )
        self.names: dict[str, str] = {}
        self.clients: dict[str, AsyncClient] = {}
        # Агенты, которым брокер доставляет сам, через их собственный HTTP API
        # (OpenCode). Для остальных доставка идёт через listener и его выход.
        self.push_urls: dict[str, str] = {}
        self.http: ClientSession | None = None
        for agent, data in cfg["agents"].items():
            if data.get("server_url"):
                self.push_urls[agent] = str(data["server_url"]).rstrip("/")
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
            self.names[agent] = data.get("display_name", agent)
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
        """Адресация по логину: localpart, display name, пилюля или @room."""
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
            if (
                bounded(localpart, low)
                or bounded(self.names[agent], low)
                or user_id in pills
            ):
                found.append(agent)
        return found

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
            if session.push:
                try:
                    await self.deliver_push(session, envelope)
                except Exception as error:  # noqa: BLE001
                    log.error("доставка в сессию %s не удалась: %s", agent, error)
                    await self.publish(
                        agent,
                        f"(сообщение не доставлено в сессию {agent}: {error}. "
                        f"Проверьте, запущен ли её сервер на {session.push_url}.)",
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

    async def resolve_push_session(self, base: str) -> str:
        """Определяет сессию агента как самую недавно обновлённую.

        Спросить «какая сессия меня сейчас выполняет» у OpenCode нечем, но в
        момент login команду выполняет именно она, поэтому по времени
        обновления она заведомо первая.
        """
        if self.http is None:
            raise RuntimeError("HTTP-клиент брокера не инициализирован")
        async with self.http.get(f"{base}/api/session") as response:
            response.raise_for_status()
            payload = await response.json()
        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or not rows:
            raise RuntimeError(f"на {base} нет ни одной сессии")
        newest = max(rows, key=lambda r: int(r.get("time", {}).get("updated", 0)))
        return str(newest["id"])

    async def deliver_push(self, session: Session, envelope: Envelope) -> None:
        if self.http is None:
            raise RuntimeError("HTTP-клиент брокера не инициализирован")
        url = f"{session.push_url}/api/session/{session.push_session}/prompt"
        body = {
            "prompt": {"text": envelope.render(restart_listener=False)},
            # queue, а не steer: не перебиваем агента на середине его хода.
            "delivery": "queue",
        }
        async with self.http.post(url, json=body) as response:
            response.raise_for_status()
        session.last_delivery = time.time()
        session.depth = envelope.depth

    async def sync_forever(self) -> None:
        self.reader.add_event_callback(self.on_message, RoomMessageText)
        await self.reader.sync_forever(timeout=30000, full_state=True)

    # ------------------------------------------------------------------ HTTP

    def session_of(self, data: dict) -> Session:
        agent = str(data.get("agent", ""))
        session = self.sessions.get(agent)
        if session is None or session.token != str(data.get("token", "")):
            raise web.HTTPConflict(text="сессия не подключена или токен неверен")
        return session

    async def handle_login(self, request: web.Request) -> web.Response:
        data = await request.json()
        agent = str(data.get("agent", ""))
        if agent not in self.clients:
            raise web.HTTPNotFound(text=f"неизвестный агент: {agent}")
        existing = self.sessions.get(agent)
        if existing is not None:
            since = datetime.fromtimestamp(existing.since).strftime("%H:%M:%S")
            raise web.HTTPConflict(
                text=(
                    f"агент {agent} уже подключён с {since} "
                    f"({existing.label}, {existing.state()}). "
                    "Перехват запрещён: он оставил бы ту сессию с мёртвым "
                    "listener, который больше ничего не получит. Освободите "
                    f"слот: agentschat logout --agent {agent} --force"
                )
            )
        session = Session(
            agent,
            str(data.get("label", "")) or agent,
            secrets.token_hex(16),
            time.time(),
        )
        base = self.push_urls.get(agent, "")
        if base:
            try:
                session.push_session = await self.resolve_push_session(base)
            except Exception as error:  # noqa: BLE001
                raise web.HTTPBadGateway(
                    text=(
                        f"сервер агента {agent} на {base} недоступен или не имеет "
                        f"сессий: {error}. Запустите его с --port и повторите."
                    )
                ) from error
            session.push_url = base
            log.info(
                "сессия %s получает доставку push в %s (сессия %s)",
                agent,
                base,
                session.push_session,
            )
        self.sessions[agent] = session
        log.info("подключена сессия %s (%s)", agent, session.label)
        return web.json_response(
            {
                "token": session.token,
                "room": self.room,
                "mode": "push" if session.push else "listener",
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
        if session.push:
            raise web.HTTPConflict(
                text=(
                    f"агенту {session.agent} брокер доставляет сам, listener ему "
                    "не нужен и работать не будет. Не запускай его."
                )
            )
        session.open_waits += 1
        session.listening_until = time.time() + LISTEN_GRACE
        try:
            if not session.inbox:
                session.signal.clear()
                try:
                    await asyncio.wait_for(session.signal.wait(), WAIT_SECONDS)
                except asyncio.TimeoutError:
                    return web.Response(status=204)
            envelope = session.inbox.popleft()
            session.depth = envelope.depth
            session.last_delivery = time.time()
            return web.json_response(envelope.as_dict())
        finally:
            session.open_waits -= 1
            session.listening_until = time.time() + LISTEN_GRACE

    async def handle_say(self, request: web.Request) -> web.Response:
        data = await request.json()
        session = self.session_of(data)
        text = str(data.get("text", "")).strip()
        if not text:
            raise web.HTTPBadRequest(text="пустое сообщение")
        depth = session.depth + 1
        if depth > MAX_DEPTH:
            raise web.HTTPForbidden(
                text=(
                    f"достигнута предельная глубина цепочки ({MAX_DEPTH}) без "
                    "участия человека. Сообщение не отправлено: нужен человек."
                )
            )
        if session.throttled():
            raise web.HTTPTooManyRequests(
                text=f"превышен предел {MAX_SENDS_PER_MINUTE} сообщений в минуту"
            )
        session.sends.append(time.time())
        event_id = await self.publish(session.agent, text, depth)
        return web.json_response({"event_id": event_id, "depth": depth})

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
    broker.http = ClientSession(timeout=ClientTimeout(total=30))
    await broker.join_all()
    runner = web.AppRunner(broker.app())
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", broker.port).start()
    log.info("БРОКЕР ГОТОВ комната=%s порт=%s", broker.room, broker.port)
    try:
        await broker.sync_forever()
    finally:
        await runner.cleanup()
        if broker.http is not None:
            await broker.http.close()
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
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    asyncio.run(run(Path(args.config).resolve(), args.agents))


if __name__ == "__main__":
    main()
