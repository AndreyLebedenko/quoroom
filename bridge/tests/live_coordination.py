"""Explicit, isolated real-Matrix/real-CLI acceptance check; not auto-discovered."""

import asyncio
import json
import sys
import uuid
from dataclasses import replace
from pathlib import Path

from nio import RoomCreateResponse, RoomSendResponse

from coordination.service import run
from coordination.settings import Settings
from coordination.store import Store
from coordination.transport import Matrix


async def wait_for(check, timeout=120):
    async def wait():
        while not check():
            await asyncio.sleep(0.25)

    await asyncio.wait_for(wait(), timeout)


async def main():
    base = Settings.load(Path("coordination.yaml").resolve())
    tag = uuid.uuid4().hex[:8]
    root = Path("live-checks") / tag
    project = root / "project"
    project.mkdir(parents=True)
    control = Matrix(base)
    sender = control.clients["codex"]
    rooms = []
    for name in ("General", "Escalations"):
        response = await sender.room_create(
            name=f"AgentsChat acceptance {tag} {name}",
            invite=[a.user_id for n, a in base.accounts.items() if n != "codex"],
        )
        assert isinstance(response, RoomCreateResponse), response
        rooms.append(response.room_id)
    # A technical account plays the human ONLY in these isolated test rooms.
    # Production config validation prohibits treating any bot as a human.
    settings = replace(
        base,
        project=project.resolve(),
        database=(root / "test.sqlite").resolve(),
        general=rooms[0],
        escalations=rooms[1],
        humans={base.accounts["codex"].user_id},
        records_port=8767,
    )
    service = asyncio.create_task(run(settings))
    await wait_for(lambda: settings.database.exists(), 15)
    store = Store(settings.database)
    try:
        await wait_for(lambda: bool(store.get_meta("sync")), 20)

        async def send(body, room=rooms[0]):
            result = await sender.room_send(
                room,
                "m.room.message",
                {"msgtype": "m.text", "body": body, "m.mentions": {}},
            )
            assert isinstance(result, RoomSendResponse), result
            return result.event_id

        for agent in settings.agents:
            topic = "probe-" + agent
            report = json.dumps(
                {
                    "action": "reply",
                    "summary": "FIRST_OK",
                    "details": "Isolated transport acceptance check.",
                    "to": [],
                }
            )
            await send(
                f"/topic {topic} @{agent} This is an isolated transport test. Do not use tools. Remember codeword ORCHID_926 for my next message. Return exactly this JSON: {report}"
            )
            await wait_for(
                lambda: (
                    store.db.execute(
                        "SELECT count(*) FROM jobs WHERE topic=? AND status='completed'",
                        (topic,),
                    ).fetchone()[0]
                    == 1
                )
            )
            session = store.session(topic, agent)
            await send(
                f"/topic {topic} @{agent} Do not use tools. Return action reply, summary equal to the codeword I asked you to remember, details explaining it is a memory check, to empty."
            )
            await wait_for(
                lambda: (
                    store.db.execute(
                        "SELECT count(*) FROM jobs WHERE topic=? AND status='completed'",
                        (topic,),
                    ).fetchone()[0]
                    == 2
                )
            )
            result = json.loads(
                store.db.execute(
                    "SELECT result FROM jobs WHERE topic=? ORDER BY rowid DESC LIMIT 1",
                    (topic,),
                ).fetchone()[0]
            )
            assert result["summary"] == "ORCHID_926", result
            assert store.session(topic, agent) == session
            print(
                "PASS Matrix -> session -> file -> Matrix", agent, session, flush=True
            )
        escalation = json.dumps(
            {
                "action": "escalate",
                "summary": "Choose A or B for this test",
                "details": "A: finish the test. B: stop. Recommendation: A.",
                "to": [],
            }
        )
        await send(
            f"/topic decision @claude-code Do not use tools. Isolated test: return exactly {escalation}"
        )
        await wait_for(
            lambda: (
                store.db.execute(
                    "SELECT count(*) FROM issues WHERE topic='decision'"
                ).fetchone()[0]
                == 1
            )
        )
        issue = store.db.execute(
            "SELECT id FROM issues WHERE topic='decision'"
        ).fetchone()[0]
        await wait_for(
            lambda: (
                store.db.execute(
                    "SELECT event_id FROM outbox WHERE id=?", ("issue-" + issue,)
                ).fetchone()[0]
                != ""
            )
        )
        answer = "Choose A. Do not use tools. Return action reply, summary DECISION_OK, details test complete, to empty."
        await send(f"/answer {issue} {answer}", rooms[1])
        await wait_for(
            lambda: (
                store.db.execute(
                    "SELECT count(*) FROM jobs WHERE topic='decision' AND status='completed'"
                ).fetchone()[0]
                == 2
            )
        )
        assert any(
            answer in p.read_text(encoding="utf-8")
            for p in project.rglob("decision-*.md")
        )
        await wait_for(lambda: not store.pending_notices())
        print(
            "PASS escalation -> explicit answer -> decision file -> resumed session",
            flush=True,
        )
        settings.database.with_suffix(".stop").write_text("stop")
        await asyncio.wait_for(service, 15)
        restarted = asyncio.create_task(run(settings))
        await wait_for(lambda: bool(store.get_meta("pid")), 15)
        before = store.db.execute("SELECT count(*) FROM jobs").fetchone()[0]
        await asyncio.sleep(2)
        assert store.db.execute("SELECT count(*) FROM jobs").fetchone()[0] == before
        settings.database.with_suffix(".stop").write_text("stop")
        await asyncio.wait_for(restarted, 15)
        print("PASS service restart without replay", flush=True)
        print("Evidence:", root.resolve(), flush=True)
    finally:
        if not service.done():
            settings.database.with_suffix(".stop").write_text("stop")
            await asyncio.wait_for(service, 15)
        store.close()
        await control.close()


if __name__ == "__main__":
    # Run from bridge with: python -m tests.live_coordination (tests is a package).
    if "--run" not in sys.argv:
        raise SystemExit("Pass --run to send test messages and invoke real models.")
    asyncio.run(main())
