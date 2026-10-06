import asyncio
import logging
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import yaml
from aiohttp import ClientSession, web
from aiohttp.abc import AbstractAccessLogger
from aiohttp.test_utils import make_mocked_request
from aiohttp.web_log import AccessLogger as DefaultAccessLogger

from sessionchat import broker as broker_module
from sessionchat.access_log import AccessLogger
from tests.test_sessionchat import CONFIG, event


class AccessLoggerTests(unittest.TestCase):
    def test_diagnostics_keep_the_method_path_status_and_duration(self):
        logger = logging.getLogger("agentschat.test.access")
        writer = AccessLogger(logger, "")
        request = make_mocked_request("GET", "/wait?agent=claude-code&token=secret")
        with self.assertLogs(logger, level="INFO") as logs:
            writer.log(request, web.Response(status=200), 0.125)
        self.assertEqual(
            logs.records[0].getMessage(), "GET /wait status=200 duration=0.125s"
        )

    def test_query_parameters_and_request_headers_never_enter_the_record(self):
        logger = logging.getLogger("agentschat.test.access")
        writer = AccessLogger(logger, "")
        for endpoint in ("wait", "inbox"):
            for status in (200, 409):
                with self.subTest(endpoint=endpoint, status=status):
                    request = make_mocked_request(
                        "GET",
                        f"/{endpoint}?token=query-secret&token=another-secret&agent=a",
                        headers={
                            "Referer": "http://localhost/?token=referrer-secret",
                            "Authorization": "Bearer header-secret",
                            "User-Agent": "agent-secret",
                        },
                    )
                    with self.assertLogs(logger, level="INFO") as logs:
                        writer.log(request, web.Response(status=status), 1.0)
                    record = repr(logs.records[0].__dict__)
                    for secret in (
                        "query-secret",
                        "another-secret",
                        "referrer-secret",
                        "header-secret",
                        "agent-secret",
                    ):
                        self.assertNotIn(secret, record)
                    self.assertNotIn("token=", record)

    def test_response_bodies_do_not_enter_the_record(self):
        logger = logging.getLogger("agentschat.test.access")
        writer = AccessLogger(logger, "")
        request = make_mocked_request(
            "POST", "/login", headers={"Content-Type": "application/json"}
        )
        with self.assertLogs(logger, level="INFO") as logs:
            writer.log(request, web.Response(status=200, text="response-secret"), 0.0)
        self.assertEqual(
            logs.records[0].getMessage(), "POST /login status=200 duration=0.000s"
        )
        self.assertNotIn("response-secret", repr(logs.records[0].__dict__))


class BrokerAccessLogStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_startup_logs_successful_and_refused_authenticated_gets_without_tokens(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            config = {**CONFIG, "sessionchat_port": 0}
            config_path = Path(directory) / "config.yaml"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
            broker = broker_module.Broker(config, Path(directory) / "agentschat.db")
            runners: list[web.AppRunner] = []
            original_runner = web.AppRunner
            ready = asyncio.Event()
            stop = asyncio.Event()

            def make_runner(
                app: web.Application,
                *,
                access_log_class: type[AbstractAccessLogger] = DefaultAccessLogger,
            ) -> web.AppRunner:
                runner = original_runner(app, access_log_class=access_log_class)
                runners.append(runner)
                return runner

            async def hold_sync() -> None:
                ready.set()
                await stop.wait()

            with (
                patch.object(broker_module, "Broker", return_value=broker),
                patch.object(broker, "join_all", AsyncMock()),
                patch.object(broker, "sync_forever", hold_sync),
                patch.object(web, "AppRunner", make_runner),
            ):
                task = asyncio.create_task(broker_module.run(config_path))
                try:
                    await asyncio.wait_for(ready.wait(), timeout=5)
                    port = runners[0].addresses[0][1]
                    base = f"http://127.0.0.1:{port}"
                    with self.assertLogs("aiohttp.access", level="INFO") as logs:
                        async with ClientSession() as client:
                            login = await client.post(
                                f"{base}/login", json={"agent": "claude-code"}
                            )
                            token = (await login.json())["token"]
                            for endpoint in ("inbox", "wait"):
                                for supplied, expected in (
                                    (token, 200),
                                    ("bad-token", 409),
                                ):
                                    with self.subTest(
                                        endpoint=endpoint, status=expected
                                    ):
                                        if endpoint == "wait" and expected == 200:
                                            await broker.on_message(
                                                types.SimpleNamespace(
                                                    room_id=config["room_id"]
                                                ),
                                                event("@claude-code test delivery"),
                                            )
                                        before = len(logs.records)
                                        response = await client.get(
                                            f"{base}/{endpoint}",
                                            params={
                                                "agent": "claude-code",
                                                "token": supplied,
                                            },
                                            headers={
                                                "Referer": f"{base}/?token={supplied}"
                                            },
                                        )
                                        await response.read()
                                        self.assertEqual(response.status, expected)
                                        recorded = "\n".join(
                                            record.getMessage()
                                            for record in logs.records[before:]
                                        )
                                        self.assertNotIn(supplied, recorded)
                                        self.assertNotIn("token=", recorded)
                                        self.assertNotIn("agent=", recorded)
                                        self.assertIn(f"GET /{endpoint}", recorded)
                                        self.assertIn(f"status={expected}", recorded)
                finally:
                    stop.set()
                    await asyncio.wait_for(task, timeout=5)


if __name__ == "__main__":
    unittest.main()
