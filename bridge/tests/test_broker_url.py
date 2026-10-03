"""Как клиент CLI выбирает адрес брокера.

Контракт: адрес целиком лежит в AGENTSCHAT_URL, локальный умолчательный,
нелокальный адрес никто не отвергает, а отказ называет тот адрес, который
клиент использует на самом деле. Умолчание одно и то же у CLI и у плагина
OpenCode, и равенство проверяется чтением исходника плагина.
"""

import io
import os
import re
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import requests

from sessionchat import client
from sessionchat.protocol import DEFAULT_PORT, DEFAULT_URL

BROKER_ENV = ("AGENTSCHAT_URL", "AGENTSCHAT_PORT")
PLUGIN_SOURCE = (
    Path(client.__file__).parent / "kit" / "opencode" / "plugins" / "agentschat.js"
)


def plugin_broker_default() -> str | None:
    """Адрес, на который плагин OpenCode смотрит без AGENTSCHAT_URL."""
    source = PLUGIN_SOURCE.read_text(encoding="utf-8")
    found = re.search(r'process\.env\.AGENTSCHAT_URL\s*\|\|\s*"([^"]*)"', source)
    return found.group(1) if found else None


@contextmanager
def broker_env(**values):
    """Окружение без переменных адреса, кроме переданных."""
    previous = {name: os.environ.get(name) for name in BROKER_ENV}
    for name in BROKER_ENV:
        os.environ.pop(name, None)
    os.environ.update(values)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def refused(run) -> tuple[str, str]:
    """Что команда напечатала, отказав из-за недоступного брокера."""
    output, error = io.StringIO(), io.StringIO()
    with redirect_stdout(output), redirect_stderr(error):
        try:
            run()
        except SystemExit:
            pass
        else:
            raise AssertionError(f"{run} не отказала")
    return output.getvalue(), error.getvalue()


class BrokerUrlTests(unittest.TestCase):
    def test_absent_variable_leaves_the_local_default(self):
        with broker_env():
            self.assertEqual(client.base(), DEFAULT_URL)

    def test_empty_variable_leaves_the_local_default(self):
        with broker_env(AGENTSCHAT_URL=""):
            self.assertEqual(client.base(), DEFAULT_URL)

    def test_the_local_default_names_the_broker_port(self):
        self.assertEqual(DEFAULT_URL, f"http://127.0.0.1:{DEFAULT_PORT}")

    def test_the_variable_gives_the_base_url(self):
        with broker_env(AGENTSCHAT_URL="http://broker.example:9911"):
            self.assertEqual(client.base(), "http://broker.example:9911")

    def test_the_removed_port_variable_no_longer_moves_the_address(self):
        with broker_env(AGENTSCHAT_PORT="9999"):
            self.assertEqual(client.base(), DEFAULT_URL)

    def status_path_for(self, url: str) -> str:
        with broker_env(AGENTSCHAT_URL=url):
            with patch.object(client.requests, "get") as get:
                get.return_value.text = "никого нет"
                with redirect_stdout(io.StringIO()):
                    client.do_status(type("Args", (), {})())
        return get.call_args.args[0]

    def test_a_trailing_slash_does_not_double_up_in_a_request_path(self):
        self.assertEqual(
            self.status_path_for("http://broker.example:9911/"),
            "http://broker.example:9911/status",
        )

    def test_a_non_local_url_is_accepted_as_is(self):
        self.assertEqual(
            self.status_path_for("https://chat.example.test/quoroom"),
            "https://chat.example.test/quoroom/status",
        )

    def test_the_address_is_read_per_call_and_not_cached(self):
        with broker_env(AGENTSCHAT_URL="http://first.example:9911"):
            first = client.base()
        with broker_env(AGENTSCHAT_URL="http://second.example:9912"):
            second = client.base()
        self.assertEqual(
            [first, second],
            ["http://first.example:9911", "http://second.example:9912"],
        )

    def test_the_default_is_the_same_url_the_plugin_falls_back_to(self):
        self.assertEqual(plugin_broker_default(), DEFAULT_URL)


class DiagnosticsNameTheAddressInUseTests(unittest.TestCase):
    def test_status_refusal_names_the_configured_address(self):
        with broker_env(AGENTSCHAT_URL="http://broker.example:9911"):
            with patch.object(
                client.requests,
                "get",
                side_effect=requests.ConnectionError("нет связи"),
            ):
                _, error = refused(lambda: client.do_status(type("Args", (), {})()))
        self.assertIn("http://broker.example:9911", error)

    def test_login_refusal_names_the_configured_address(self):
        with broker_env(AGENTSCHAT_URL="http://broker.example:9911"):
            with patch.object(
                client.requests,
                "post",
                side_effect=requests.ConnectionError("нет связи"),
            ):
                _, error = refused(
                    lambda: client.do_login(
                        type(
                            "Args",
                            (),
                            {"agent": "terra", "label": "", "reconnect": False},
                        )()
                    )
                )
        self.assertIn("http://broker.example:9911", error)

    def test_deaf_listener_notice_names_the_configured_address(self):
        output = io.StringIO()
        with broker_env(AGENTSCHAT_URL="http://broker.example:9911"):
            with (
                patch.object(client, "credentials", return_value={"token": "t"}),
                patch.object(
                    client,
                    "poll_once",
                    side_effect=requests.ConnectionError("нет связи"),
                ),
                patch.object(client, "DEAF_SECONDS", 0.0),
                redirect_stdout(output),
            ):
                with self.assertRaises(SystemExit):
                    client.do_wait(type("Args", (), {"agent": "terra"})())
        self.assertIn("http://broker.example:9911", output.getvalue())


if __name__ == "__main__":
    unittest.main()
