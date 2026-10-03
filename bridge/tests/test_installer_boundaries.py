"""Карточка local-installers-02: Probe отличает ответ брокера от ошибки."""

import http.server
import os
import ssl
import threading
import unittest
import urllib.error
from unittest.mock import patch

from sessionchat.installer.boundaries import Probe, answers, describe

MISSING = "/missing"


class Quiet(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(404 if self.path == MISSING else 200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args) -> None:
        return None


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def test_an_answer_carries_its_status(self):
        self.assertEqual(answers(self.url), Probe(200, None))

    def test_an_error_status_is_still_an_answer(self):
        self.assertEqual(answers(f"{self.url}{MISSING}"), Probe(404, None))

    def test_a_refused_connection_is_an_error_not_a_status(self):
        closed = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        port = closed.server_address[1]
        closed.server_close()
        result = answers(f"http://127.0.0.1:{port}", timeout=1.0)
        self.assertIsNone(result.status)
        self.assertIsNotNone(result.error)

    def test_the_probe_ignores_the_environment_proxy(self):
        with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1"}):
            self.assertEqual(answers(self.url), Probe(200, None))


class DescribeTests(unittest.TestCase):
    def test_a_certificate_failure_is_named_as_such(self):
        failure = ssl.SSLCertVerificationError("certificate verify failed", 18)
        self.assertIn("сертификат", describe(urllib.error.URLError(failure)))

    def test_a_refused_connection_keeps_its_reason(self):
        reason = ConnectionRefusedError("отказано в соединении")
        self.assertIn("отказано", describe(urllib.error.URLError(reason)))

    def test_a_plain_error_is_described_as_is(self):
        self.assertIn("таймаут", describe(TimeoutError("таймаут")))


if __name__ == "__main__":
    unittest.main()
