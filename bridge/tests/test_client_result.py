"""Task english-release-22: reading the result line the client prints."""

import unittest

from sessionchat import client_result


class TheResultLineTests(unittest.TestCase):
    def test_the_last_result_line_is_the_answer(self):
        printed = "\n".join(
            [
                client_result.line("login", False, code="not_logged_in"),
                "a table of sessions",
                client_result.line("status", True, language="ru"),
            ]
        )
        self.assertEqual(
            client_result.read(printed),
            {"command": "status", "ok": True, "language": "ru"},
        )

    def test_output_without_a_result_line_has_no_answer(self):
        self.assertIsNone(client_result.read("The broker answers at ...\n"))

    def test_a_result_line_that_is_not_json_has_no_answer(self):
        self.assertIsNone(client_result.read(f"{client_result.PREFIX} {{"))

    def test_a_result_line_holding_a_json_list_has_no_answer(self):
        self.assertIsNone(client_result.read(f"{client_result.PREFIX} [1]"))

    def test_a_word_beginning_like_the_prefix_is_not_a_result_line(self):
        self.assertIsNone(client_result.read("AGENTSCHAT-RESULTATION of the run"))
