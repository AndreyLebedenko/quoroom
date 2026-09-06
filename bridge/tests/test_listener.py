"""Поведение listener — того самого процесса, выход которого будит сессию.

Здесь проверяется не транспорт, а два обещания из docs/SESSION_BRIDGE.md:
сообщение доводится до вывода и процесс завершается, а потеря брокера дольше
запаса тоже завершает процесс, вместо того чтобы изображать работу вслепую.
"""

import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import requests

from sessionchat import client
from sessionchat.protocol import DEAF_SECONDS, Envelope

MESSAGE = Envelope("@human:local", "человек", "проверка связи", "$e", "22:00:00", 0)


class Clock:
    """Часы, которые двигает только sleep: тест не ждёт реального времени."""

    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class ListenerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        patches = [
            patch.object(client, "credentials", return_value={"token": "tok"}),
            patch.object(client, "time", self.clock),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.args = type("Args", (), {"agent": "claude-code"})()

    def run_wait(self, side_effect):
        output = io.StringIO()
        with patch.object(client, "poll_once", side_effect=side_effect):
            with redirect_stdout(output):
                try:
                    client.do_wait(self.args)
                except SystemExit as exit_code:
                    return output.getvalue(), exit_code.code
        return output.getvalue(), 0

    def test_message_is_printed_and_the_process_ends(self):
        text, code = self.run_wait([MESSAGE])
        self.assertEqual(code, 0)
        self.assertIn("проверка связи", text)
        self.assertIn("AGENTSCHAT: входящее сообщение", text)
        self.assertIn("Подними новый listener ПЕРВЫМ действием", text)

    def test_empty_windows_do_not_end_the_process(self):
        text, code = self.run_wait([None, None, MESSAGE])
        self.assertEqual(code, 0)
        self.assertIn("проверка связи", text)

    def test_losing_the_broker_for_too_long_ends_the_process(self):
        outage = requests.ConnectionError("брокер не отвечает")
        text, code = self.run_wait([outage] * 200)
        self.assertEqual(code, 1)
        self.assertIn("связь с брокером потеряна", text)
        self.assertIn("подними listener заново", text.lower())
        # Умереть можно только после запаса, иначе моргание сети жгло бы ходы.
        self.assertGreaterEqual(self.clock.now - 1000.0, DEAF_SECONDS)

    def test_short_outage_is_survived_and_the_timer_resets(self):
        outage = requests.ConnectionError("моргнуло")
        text, code = self.run_wait([outage, outage, None, outage, MESSAGE])
        self.assertEqual(code, 0)
        self.assertIn("проверка связи", text)
        self.assertNotIn("связь с брокером потеряна", text)

    def test_revoked_session_ends_the_process_at_once(self):
        text, code = self.run_wait(
            [RuntimeError("сессия не подключена или токен неверен")]
        )
        self.assertEqual(code, 1)
        self.assertIn("listener остановлен", text)
        self.assertIn("токен неверен", text)
        self.assertEqual(self.clock.now, 1000.0)  # без выжидания запаса


if __name__ == "__main__":
    unittest.main()
