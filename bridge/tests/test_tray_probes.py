"""Task tray-02: the two probes behind their injectable seams."""

import http.client
import http.server
import json
import socket
import threading
import unittest
from unittest import mock

from quoroomtray import probes, settings
from quoroomtray.broker_status import parse_sessions
from quoroomtray.observation import SessionLine
from quoroomtray.probes import StandProbes
from tests.tray_fakes import FakeConnect, FakeFetch


def status_body(*sessions: dict) -> bytes:
    return json.dumps({"language": "en", "sessions": list(sessions)}).encode("utf-8")


def session(agent: str, state: str, line: str) -> dict:
    return {"agent": agent, "state": state, "line": line, "quiet": 3}


class StackProbeTests(unittest.TestCase):
    def test_it_connects_to_port_443_on_the_loopback_with_a_short_timeout(self):
        connect = FakeConnect()

        StandProbes(connect=connect, fetch=FakeFetch(b"{}")).stack_answers()

        self.assertEqual(
            [(("127.0.0.1", 443), settings.PORT_TIMEOUT_SECONDS)], connect.calls
        )

    def test_a_successful_connection_means_the_stack_answers(self):
        probes_ = StandProbes(connect=FakeConnect(), fetch=FakeFetch(b"{}"))

        self.assertTrue(probes_.stack_answers())

    def test_the_connection_is_closed_after_the_probe(self):
        connect = FakeConnect()

        StandProbes(connect=connect, fetch=FakeFetch(b"{}")).stack_answers()

        self.assertTrue(all(opened.closed for opened in connect.sockets))

    def test_a_refused_connection_means_the_stack_is_silent(self):
        connect = FakeConnect(ConnectionRefusedError())

        self.assertFalse(StandProbes(connect=connect).stack_answers())

    def test_a_timed_out_connection_means_the_stack_is_silent(self):
        connect = FakeConnect(TimeoutError())

        self.assertFalse(StandProbes(connect=connect).stack_answers())


class BrokerProbeTests(unittest.TestCase):
    def test_it_asks_the_broker_status_url_with_a_short_timeout(self):
        fetch = FakeFetch(status_body())

        StandProbes(connect=FakeConnect(), fetch=fetch).broker_sessions()

        self.assertEqual(
            [("http://127.0.0.1:8770/status", settings.STATUS_TIMEOUT_SECONDS)],
            fetch.calls,
        )

    def test_the_status_port_is_the_one_start_ps1_waits_for(self):
        script = settings.START_SCRIPT.read_text(encoding="utf-8-sig")

        self.assertIn("$brokerPort = 8770", script)
        self.assertIn(":8770/", settings.BROKER_STATUS_URL)

    def test_the_sessions_are_returned_with_the_lines_exactly_as_the_broker_wrote_them(
        self,
    ):
        body = status_body(
            session("claude", "online", "claude     online  quiet 3s"),
            session("opencode", "not connected", "opencode   not connected"),
        )
        probes_ = StandProbes(connect=FakeConnect(), fetch=FakeFetch(body))

        self.assertEqual(
            (
                SessionLine("claude", "online", "claude     online  quiet 3s"),
                SessionLine("opencode", "not connected", "opencode   not connected"),
            ),
            probes_.broker_sessions(),
        )

    def test_a_broker_without_sessions_answers_with_an_empty_tuple(self):
        probes_ = StandProbes(connect=FakeConnect(), fetch=FakeFetch(status_body()))

        self.assertEqual((), probes_.broker_sessions())

    def test_a_connection_error_means_the_broker_is_silent(self):
        fetch = FakeFetch(failure=ConnectionRefusedError())

        self.assertIsNone(StandProbes(fetch=fetch).broker_sessions())

    def test_a_timeout_means_the_broker_is_silent(self):
        fetch = FakeFetch(failure=TimeoutError())

        self.assertIsNone(StandProbes(fetch=fetch).broker_sessions())

    def test_a_dropped_http_connection_means_the_broker_is_silent(self):
        fetch = FakeFetch(failure=http.client.RemoteDisconnected())

        self.assertIsNone(StandProbes(fetch=fetch).broker_sessions())


class StatusParsingTests(unittest.TestCase):
    def test_a_body_that_is_not_json_is_no_answer(self):
        self.assertIsNone(parse_sessions(b"<html>not a broker</html>"))

    def test_json_that_is_not_an_object_is_no_answer(self):
        self.assertIsNone(parse_sessions(b"[1, 2, 3]"))

    def test_an_object_without_a_sessions_list_is_no_answer(self):
        self.assertIsNone(parse_sessions(b'{"language": "en"}'))

    def test_a_sessions_value_that_is_not_a_list_is_no_answer(self):
        self.assertIsNone(parse_sessions(b'{"sessions": "none"}'))

    def test_an_entry_missing_its_line_is_left_out_and_the_others_are_kept(self):
        body = json.dumps(
            {
                "sessions": [
                    {"agent": "claude", "state": "online"},
                    session("opencode", "online", "opencode online"),
                    "garbage",
                ]
            }
        ).encode("utf-8")

        self.assertEqual(
            (SessionLine("opencode", "online", "opencode online"),),
            parse_sessions(body),
        )

    def test_russian_lines_survive_unchanged(self):
        line = "claude     подключён"
        body = json.dumps({"sessions": [session("claude", "online", line)]}).encode()

        self.assertEqual(line, parse_sessions(body)[0].line)


class ObservationTests(unittest.TestCase):
    def test_it_combines_both_probes_into_one_observation(self):
        probes_ = StandProbes(
            connect=FakeConnect(),
            fetch=FakeFetch(status_body(session("claude", "online", "claude online"))),
        )

        observation = probes_.observe()

        self.assertTrue(observation.stack_answers)
        self.assertTrue(observation.broker_answers)
        self.assertEqual(
            (SessionLine("claude", "online", "claude online"),), observation.sessions
        )

    def test_with_both_silent_neither_answers(self):
        probes_ = StandProbes(
            connect=FakeConnect(ConnectionRefusedError()),
            fetch=FakeFetch(failure=ConnectionRefusedError()),
        )

        observation = probes_.observe()

        self.assertFalse(observation.stack_answers)
        self.assertFalse(observation.broker_answers)

    def test_the_stack_can_answer_while_the_broker_is_silent(self):
        probes_ = StandProbes(
            connect=FakeConnect(), fetch=FakeFetch(failure=ConnectionRefusedError())
        )

        observation = probes_.observe()

        self.assertTrue(observation.stack_answers)
        self.assertFalse(observation.broker_answers)

    def test_the_broker_can_answer_while_the_stack_is_silent(self):
        probes_ = StandProbes(
            connect=FakeConnect(ConnectionRefusedError()),
            fetch=FakeFetch(status_body()),
        )

        observation = probes_.observe()

        self.assertFalse(observation.stack_answers)
        self.assertTrue(observation.broker_answers)


class StatusHandler(http.server.BaseHTTPRequestHandler):
    body = b""
    status = 200

    def do_GET(self):
        self.send_response(self.status)
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *arguments):
        pass


class DefaultTransportsOnTheLoopbackTests(unittest.TestCase):
    def serve(self, body: bytes, status: int = 200) -> str:
        handler = type("Handler", (StatusHandler,), {"body": body, "status": status})
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}/status"

    def test_the_default_fetch_reads_the_body_of_a_local_answer(self):
        url = self.serve(b'{"sessions": []}')

        self.assertEqual(b'{"sessions": []}', probes.fetch_body(url, 2.0))

    def test_the_default_fetch_ignores_a_configured_proxy(self):
        url = self.serve(b'{"sessions": []}')

        with mock.patch.dict("os.environ", {"HTTP_PROXY": "http://127.0.0.1:9"}):
            self.assertEqual(b'{"sessions": []}', probes.fetch_body(url, 2.0))

    def test_a_server_error_from_the_default_fetch_makes_the_broker_silent(self):
        url = self.serve(b"oops", status=500)
        with mock.patch.object(settings, "BROKER_STATUS_URL", url):
            self.assertIsNone(StandProbes().broker_sessions())

    def test_the_default_connect_reaches_a_listening_port(self):
        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with mock.patch.object(settings, "STACK_PORT", listener.getsockname()[1]):
            self.assertTrue(StandProbes().stack_answers())

    def test_the_default_connect_finds_a_closed_port_silent(self):
        holder = socket.socket()
        holder.bind(("127.0.0.1", 0))
        port = holder.getsockname()[1]
        holder.close()
        with mock.patch.object(settings, "STACK_PORT", port):
            self.assertFalse(StandProbes().stack_answers())


if __name__ == "__main__":
    unittest.main()
