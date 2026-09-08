#!/usr/bin/env python3
"""
Мост Matrix <-> CLI-агент для проекта AgentsChat.

Один процесс = один агент (один Matrix-аккаунт бота). Слушает заданную
комнату через долгий /sync, и при подходящем сообщении запускает CLI-агента
в headless-режиме, а его финальный ответ публикует обратно в комнату от
имени бота.

Запуск (после заполнения config.yaml по образцу config.example.yaml):

    python matrix_bridge.py --config config.yaml --agent claude-code
    python matrix_bridge.py --config config.yaml --agent codex
    python matrix_bridge.py --config config.yaml --agent opencode

Подробности архитектуры и обоснование дефолтов (mention_only,
max_replies_per_minute) — в docs/ARCHITECTURE.md. Точный формат вывода codex
и opencode в JSON-режиме не проверялся вживую — см. docs/AGENTS_INTEGRATION.md,
почему для них по умолчанию выбраны более консервативные result_mode.
"""

import argparse
import asyncio
import json
import logging
import re
import ssl
import sys
import tempfile
import time
from collections import deque
from pathlib import Path

import yaml
from nio import (
    AsyncClient,
    AsyncClientConfig,
    Event,
    JoinResponse,
    MatrixRoom,
    RoomGetStateEventResponse,
    RoomMessageText,
)

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

log = logging.getLogger("agentschat.bridge")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def is_addressed(
    event,
    body: str,
    user_id: str,
    display_name: str,
    aliases,
    respond_to_room_mention: bool,
) -> bool:
    """Считаем, что сообщение адресовано этому агенту, если выполнено любое из:

    1. Персональное упоминание — в тексте есть localpart (@claude-code) или
       display name агента, ИЛИ Matrix-пилл на этого пользователя (поле
       m.mentions.user_ids в содержимом события — так Element оформляет
       упоминание, выбранное из списка).
    2. Любой из дополнительных псевдонимов из aliases (напр. "все", "agents").
    3. Широковещательное @room (аналог slack @here/@channel) — только если у
       агента включён respond_to_room_mention. Ловим и текстовое "@room",
       и m.mentions.room = true.
    """
    body_low = body.lower()
    localpart = user_id.split(":", 1)[0]  # "@claude-code"

    # (1) текстовое персональное упоминание
    if localpart.lower() in body_low or display_name.lower() in body_low:
        return True

    # (1) Matrix-пилл на этого пользователя (rich mention)
    try:
        mentions = (event.source.get("content", {}) or {}).get("m.mentions", {}) or {}
    except AttributeError:
        mentions = {}
    if user_id in (mentions.get("user_ids") or []):
        return True

    # (2) настраиваемые псевдонимы адресации
    for alias in aliases or []:
        if alias and alias.lower() in body_low:
            return True

    # (3) широковещательное @room
    if respond_to_room_mention:
        if "@room" in body_low or mentions.get("room") is True:
            return True

    return False


class AgentBridge:
    def __init__(
        self,
        homeserver_url: str,
        verify_ssl,
        room_id: str,
        agent_name: str,
        agent_cfg: dict,
    ):
        # Значение из конфига: внутренний ID (!...), алиас (#...) — приводим
        # к внутреннему ID при старте в run() через join().
        self.configured_room = room_id
        self.room_id = room_id  # будет переопределён после join
        self.agent_name = agent_name
        self.cfg = agent_cfg
        self.user_id = agent_cfg["user_id"]
        self.display_name = agent_cfg.get("display_name", agent_name)
        self.mention_only = agent_cfg.get("mention_only", True)
        self.aliases = agent_cfg.get("aliases", [])
        self.respond_to_room_mention = agent_cfg.get("respond_to_room_mention", True)
        self.max_replies_per_minute = agent_cfg.get("max_replies_per_minute", 6)
        self.timeout_seconds = agent_cfg.get("timeout_seconds", 600)
        self.workdir = agent_cfg["workdir"]
        self.command_template = agent_cfg["command"]
        self.result_mode = agent_cfg.get("result_mode", "raw_stdout")
        self.result_json_path = agent_cfg.get("result_json_path")
        self.output_file_template = agent_cfg.get("output_file")

        self._reply_timestamps = deque()
        self._last_throttle_notice = 0.0
        self._start_time_ms = int(time.time() * 1000)

        # verify_ssl из config.yaml: true / false / путь к CA-файлу
        # (например, к rootCA.pem от mkcert -CAROOT, если вдруг aiohttp на
        # этой машине не подхватывает системное хранилище Windows сам).
        if isinstance(verify_ssl, str):
            ssl_arg = ssl.create_default_context(cafile=verify_ssl)
        else:
            ssl_arg = True if verify_ssl else False
        self.client = AsyncClient(
            homeserver_url,
            self.user_id,
            config=AsyncClientConfig(store_sync_tokens=False),
            ssl=ssl_arg,
        )
        self.client.restore_login(
            user_id=self.user_id,
            device_id=agent_cfg.get("device_id") or "AGENTSCHAT_BRIDGE",
            access_token=agent_cfg["access_token"],
        )

    def _rate_limited(self) -> bool:
        now = time.time()
        while self._reply_timestamps and now - self._reply_timestamps[0] > 60:
            self._reply_timestamps.popleft()
        return len(self._reply_timestamps) >= self.max_replies_per_minute

    async def _notify_throttle(self):
        now = time.time()
        if now - self._last_throttle_notice < 300:
            return  # не спамим предупреждением чаще раза в 5 минут
        self._last_throttle_notice = now
        await self._send(
            f"(лимит {self.max_replies_per_minute} ответов/мин для "
            f"{self.display_name} достигнут, сообщение проигнорировано)"
        )

    async def _send(self, text: str):
        # Защита от каскада: не даём ответу агента самому будить остальных
        # ботов широковещательным @room. Разрываем строку нулевой шириной,
        # чтобы визуально осталось "@room", но триггером не работало, и
        # явно гасим rich-mention room в m.mentions.
        safe = text.replace("@room", "@​room")
        await self.client.room_send(
            room_id=self.room_id,
            message_type="m.room.message",
            content={
                "msgtype": "m.text",
                "body": safe,
                "m.mentions": {},
            },
        )

    def _build_command(self, prompt: str, tmp_path: str):
        return [
            part.replace("{prompt}", prompt)
            .replace("{workdir}", self.workdir)
            .replace("{tmp}", tmp_path)
            for part in self.command_template
        ]

    async def _run_cli(self, prompt: str) -> str:
        tmp_path = ""
        if self.result_mode == "file":
            fd, tmp_path = tempfile.mkstemp(prefix="agentschat_", suffix=".txt")
            import os

            os.close(fd)
            Path(tmp_path).unlink(missing_ok=True)  # CLI должен создать файл сам

        cmd = self._build_command(prompt, tmp_path)
        log.info("[%s] running: %s", self.agent_name, cmd)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=self.workdir,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return f"(таймаут {self.timeout_seconds}s при вызове {self.agent_name})"

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            log.warning(
                "[%s] exit=%s stderr=%s",
                self.agent_name,
                proc.returncode,
                stderr[:2000],
            )
            return f"(ошибка запуска {self.agent_name}, код {proc.returncode}: {stderr[:500] or 'см. логи моста'})"

        if self.result_mode == "json_field":
            try:
                data = json.loads(stdout.strip())
                value = data
                for key in self.result_json_path.split("."):
                    value = value[key]
                return str(value)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "[%s] failed to parse json result: %s", self.agent_name, exc
                )
                return stdout.strip() or "(пустой ответ)"

        if self.result_mode == "file":
            try:
                text = Path(tmp_path).read_text(encoding="utf-8", errors="replace")
                return text.strip() or "(пустой файл ответа)"
            except FileNotFoundError:
                return stdout.strip() or "(файл ответа не создан, см. stdout/логи)"
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        # raw_stdout
        return strip_ansi(stdout).strip() or "(пустой ответ)"

    async def on_any_event(self, room: MatrixRoom, event):
        """Диагностика: логируем ЛЮБОЕ событие в нашей комнате и его тип.
        Помогает понять, доходят ли новые сообщения и как nio их разбирает
        (например, не как RoomMessageText). Можно убрать, когда всё работает."""
        if room.room_id != self.room_id:
            return
        raw_type = ""
        try:
            raw_type = (event.source or {}).get("type", "")
        except AttributeError:
            pass
        log.info(
            "[%s] СОБЫТИЕ class=%s type=%s sender=%s",
            self.agent_name,
            type(event).__name__,
            raw_type,
            getattr(event, "sender", "?"),
        )

    async def on_message(self, room: MatrixRoom, event: RoomMessageText):
        if room.room_id != self.room_id:
            log.debug(
                "[%s] событие из другой комнаты %s (ждём %s), пропуск",
                self.agent_name,
                room.room_id,
                self.room_id,
            )
            return
        if event.sender == self.user_id:
            return  # своё сообщение

        body = event.body or ""
        log.info(
            "[%s] получено от %s (ts=%s): %r",
            self.agent_name,
            event.sender,
            event.server_timestamp,
            body[:100],
        )

        if event.server_timestamp < self._start_time_ms:
            log.info(
                "[%s] -> пропуск: история (ts=%s < старт=%s)",
                self.agent_name,
                event.server_timestamp,
                self._start_time_ms,
            )
            return  # игнорируем историю, накопленную до старта моста

        if self.mention_only and not is_addressed(
            event,
            body,
            self.user_id,
            self.display_name,
            self.aliases,
            self.respond_to_room_mention,
        ):
            log.info(
                "[%s] -> пропуск: не адресовано мне (нет @%s / имени / @room / алиаса)",
                self.agent_name,
                self.user_id.split(":", 1)[0].lstrip("@"),
            )
            return

        log.info("[%s] -> сообщение адресовано мне, запускаю CLI", self.agent_name)

        if self._rate_limited():
            await self._notify_throttle()
            return
        self._reply_timestamps.append(time.time())

        try:
            reply = await self._run_cli(body)
        except Exception as exc:  # noqa: BLE001
            log.exception("[%s] unexpected error", self.agent_name)
            reply = f"(внутренняя ошибка моста {self.agent_name}: {exc})"

        await self._send(reply)

    async def _join_room(self, target: str) -> str | None:
        """Вступает в комнату target (внутренний ID '!...' или алиас '#...')
        и возвращает внутренний room_id, либо None при ошибке.

        Почему не self.client.join(): nio отправляет POST /join без тела
        запроса, а Continuwuity (в отличие от Synapse) требует хотя бы пустой
        JSON '{}' и иначе отвечает M_BAD_JSON "EOF while parsing". Поэтому
        шлём запрос сами через ту же сессию nio, с телом '{}'.
        """
        from urllib.parse import quote

        method = "POST"
        path = (
            f"/_matrix/client/v3/join/{quote(target, safe='')}"
            f"?access_token={quote(self.client.access_token, safe='')}"
        )
        resp = await self.client._send(JoinResponse, method, path, data="{}")
        if isinstance(resp, JoinResponse):
            return resp.room_id
        log.error(
            "[%s] не удалось войти в комнату %r: %s\n"
            "  Проверьте room_id в config.yaml: нужен внутренний ID "
            "(начинается с '!') или алиас (начинается с '#'), не имя "
            "пространства. Внутренний ID: в Element откройте комнату -> "
            "Room settings -> Advanced -> Internal room ID. И убедитесь, "
            "что этот бот приглашён в комнату.",
            self.agent_name,
            target,
            resp,
        )
        return None

    async def run(self):
        # Вступаем в комнату (или принимаем приглашение) и приводим алиас/ID к
        # внутреннему room_id. Принимает и "!id:server", и "#alias:server".
        # Для приватной комнаты бот должен быть предварительно приглашён
        # (см. docs/INSTALL.md, шаг 6) — тогда join принимает инвайт.
        room_id = await self._join_room(self.configured_room)
        if room_id is None:
            return
        self.room_id = room_id
        creation = await self.client.room_get_state_event(room_id, "m.room.create")
        if not isinstance(creation, RoomGetStateEventResponse):
            raise RuntimeError(
                f"Не удалось проверить тип комнаты {room_id}: {creation}"
            )
        if creation.content.get("type") == "m.space":
            raise RuntimeError(
                f"{self.configured_room} — пространство, а не комната чата. "
                "Укажите Internal room ID комнаты General в config.yaml."
            )
        log.info(
            "[%s] в комнате %s (из %r)",
            self.agent_name,
            self.room_id,
            self.configured_room,
        )

        self.client.add_event_callback(self.on_message, RoomMessageText)
        self.client.add_event_callback(self.on_any_event, Event)  # диагностика
        log.info(
            "[%s] синхронизация начата, жду сообщений в %s",
            self.agent_name,
            self.room_id,
        )
        # sync_forever сам делает первичную синхронизацию (первый цикл с
        # timeout=0), затем long-poll за новыми событиями. Старые сообщения из
        # первичной синхронизации отсекаются в on_message по _start_time_ms.
        await self.client.sync_forever(timeout=30000, full_state=True)


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


async def main_async(config_path: str, agent_name: str):
    cfg = load_config(config_path)
    if agent_name not in cfg["agents"]:
        print(
            f"Агент '{agent_name}' не найден в {config_path}. "
            f"Доступны: {', '.join(cfg['agents'])}",
            file=sys.stderr,
        )
        sys.exit(1)

    bridge = AgentBridge(
        homeserver_url=cfg["homeserver_url"],
        verify_ssl=cfg.get("verify_ssl", True),
        room_id=cfg["room_id"],
        agent_name=agent_name,
        agent_cfg=cfg["agents"][agent_name],
    )
    try:
        await bridge.run()
    finally:
        await bridge.client.close()


def main():
    parser = argparse.ArgumentParser(description="AgentsChat Matrix<->CLI bridge")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--agent", required=True, help="claude-code | codex | opencode")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    asyncio.run(main_async(args.config, args.agent))


if __name__ == "__main__":
    main()
