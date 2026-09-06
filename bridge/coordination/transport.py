import ssl
import time
from urllib.parse import quote

from nio import (
    AsyncClient,
    AsyncClientConfig,
    Event,
    JoinResponse,
    RoomGetStateResponse,
    RoomMessageText,
    RoomMessagesResponse,
    RoomSendResponse,
    SyncResponse,
)

from .engine import Engine
from .model import Incoming, Notice
from .settings import Settings
from .store import Store


def incoming(room: str, event: Event) -> Incoming | None:
    if not isinstance(event, RoomMessageText):
        return None
    content = event.source.get("content", {})
    if content.get("com.agentschat.notice"):
        return None
    relation = content.get("m.relates_to", {})
    thread = (
        relation.get("event_id", "") if relation.get("rel_type") == "m.thread" else ""
    )
    body = event.body
    if body.startswith("> ") and "\n\n" in body:
        body = body.split("\n\n", 1)[1]
    return Incoming(event.event_id, room, event.sender, body, thread)


class Matrix:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.started = int(time.time() * 1000)
        self.clients: dict[str, AsyncClient] = {}
        for name, account in settings.accounts.items():
            verify = settings.verify_ssl
            tls = (
                ssl.create_default_context(cafile=verify)
                if isinstance(verify, str)
                else verify
            )
            client = AsyncClient(
                settings.homeserver,
                account.user_id,
                ssl=tls,
                config=AsyncClientConfig(store_sync_tokens=False),
            )
            client.restore_login(
                account.user_id, account.device_id, account.access_token
            )
            self.clients[name] = client
        self.reader = next(iter(self.clients.values()))

    async def close(self) -> None:
        for client in self.clients.values():
            await client.close()

    async def setup(self) -> None:
        for client in self.clients.values():
            for room in (self.settings.general, self.settings.escalations):
                path = f"/_matrix/client/v3/join/{quote(room, safe='')}?access_token={quote(client.access_token, safe='')}"
                response = await client._send(JoinResponse, "POST", path, data="{}")
                if not isinstance(response, JoinResponse):
                    raise RuntimeError(f"Cannot join {room}: {response}")
        for room in (self.settings.general, self.settings.escalations):
            state = await self.reader.room_get_state(room)
            if not isinstance(state, RoomGetStateResponse):
                raise RuntimeError(f"Cannot inspect room {room}: {state}")
            for event in state.events:
                if event["type"] == "m.room.encryption":
                    raise ValueError("Encrypted rooms are not supported by this bridge")
                if (
                    event["type"] == "m.room.create"
                    and event["content"].get("type") == "m.space"
                ):
                    raise ValueError(f"{room} is a space, not a chat room")

    async def backfill(self, room: str, start: str, checkpoint: str) -> list[Event]:
        collected: list[Event] = []
        seen: set[str] = set()
        while start and start not in seen:
            seen.add(start)
            page = await self.reader.room_messages(room, start=start, limit=100)
            if not isinstance(page, RoomMessagesResponse):
                raise RuntimeError(f"Cannot recover Matrix history: {page}")
            for event in page.chunk:
                if event.event_id == checkpoint:
                    return list(reversed(collected))
                collected.append(event)
            start = page.end or ""
        raise RuntimeError(
            "Matrix history checkpoint is unavailable; refusing to silently skip requests"
        )

    async def poll(self, store: Store, engine: Engine) -> None:
        cursor = store.get_meta("sync")
        response = await self.reader.sync(
            timeout=1000, since=cursor or None, full_state=True
        )
        if not isinstance(response, SyncResponse):
            raise RuntimeError(f"Matrix sync failed: {response}")
        for room, info in response.rooms.join.items():
            if room not in {self.settings.general, self.settings.escalations}:
                continue
            events = list(info.timeline.events)
            checkpoint = store.get_meta("last:" + room)
            if (
                cursor
                and info.timeline.limited
                and checkpoint
                and all(e.event_id != checkpoint for e in events)
            ):
                events = (
                    await self.backfill(room, info.timeline.prev_batch, checkpoint)
                    + events
                )
            for event in events:
                message = incoming(room, event)
                if message is not None and (
                    cursor or event.server_timestamp >= self.started
                ):
                    engine.ingest(message)
            if events:
                store.set_meta("last:" + room, events[-1].event_id)
        store.set_meta("sync", response.next_batch)

    async def send(self, notice: Notice) -> str:
        mentions: dict[str, object] = (
            {"user_ids": sorted(self.settings.humans)} if notice.human else {}
        )
        body = notice.body
        if notice.human:
            body = " ".join(sorted(self.settings.humans)) + "\n" + body
        content: dict[str, object] = {
            "msgtype": "m.text",
            "body": body,
            "m.mentions": mentions,
            "com.agentschat.notice": True,
        }
        if notice.thread:
            content["m.relates_to"] = {
                "rel_type": "m.thread",
                "event_id": notice.thread,
                "is_falling_back": True,
                "m.in_reply_to": {"event_id": notice.thread},
            }
        response = await self.clients[notice.agent].room_send(
            notice.room, "m.room.message", content, tx_id=notice.id
        )
        if not isinstance(response, RoomSendResponse):
            raise RuntimeError(f"Matrix publication failed: {response}")
        return response.event_id
