import argparse
import asyncio
import logging
import os
from pathlib import Path

import yaml
from aiohttp import web

from .artifacts import Artifacts
from .engine import Engine
from .model import Notice, identifier
from .settings import Settings, mapping, string
from .store import Store
from .transport import Matrix

log = logging.getLogger("agentschat.coordination")


class InstanceLock:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("a+b")
        try:
            self.file.seek(0, 2)
            if self.file.tell() == 0:
                self.file.write(b"0")
                self.file.flush()
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.file.close()
            raise RuntimeError(
                "A coordination service already owns this database"
            ) from error

    def close(self) -> None:
        self.file.close()


def record_app(artifacts: Artifacts) -> web.Application:
    async def read(request: web.Request) -> web.Response:
        try:
            topic, record = (
                identifier(request.match_info["topic"]),
                identifier(request.match_info["record"]),
            )
            path = (
                artifacts.project
                / ".agent-comms"
                / "active"
                / ("ac-" + topic)
                / "bridge"
                / (record + ".md")
            )
            if (
                not path.resolve().is_relative_to(artifacts.project)
                or not path.is_file()
            ):
                raise web.HTTPNotFound()
            return web.Response(
                text=path.read_text(encoding="utf-8"),
                content_type="text/plain",
                charset="utf-8",
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        except ValueError as error:
            raise web.HTTPNotFound() from error

    app = web.Application()
    app.router.add_get("/records/{topic}/{record}", read)
    return app


async def workers(engine: Engine, agent: str) -> None:
    while True:
        if not await engine.process(agent):
            await asyncio.sleep(0.25)


async def receive(matrix: Matrix, store: Store, engine: Engine) -> None:
    while True:
        try:
            await matrix.poll(store, engine)
        except (OSError, asyncio.TimeoutError, RuntimeError) as error:
            log.error("Receiving paused: %s", error)
            # Delivery failures must not advance the cursor or discard jobs.
            store.notice(
                Notice(
                    "transport-failure",
                    engine.escalations,
                    next(iter(engine.runners)),
                    "Связь Matrix нарушена или история недоступна. Приём приостановлен; очередь сохранена. Проверьте журнал службы.",
                    True,
                )
            )
            await asyncio.sleep(5)


async def publish(matrix: Matrix, store: Store) -> None:
    while True:
        for notice in store.pending_notices():
            try:
                event_id = await matrix.send(notice)
            except (OSError, asyncio.TimeoutError, RuntimeError) as error:
                log.error("Publication pending (%s): %s", notice.id, error)
                await asyncio.sleep(5)
                break
            store.sent(notice.id, event_id)
        await asyncio.sleep(0.25)


async def watch_stop(path: Path) -> None:
    while not path.exists():
        await asyncio.sleep(0.25)


async def run(settings: Settings) -> None:
    lock = InstanceLock(settings.database.with_suffix(".lock"))
    store = Store(settings.database)
    matrix = Matrix(settings)
    artifacts = Artifacts(settings.project)
    engine = Engine(
        store,
        artifacts,
        dict(settings.agents),
        settings.general,
        settings.escalations,
        settings.humans,
        f"http://127.0.0.1:{settings.records_port}/records",
    )
    server = web.AppRunner(record_app(artifacts))
    stop = settings.database.with_suffix(".stop")
    tasks: list[asyncio.Task[None]] = []
    try:
        binding = (
            str(settings.project) + "|" + settings.general + "|" + settings.escalations
        )
        if store.get_meta("binding") not in {"", binding}:
            raise ValueError("This database belongs to another project or room pair")
        store.set_meta("binding", binding)
        stop.unlink(missing_ok=True)
        await matrix.setup()
        await server.setup()
        await web.TCPSite(server, "127.0.0.1", settings.records_port).start()
        engine.recover()
        engine.reconcile_answers()
        engine.publish_results()
        store.set_meta("pid", str(os.getpid()))
        log.info(
            "READY project=%s General=%s Escalations=%s",
            settings.project,
            settings.general,
            settings.escalations,
        )
        tasks = [
            asyncio.create_task(receive(matrix, store, engine)),
            asyncio.create_task(publish(matrix, store)),
            asyncio.create_task(watch_stop(stop)),
        ]
        tasks += [
            asyncio.create_task(workers(engine, name)) for name in settings.agents
        ]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                log.error("Service task stopped: %s", result)
        await server.cleanup()
        await matrix.close()
        store.set_meta("pid", "")
        store.close()
        lock.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Project agent coordination")
    parser.add_argument("--config", default="coordination.yaml")
    parser.add_argument("--action", choices=["run", "stop", "status"], default="run")
    args = parser.parse_args()
    path = Path(args.config).resolve()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if args.action == "run":
        asyncio.run(run(Settings.load(path)))
        return
    config = mapping(yaml.safe_load(path.read_text(encoding="utf-8")))
    database = (path.parent / string(config.get("state_file"))).resolve()
    if args.action == "stop":
        database.parent.mkdir(parents=True, exist_ok=True)
        database.with_suffix(".stop").write_text("stop", encoding="ascii")
        print("Stop requested; active CLI processes will be cancelled.")
    elif database.is_file():
        store = Store(database)
        try:
            print("PID:", store.get_meta("pid") or "stopped")
            for row in store.db.execute(
                "SELECT status,count(*) FROM jobs GROUP BY status"
            ):
                print(row[0], row[1])
            print(
                "Unresolved issues:",
                store.db.execute(
                    "SELECT count(*) FROM issues WHERE status!='resolved'"
                ).fetchone()[0],
            )
        finally:
            store.close()
    else:
        print("Not started yet")


if __name__ == "__main__":
    main()
