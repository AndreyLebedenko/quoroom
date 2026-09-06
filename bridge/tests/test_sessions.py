import unittest

from coordination.cli import AgentCLI, parse_result


class SessionTests(unittest.TestCase):
    def test_claude_keeps_session_id(self):
        result = parse_result(
            "claude-code", '{"session_id":"c1","result":"hello","is_error":false}'
        )
        self.assertEqual((result.session, result.text), ("c1", "hello"))

    def test_codex_uses_last_agent_message(self):
        text = "\n".join(
            [
                '{"type":"thread.started","thread_id":"c2"}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"working"}}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"done"}}',
                '{"type":"turn.completed"}',
            ]
        )
        result = parse_result("codex", text)
        self.assertEqual((result.session, result.text), ("c2", "done"))

    def test_opencode_combines_text_parts(self):
        text = "\n".join(
            [
                '{"type":"text","sessionID":"s1","part":{"text":"hello "}}',
                '{"type":"text","sessionID":"s1","part":{"text":"world"}}',
                '{"type":"step_finish","sessionID":"s1","part":{"reason":"stop"}}',
            ]
        )
        result = parse_result("opencode", text)
        self.assertEqual((result.session, result.text), ("s1", "hello world"))

    def test_provider_error_is_not_a_successful_reply(self):
        for provider, text in [
            ("claude-code", '{"session_id":"c1","result":"error","is_error":true}'),
            ("codex", '{"type":"error","message":"failed"}'),
            ("opencode", '{"type":"error","error":{"name":"APIError"}}'),
        ]:
            with self.subTest(provider=provider), self.assertRaises(ValueError):
                parse_result(provider, text)

    def test_resume_names_exact_session(self):
        for name in ("claude-code", "codex", "opencode"):
            command = AgentCLI(
                name, "agent.exe", "model" if name == "opencode" else ""
            ).command("exact-session")
            self.assertIn("exact-session", command)
            self.assertNotIn("--last", command)
            self.assertNotIn("--continue", command)
