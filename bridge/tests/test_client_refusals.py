"""Task english-release-03: the client shows the broker's message and trusts its code."""

import io
import json
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

import requests

from sessionchat import client


def answer(status: int, body: bytes, content_type: str = "application/json"):
    response = requests.Response()
    response.status_code = status
    response._content = body
    response.headers["Content-Type"] = content_type
    response.encoding = "utf-8"
    return response


def refusal(status: int, code: str, message: str, params: dict | None = None):
    body = {"code": code, "message": message, "params": params or {}}
    return answer(status, json.dumps(body, ensure_ascii=False).encode("utf-8"))


class ExplainTests(unittest.TestCase):
    def test_a_refusal_is_shown_as_its_message(self):
        response = refusal(409, "slot_taken", "agent claude-code is taken")
        self.assertEqual(client.explain(response), "agent claude-code is taken")

    def test_a_russian_message_is_shown_as_it_is(self):
        response = refusal(404, "unknown_agent", "неизвестный агент: nobody")
        self.assertEqual(client.explain(response), "неизвестный агент: nobody")

    def test_the_code_and_the_params_are_not_part_of_what_is_shown(self):
        response = refusal(409, "slot_taken", "sentence", {"agent": "claude-code"})
        shown = client.explain(response)
        self.assertNotIn("slot_taken", shown)
        self.assertNotIn("claude-code", shown)

    def test_what_is_shown_does_not_depend_on_the_code(self):
        first = refusal(409, "one_code", "the same words")
        second = refusal(409, "another_code", "the same words")
        self.assertEqual(client.explain(first), client.explain(second))

    def test_a_plain_text_body_is_shown_as_it_is(self):
        response = answer(409, "  not json at all\n".encode(), "text/plain")
        self.assertEqual(client.explain(response), "not json at all")

    def test_an_empty_body_falls_back_to_the_status(self):
        self.assertEqual(client.explain(answer(502, b"", "text/plain")), "HTTP 502")

    def test_json_without_a_message_is_shown_as_the_body_text(self):
        response = answer(500, b'{"detail": "boom"}')
        self.assertEqual(client.explain(response), '{"detail": "boom"}')

    def test_a_json_body_that_is_not_an_object_is_shown_as_the_body_text(self):
        response = answer(500, b'["boom"]')
        self.assertEqual(client.explain(response), '["boom"]')

    def test_a_blank_message_falls_back_to_the_body_text(self):
        response = refusal(409, "code", "   ")
        self.assertIn("code", client.explain(response))


class LoginRefusalTests(unittest.TestCase):
    def run_login(self, response: requests.Response) -> str:
        arguments = client.argparse.Namespace(
            agent="claude-code", label="x", reconnect=False
        )
        stderr = io.StringIO()
        with (
            patch.object(client.requests, "post", return_value=response),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as stopped,
        ):
            client.do_login(arguments)
        self.assertEqual(stopped.exception.code, 1)
        return stderr.getvalue()

    def test_login_prints_the_message_of_a_refusal(self):
        shown = self.run_login(refusal(409, "slot_taken", "taken, ask the human"))
        self.assertEqual(shown, "AGENTSCHAT: taken, ask the human\n")

    def test_login_does_not_print_the_json_envelope(self):
        shown = self.run_login(refusal(409, "slot_taken", "taken", {"agent": "a"}))
        self.assertNotIn("{", shown)


class WaitRefusalTests(unittest.TestCase):
    def test_a_refused_poll_raises_with_the_message(self):
        response = refusal(409, "session_not_registered", "not connected")
        with patch.object(client.requests, "get", return_value=response):
            with self.assertRaises(RuntimeError) as raised:
                client.poll_once("claude-code", "token")
        self.assertEqual(str(raised.exception), "not connected")
