"""Карточка local-installers-02: Probe отличает ответ брокера от ошибки."""

import http.server
import os
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from sessionchat.installer.boundaries import (
    PASSWORD_MISMATCH,
    Probe,
    answers,
    ask_secret,
    describe,
    resolved,
    run_command,
)

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


class UntrustedProbeTests(unittest.TestCase):
    def refusing(self, error):
        class Refusing:
            def open(self, url, timeout=None):
                raise error

        return Refusing()

    def test_a_certificate_failure_marks_the_probe_untrusted(self):
        failure = ssl.SSLCertVerificationError(
            "certificate verify failed: self signed", 18
        )
        refusing = self.refusing(urllib.error.URLError(failure))
        with patch("urllib.request.build_opener", return_value=refusing):
            result = answers("https://agentschat.local/status")
        self.assertEqual(result, Probe(None, describe(failure), True))
        self.assertTrue(result.untrusted)

    def test_a_refused_connection_is_not_untrusted(self):
        refusing = self.refusing(
            urllib.error.URLError(ConnectionRefusedError("отказано в соединении"))
        )
        with patch("urllib.request.build_opener", return_value=refusing):
            result = answers("http://127.0.0.1:8770/status")
        self.assertFalse(result.untrusted)


class DescribeTests(unittest.TestCase):
    def test_a_certificate_failure_is_named_as_such(self):
        failure = ssl.SSLCertVerificationError("certificate verify failed", 18)
        self.assertIn("сертификат", describe(urllib.error.URLError(failure)))

    def test_a_refused_connection_keeps_its_reason(self):
        reason = ConnectionRefusedError("отказано в соединении")
        self.assertIn("отказано", describe(urllib.error.URLError(reason)))

    def test_a_plain_error_is_described_as_is(self):
        self.assertIn("таймаут", describe(TimeoutError("таймаут")))


def echo_child() -> list[str]:
    return [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"]


def stop(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        return
    os.kill(pid, signal.SIGKILL)


def alive(pid: int) -> bool:
    if os.name == "nt":
        found = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
        )
        return str(pid) in found.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class RunCommandTests(unittest.TestCase):
    def run_within(self, seconds: float, *args, **values):
        outcome: list = []
        worker = threading.Thread(
            target=lambda: outcome.append(run_command(*args, **values)),
            daemon=True,
        )
        worker.start()
        worker.join(seconds)
        self.assertFalse(
            worker.is_alive(), f"вызов не вернулся за {seconds}с, а потомок ждёт stdin"
        )
        return outcome[0]

    def test_a_child_receives_what_the_caller_typed(self):
        done = self.run_within(15, echo_child(), stdin="пароль-через-stdin")
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout, "пароль-через-stdin")

    def test_a_child_that_fails_keeps_its_code(self):
        done = run_command([sys.executable, "-c", "raise SystemExit(3)"], stdin=None)
        self.assertEqual(done.returncode, 3)

    def test_the_output_file_lands_where_the_caller_asked(self):
        with tempfile.TemporaryDirectory() as home:
            log = Path(home) / "nested" / "start.log"
            run_command(echo_child(), stdin="токен-не-в-argv", output=log)
            self.assertIn("токен-не-в-argv", log.read_text(encoding="utf-8"))

    def test_the_output_file_holds_stdout_and_stderr_together(self):
        with tempfile.TemporaryDirectory() as home:
            log = Path(home) / "start.log"
            run_command(
                [
                    sys.executable,
                    "-c",
                    "import sys; print('out'); print('err', file=sys.stderr)",
                ],
                output=log,
            )
            text = log.read_text(encoding="utf-8")
            self.assertIn("out", text)
            self.assertIn("err", text)

    def test_a_call_without_text_closes_the_childs_stdin(self):
        with patch("subprocess.run", wraps=subprocess.run) as started:
            run_command([sys.executable, "-c", "pass"])
        self.assertIs(started.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_a_call_with_text_pipes_exactly_that_text(self):
        with patch("subprocess.run", wraps=subprocess.run) as started:
            run_command([sys.executable, "-c", "pass"], stdin="пароль-через-pipe")
        self.assertIsNone(started.call_args.kwargs["stdin"])
        self.assertEqual(started.call_args.kwargs["input"], "пароль-через-pipe")

    def test_a_child_that_reads_stdin_without_it_gets_nothing_and_returns(self):
        with tempfile.TemporaryDirectory() as home:
            seen = Path(home) / "seen.txt"
            script = (
                "import pathlib, sys\n"
                f"pathlib.Path({str(seen)!r}).write_text(repr(sys.stdin.read()), encoding='utf-8')\n"
            )
            self.run_within(15, [sys.executable, "-c", script])
            self.assertEqual(seen.read_text(encoding="utf-8"), "''")

    def test_a_child_that_outlives_the_call_does_not_block_it(self):
        with tempfile.TemporaryDirectory() as home:
            marker = Path(home) / "late.txt"
            grandchild = Path(home) / "grandchild.py"
            grandchild.write_text(
                "import pathlib, sys, time\n"
                "time.sleep(30)\n"
                "pathlib.Path(sys.argv[1]).write_text('позже', encoding='utf-8')\n",
                encoding="utf-8",
            )
            child = Path(home) / "child.py"
            child.write_text(
                "import subprocess, sys\n"
                f"kid = subprocess.Popen([sys.executable, {str(grandchild)!r}, {str(marker)!r}],"
                " stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                "print(kid.pid)\n",
                encoding="utf-8",
            )
            log = Path(home) / "out.log"
            started = time.monotonic()
            done = self.run_within(15, [sys.executable, str(child)], output=log)
            elapsed = time.monotonic() - started
            self.assertEqual(done.returncode, 0)
            self.assertLess(elapsed, 15, "вызов ждал внука, который живёт 30 секунд")
            self.assertFalse(marker.is_file())
            pid = int(log.read_text(encoding="utf-8").split()[-1])
            stop(pid)
            for _ in range(30):
                if not alive(pid):
                    break
                time.sleep(0.1)
            self.assertFalse(alive(pid), "внук пережил тест")
            time.sleep(0.5)


class ResolvedTests(unittest.TestCase):
    def test_a_name_that_does_not_resolve_is_an_empty_answer(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror):
            self.assertEqual(resolved("no-such-host.invalid"), ())

    def test_an_address_the_system_gave_is_answered_as_is(self):
        with patch(
            "socket.getaddrinfo",
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
            ],
        ):
            self.assertEqual(resolved("localhost"), ("127.0.0.1",))


class AskSecretTests(unittest.TestCase):
    def typed(self, *answers: str):
        asked: list[str] = []

        def fake(prompt: str) -> str:
            asked.append(prompt)
            return answers[len(asked) - 1] if len(asked) <= len(answers) else ""

        return fake, asked

    def test_the_typed_password_is_returned_once(self):
        fake, asked = self.typed("одинаковый", "одинаковый")
        with patch("getpass.getpass", fake):
            self.assertEqual(ask_secret("Пароль: "), "одинаковый")
        self.assertEqual(len(asked), 2)

    def test_two_different_passwords_are_refused_by_name(self):
        fake, _ = self.typed("первый", "второй")
        with patch("getpass.getpass", fake):
            with self.assertRaises(ValueError) as caught:
                ask_secret("Пароль: ")
        self.assertEqual(str(caught.exception), PASSWORD_MISMATCH)


if __name__ == "__main__":
    unittest.main()
