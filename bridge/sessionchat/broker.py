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
import json
import logging
import re
import secrets
import ssl
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import NoReturn
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

from .i18n import DEFAULT_LANGUAGE, LANGUAGES, Catalogue
from .protocol import (
    DEFAULT_PORT,
    LISTEN_GRACE,
    MAX_DEPTH,
    MAX_SENDS_PER_MINUTE,
    STALE_SECONDS,
    WAIT_SECONDS,
    Envelope,
)
from .store import (
    DuplicateAgent,
    delete_registration,
    insert_registration,
    load_registrations,
    open_read_only,
    open_store,
    update_registration,
)

log = logging.getLogger("agentschat.broker")

REGISTRATIONS_DB = Path(__file__).resolve().parent.parent / "state" / "agentschat.db"
BROKER_CATALOGUE = Catalogue("sessionchat", "broker_messages")

ADVICE_SENTENCES = {
    "over_limit": ("advice_over_limit",),
    "polled": ("advice_polled", "advice_polled_meaning"),
    "silent": ("advice_silent", "advice_silent_meaning"),
}

SLOT_TAKEN_SENTENCES = (
    "slot_taken_not_yours",
    "slot_taken_token_proof",
    "slot_taken_ask_human",
    "slot_taken_force",
)

SESSION_STATES = ("listening", "processing", "not_listening")
NOT_CONNECTED = "not_connected"
AGENT_COLUMN = 14


def dump_json(body: object) -> str:
    return json.dumps(body, ensure_ascii=False)


class LanguageRefused(ValueError):
    pass


def room_language(cfg: dict) -> str:
    value = cfg.get("language", DEFAULT_LANGUAGE)
    if isinstance(value, str) and value in LANGUAGES:
        return value
    raise LanguageRefused(
        f'The config key "language" must be one of: {", ".join(LANGUAGES)} '
        f"(got {ascii(value)})."
    )


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
class Registration:
    """Подключённая живая сессия. Одна на агента: повторный вход — отказ."""

    agent: str
    label: str
    token: str
    registered_at: float
    inbox: deque = field(default_factory=deque)
    sends: deque = field(default_factory=deque)
    open_waits: int = 0
    listening_until: float = 0.0
    last_delivery: float = 0.0
    # Когда пришёл запрос с токеном этой регистрации. Об обмене сообщениями
    # не говорит ничего: пустой /wait, вернувший 204, обновляет отметку так
    # же, как доставка. О живости не говорит ничего: файл с токеном переживает
    # смерть процесса, и предъявить его может осиротевший listener. Это факт о
    # прошлом; живость считает state_code(), опираясь на open_waits и
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

    def state_code(self) -> str:
        now = time.time()
        if self.open_waits > 0 or now < self.listening_until:
            return "listening"
        if self.last_delivery and now - self.last_delivery < 120:
            return "processing"
        return "not_listening"

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
        last = max(self.registered_at, self.last_delivery, self.last_contact)
        return now - last > STALE_SECONDS

    def advice(self) -> tuple[str, dict[str, int]]:
        """Что делать тому, кому отказано во входе на этот слот.

        Отказ без срока провоцирует перехват: сессия видит «занято», не знает,
        надолго ли, и тянется к --force. А занимать слот может её собственный
        труп — регистрация от процесса, убитого минуту назад.
        """
        now = time.time()
        last = max(self.registered_at, self.last_delivery, self.last_contact)
        quiet = int(now - last)
        # Освободится, когда кончится и фора слушателя, и счёт молчания.
        left = int(max(self.listening_until, last + STALE_SECONDS) - now)
        timing = {"quiet": quiet, "left": left}
        if left <= 0:
            return "over_limit", timing
        if self.open_waits > 0 or now < self.listening_until:
            # «Она жива» здесь сказать нельзя: убитый процесс оставляет свой
            # запрос висеть, и брокер ещё минуту видит опрос от того, кого уже
            # нет. Известно только, когда был последний опрос.
            return "polled", timing
        return "silent", timing

    def throttled(self) -> bool:
        now = time.time()
        while self.sends and now - self.sends[0] > 60:
            self.sends.popleft()
        return len(self.sends) >= MAX_SENDS_PER_MINUTE


class Broker:
    def __init__(self, cfg: dict, store_path: Path | None = None):
        self.language = room_language(cfg)
        self.state_width = max(len(self.state_word(state)) for state in SESSION_STATES)
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
                    self._compose(
                        ("unknown_delivery", "unknown_delivery_allowed"),
                        agent=agent,
                        kind=kind,
                    )
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
        self.store_path = store_path or REGISTRATIONS_DB
        self.registrations: dict[str, Registration] = self._restore_registrations()
        self._login_locks: dict[str, asyncio.Lock] = {}
        self.reader = next(iter(self.clients.values()))
        self.started_ms = int(time.time() * 1000)

    def _restore_registrations(self) -> dict[str, Registration]:
        if not self.store_path.exists():
            return {}
        with open_read_only(self.store_path) as store:
            rows = load_registrations(store)
        restored = {}
        for agent, label, token, registered_at, depth in rows:
            restored[agent] = Registration(
                agent,
                label,
                token,
                registered_at,
                depth=depth,
            )
            restored[agent].listener_kind = self.delivery_kinds.get(agent, "listener")
            restored[agent].max_depth = self.max_depth
        return restored

    async def _store_write(self, operation) -> None:
        with open_store(self.store_path) as store:
            operation(store)

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
            return list(self.registrations)
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
            registration = self.registrations.get(agent)
            if registration is None:
                if human:
                    await self.publish(
                        agent,
                        self._notice(
                            ("notice_not_connected", "notice_not_connected_login"),
                            agent=agent,
                        ),
                        0,
                    )
                continue
            registration.inbox.append(envelope)
            registration.signal.set()

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

    def _compose(self, keys: tuple[str, ...], **params: object) -> str:
        return " ".join(
            BROKER_CATALOGUE.text(self.language, f"broker.{key}", **params)
            for key in keys
        )

    def _notice(self, keys: tuple[str, ...], **params: object) -> str:
        return f"({self._compose(keys, **params)})"

    def state_word(self, state: str) -> str:
        return self._compose((f"state_{state}",))

    def _answer(self, body: dict) -> web.Response:
        return web.json_response(body, dumps=dump_json)

    def _refusal(
        self,
        status: type[web.HTTPException],
        code: str,
        params: dict[str, object] | None = None,
        keys: tuple[str, ...] | None = None,
        **words: str,
    ) -> web.HTTPException:
        params = params or {}
        message = self._compose(keys or (code,), **params, **words)
        body = {"code": code, "message": message, "params": params}
        return status(text=dump_json(body), content_type="application/json")

    def registration_of(self, data: dict) -> Registration:
        agent = str(data.get("agent", ""))
        registration = self.registrations.get(agent)
        if registration is None or registration.token != str(data.get("token", "")):
            raise self._refusal(web.HTTPConflict, "session_not_registered")
        registration.last_contact = time.time()
        return registration

    async def _release_stale(self, agent: str) -> Registration | None:
        existing = self.registrations.get(agent)
        if existing is None or not existing.stale():
            return existing
        quiet = int(
            time.time()
            - max(
                existing.registered_at,
                existing.last_delivery,
                existing.last_contact,
            )
        )
        log.info(
            "слот %s освобождён: прежняя сессия молчала %sс (%s)",
            agent,
            quiet,
            existing.label,
        )
        await self._delete_stored(agent)
        self.registrations.pop(agent, None)
        return None

    def _refuse_taken_slot(self, agent: str, existing: Registration) -> NoReturn:
        registered = datetime.fromtimestamp(existing.registered_at).strftime("%H:%M:%S")
        advice, timing = existing.advice()
        state = existing.state_code()
        params = {
            "agent": agent,
            "registered": registered,
            "label": existing.label,
            "state": state,
            "advice": advice,
            **timing,
        }
        keys = ("slot_taken", *ADVICE_SENTENCES[advice], *SLOT_TAKEN_SENTENCES)
        raise self._refusal(
            web.HTTPConflict,
            "slot_taken",
            params,
            keys,
            state_word=self.state_word(state),
        )

    async def handle_login(self, request: web.Request) -> web.Response:
        data = await request.json()
        agent = str(data.get("agent", ""))
        if agent not in self.clients:
            raise self._refusal(web.HTTPNotFound, "unknown_agent", {"agent": agent})
        async with self._login_lock(agent):
            existing = await self._release_stale(agent)
            if data.get("reconnect"):
                if existing is None:
                    raise self._refusal(
                        web.HTTPConflict,
                        "reconnect_without_registration",
                        {"agent": agent},
                        (
                            "reconnect_without_registration",
                            "reconnect_without_registration_hint",
                        ),
                    )
                if existing.token != str(data.get("token", "")):
                    raise self._refusal(
                        web.HTTPConflict,
                        "reconnect_token_mismatch",
                        {"agent": agent},
                        ("reconnect_token_mismatch", "reconnect_token_mismatch_owner"),
                    )
                existing.label = str(data.get("label", "")) or existing.label
                existing.last_contact = time.time()
                await self._store_write(
                    lambda store: update_registration(
                        store, agent, label=existing.label
                    )
                )
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
                self._refuse_taken_slot(agent, existing)
            token = secrets.token_hex(16)
            label = str(data.get("label", "")) or agent
            registered_at = time.time()
            registration = Registration(
                agent,
                label,
                token,
                registered_at,
            )
            registration.listener_kind = self.delivery_kinds.get(agent, "listener")
            registration.max_depth = self.max_depth
            try:
                await self._store_write(
                    lambda store: insert_registration(
                        store, agent, label, token, registered_at, depth=0
                    )
                )
            except DuplicateAgent:
                # Память и store уже разошлись, и в store сидит чужая строка.
                # Она держит слот: не создавая вторую регистрацию поверх неё,
                # отказываем как за занятый слот.
                self.registrations.pop(agent, None)
                restored = self._restore_one(agent)
                if restored is not None:
                    self.registrations[agent] = restored
                raise self._refusal(
                    web.HTTPConflict,
                    "slot_in_store",
                    {"agent": agent},
                    ("slot_in_store", "slot_in_store_next"),
                ) from None
            self.registrations[agent] = registration
            log.info("подключена сессия %s (%s)", agent, registration.label)
            return web.json_response(
                {
                    "token": token,
                    "room": self.room,
                    "mode": registration.mode,
                }
            )

    def _login_lock(self, agent: str) -> asyncio.Lock:
        if agent not in self._login_locks:
            self._login_locks[agent] = asyncio.Lock()
        return self._login_locks[agent]

    async def handle_logout(self, request: web.Request) -> web.Response:
        data = await request.json()
        agent = str(data.get("agent", ""))
        if not data.get("force"):
            self.registration_of(data)
        await self._delete_stored(agent)
        self.registrations.pop(agent, None)
        log.info("отключена сессия %s", agent)
        return web.json_response({"ok": True})

    async def _delete_stored(self, agent: str) -> None:
        await self._store_write(lambda store: delete_registration(store, agent))

    def _restore_one(self, agent: str) -> Registration | None:
        if not self.store_path.exists():
            return None
        with open_read_only(self.store_path) as store:
            rows = [row for row in load_registrations(store) if row[0] == agent]
        if not rows:
            return None
        _, label, token, registered_at, depth = rows[0]
        restored = Registration(agent, label, token, registered_at, depth=depth)
        restored.listener_kind = self.delivery_kinds.get(agent, "listener")
        restored.max_depth = self.max_depth
        return restored

    async def handle_wait(self, request: web.Request) -> web.Response:
        registration = self.registration_of(dict(request.query))
        registration.open_waits += 1
        registration.listening_until = time.time() + LISTEN_GRACE
        try:
            if not registration.inbox:
                registration.signal.clear()
                try:
                    await asyncio.wait_for(registration.signal.wait(), WAIT_SECONDS)
                except asyncio.TimeoutError:
                    return web.Response(status=204)
            if not registration.inbox:
                # Разбудили, но сообщение уже забрал другой listener на этой же
                # сессии. Так бывает, когда токен из ~/.agentschat/<агент>.json
                # прочитали два процесса. Пустое окно — честный ответ: клиент
                # просто опросит ещё раз. Без этой проверки popleft падал с
                # IndexError, и опоздавший получал 500.
                return web.Response(status=204)
            envelope = registration.inbox.popleft()
            registration.depth = envelope.depth
            registration.last_delivery = time.time()
            return web.json_response(
                {
                    **envelope.as_dict(),
                    "rendered": envelope.render(
                        registration.restart_listener, registration.max_depth
                    ),
                }
            )
        finally:
            registration.open_waits -= 1
            registration.listening_until = time.time() + LISTEN_GRACE

    async def handle_inbox(self, request: web.Request) -> web.Response:
        registration = self.registration_of(dict(request.query))
        return self._answer(
            {"language": self.language, "pending": registration.drain()}
        )

    async def handle_say(self, request: web.Request) -> web.Response:
        data = await request.json()
        registration = self.registration_of(data)
        text = str(data.get("text", "")).strip()
        if not text:
            raise self._refusal(
                web.HTTPBadRequest, "empty_message", keys=("say_empty",)
            )
        depth = registration.depth + 1
        if depth > self.max_depth:
            # Человек, который просто наблюдает, иначе увидит тишину и не
            # поймёт, что цепочка упёрлась в предел: отказ уходит агенту, а в
            # комнате не появляется ничего.
            await self.publish(
                registration.agent,
                self._notice(
                    ("notice_depth_limit", "notice_depth_limit_reset"),
                    max_depth=self.max_depth,
                ),
                0,
            )
            raise self._refusal(
                web.HTTPForbidden,
                "depth_limit",
                {"max_depth": self.max_depth},
                (
                    "say_depth_limit",
                    "say_depth_limit_not_sent",
                    "say_depth_limit_announced",
                ),
            )
        if registration.throttled():
            raise self._refusal(
                web.HTTPTooManyRequests,
                "rate_limit",
                {"limit": MAX_SENDS_PER_MINUTE},
                ("say_rate_limit",),
            )
        registration.sends.append(time.time())
        # Сообщение без обращения попадает в комнату, но не доставляется никому:
        # человек видит его в Element, а агенты — нет. Отправитель при этом
        # уверен, что сказал. На живом прогоне так и вышло: backend объявил
        # протокол в пустоту, а frontend ждал его и не дождался.
        reach = [a for a in self.addressees(text, None) if a != registration.agent]
        event_id = await self.publish(registration.agent, text, depth)
        answer = {"event_id": event_id, "depth": depth, "language": self.language}
        if not reach:
            answer.update(self._unreached(registration, text))
        return self._answer(answer)

    def _unreached(self, registration: Registration, text: str) -> dict[str, str]:
        if self.addressed_to_a_person(text):
            # Обращение есть, просто не к агенту: ответ человеку на его же
            # вопрос — обычное дело, и пугать отправителя тут нечем.
            return {
                "note": self._compose(("say_to_person", "say_to_person_visible")),
                "note_code": "addressed_to_person",
            }
        others = sorted(a for a in self.registrations if a != registration.agent)
        connected = "say_unaddressed_connected" if others else "say_unaddressed_alone"
        return {
            "warning": self._compose(
                ("say_unaddressed", "say_unaddressed_how", connected),
                others=", ".join(others),
            ),
            "warning_code": "unaddressed",
        }

    def _session_status(self, agent: str) -> dict[str, object]:
        registration = self.registrations.get(agent)
        column = f"{agent:<{AGENT_COLUMN}}"
        if registration is None:
            return {
                "agent": agent,
                "state": NOT_CONNECTED,
                "line": self._compose(("status_not_connected",), agent=column),
            }
        quiet = int(
            time.time() - max(registration.last_delivery, registration.registered_at)
        )
        registered = datetime.fromtimestamp(registration.registered_at).strftime(
            "%H:%M:%S"
        )
        state = registration.state_code()
        line = self._compose(
            ("status_session",),
            agent=column,
            state_word=self.state_word(state).ljust(self.state_width),
            label=registration.label,
            registered=registered,
            quiet=quiet,
        )
        return {
            "agent": agent,
            "state": state,
            "label": registration.label,
            "registered": registered,
            "quiet": quiet,
            "line": line,
        }

    async def handle_status(self, request: web.Request) -> web.Response:
        sessions = [self._session_status(agent) for agent in self.clients]
        return self._answer({"language": self.language, "sessions": sessions})

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
    parser = argparse.ArgumentParser(description="Quoroom session broker")
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
    except LanguageRefused as error:
        raise SystemExit(f"BROKER NOT STARTED: {error}") from None
    except ValueError as error:
        # Опечатка в --agents или имя, которого ещё нет в конфиге. Причина
        # известна точно, и traceback к ней ничего не добавляет.
        raise SystemExit(f"БРОКЕР НЕ ЗАПУЩЕН: {error}") from None
    except KeyboardInterrupt:
        log.info("брокер остановлен")


if __name__ == "__main__":
    main()
