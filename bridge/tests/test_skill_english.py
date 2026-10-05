"""Task english-release-14 and -15: the English kit text for both CLIs."""

import re
import unittest

from sessionchat import kit
from sessionchat.i18n import Catalogue

BROKER = "broker"
CLIENT = "client"
CATALOGUES = {
    BROKER: Catalogue("sessionchat", "broker_messages"),
    CLIENT: Catalogue("sessionchat", "client_messages"),
}
SLOT = {
    "agent": "claude-code",
    "registered": "22:34",
    "label": "refactoring",
    "state_word": "listening",
}
QUOTED = (
    ("=== AGENTSCHAT: incoming message ===", BROKER, "broker.envelope_open", {}),
    ("has been connected since", BROKER, "broker.slot_taken", SLOT),
    ("human", BROKER, "broker.envelope_kind_human", {}),
    ("agent", BROKER, "broker.envelope_kind_agent", {}),
    ("Unknown agent", BROKER, "broker.unknown_agent", {"agent": "terra"}),
    ("broker connection lost", CLIENT, "wait_broker_lost_title", {}),
)
BOUNDARIES = {"ru": "## Границы", "en": "## Boundaries"}
COMMAND = re.compile(r"^(\.\.\.|agentschat)(\s|$)")
SUBCOMMAND = ("login", "logout", "say", "ask", "status", "wait", "inbox")
INVOCATION = re.compile(r"^/chatlogin(\s|$)")
FLAG = re.compile(r"^--[a-z][a-z-]*")
PLACEHOLDER = re.compile(r"^<[A-Z]+>$")
SPAN = re.compile(r"`([^`\n]+)`")
ADDRESSED = ("@name", "@room", "@human ...")
PLAIN_NAMES = (
    "agentschat",
    "claude-code",
    "opencode",
    "config.yaml",
    "run_in_background: true",
    "terra",
    "helium",
    "user_id",
    "access_token",
    'delivery: "plugin"',
)
PRINTABLE_ASCII = re.compile(r"[\x20-\x7e\n]*")
CYRILLIC = re.compile("[Ѐ-ӿ]")
MENTIONS = re.compile(r"\bagentschat ([a-z][a-z-]*)")
MENTIONED_FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z-]*)")
FENCE = "```"
SHARED_COMMANDS = {"login", "say", "ask", "status"}


def skill_of(cli: str, lang: str) -> str:
    return (kit.KIT / lang / cli / "skills" / "chatlogin" / "SKILL.md").read_text(
        encoding="utf-8"
    )


def command_of(lang: str) -> str:
    return (kit.KIT / lang / "opencode" / "command" / "chatlogin.md").read_text(
        encoding="utf-8"
    )


def headings_of(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("## ")]


def rules_of(text: str, lang: str) -> list[str]:
    block = text.split(BOUNDARIES[lang], 1)[1].split("\n## ", 1)[0]
    return [line for line in block.splitlines() if line.startswith("- ")]


def bullets_of(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("- ")]


def mentions_of(text: str) -> tuple[set[str], set[str]]:
    body = "\n".join(line for line in text.splitlines() if not line.startswith(FENCE))
    return set(MENTIONS.findall(body)), set(MENTIONED_FLAG.findall(body))


def is_a_known_shape(span: str) -> bool:
    return bool(
        COMMAND.match(span)
        or INVOCATION.match(span)
        or FLAG.match(span)
        or PLACEHOLDER.match(span)
        or span in SUBCOMMAND
        or span in PLAIN_NAMES
        or span in ADDRESSED
    )


class EnglishSkillTests(unittest.TestCase):
    def setUp(self):
        self.text = skill_of("claude", "en")
        self.russian = skill_of("claude", "ru")

    def test_the_skill_has_no_cyrillic(self):
        self.assertIsNone(CYRILLIC.search(self.text), self.text)

    def test_the_skill_uses_ascii_punctuation_only(self):
        self.assertTrue(PRINTABLE_ASCII.fullmatch(self.text), self.text)

    def test_the_skill_declares_its_name_and_when_to_use_it(self):
        self.assertTrue(self.text.startswith("---\nname: chatlogin\n"))
        self.assertTrue(self.text.splitlines()[2].startswith("description: "))

    def test_the_skill_has_the_same_sections_as_the_russian_one(self):
        self.assertEqual(len(headings_of(self.text)), len(headings_of(self.russian)))

    def test_the_boundaries_section_has_as_many_rules_as_the_russian_one(self):
        self.assertEqual(
            len(rules_of(self.text, "en")), len(rules_of(self.russian, "ru"))
        )

    def test_the_english_skill_names_the_same_commands_and_flags_as_the_russian_one(
        self,
    ):
        self.assertEqual(mentions_of(self.text), mentions_of(self.russian))

    def test_the_shared_commands_of_the_project_are_in_the_english_skill(self):
        commands, _ = mentions_of(self.text)
        self.assertTrue(SHARED_COMMANDS <= commands, commands)

    def test_the_listener_command_is_in_the_english_skill(self):
        commands, _ = mentions_of(self.text)
        self.assertIn("wait", commands)


class EnglishOpenCodeSkillTests(unittest.TestCase):
    """Количественные проверки те же, что у скилла Claude Code, плюс те, что
    следуют из отличия OpenCode: своего listener нет и имя задаёт человек."""

    def setUp(self):
        self.text = skill_of("opencode", "en")
        self.russian = skill_of("opencode", "ru")

    def test_the_skill_has_no_cyrillic(self):
        self.assertIsNone(CYRILLIC.search(self.text), self.text)

    def test_the_skill_uses_ascii_punctuation_only(self):
        self.assertTrue(PRINTABLE_ASCII.fullmatch(self.text), self.text)

    def test_the_skill_declares_its_name_and_when_to_use_it(self):
        self.assertTrue(self.text.startswith("---\nname: chatlogin\n"))
        self.assertTrue(self.text.splitlines()[2].startswith("description: "))

    def test_the_skill_has_the_same_sections_as_the_russian_one(self):
        self.assertEqual(len(headings_of(self.text)), len(headings_of(self.russian)))

    def test_the_boundaries_section_has_as_many_rules_as_the_russian_one(self):
        self.assertEqual(
            len(rules_of(self.text, "en")), len(rules_of(self.russian, "ru"))
        )

    def test_the_english_skill_names_the_same_commands_and_flags_as_the_russian_one(
        self,
    ):
        self.assertEqual(mentions_of(self.text), mentions_of(self.russian))

    def test_the_shared_commands_of_the_project_are_in_the_english_skill(self):
        commands, _ = mentions_of(self.text)
        self.assertTrue(SHARED_COMMANDS <= commands, commands)

    def test_the_listener_command_is_not_started_because_the_plugin_holds_the_link(
        self,
    ):
        commands, _ = mentions_of(self.text)
        self.assertNotIn("wait", commands)
        self.assertIn("plugin", self.text)

    def test_the_name_the_human_gives_is_used_in_every_command(self):
        self.assertIn("that name is written `<NAME>`", self.text)
        self.assertIn("Use the same name in", self.text)

    def test_the_extra_rule_of_the_opencode_boundaries_is_kept(self):
        english = rules_of(self.text, "en")
        self.assertEqual(len(english), 7)
        self.assertTrue(english[-1].startswith("- Do not log in under another name"))


class EnglishCommandTests(unittest.TestCase):
    def setUp(self):
        self.text = command_of("en")
        self.russian = command_of("ru")

    def test_the_command_has_no_cyrillic_and_only_ascii_punctuation(self):
        self.assertIsNone(CYRILLIC.search(self.text), self.text)
        self.assertTrue(PRINTABLE_ASCII.fullmatch(self.text), self.text)

    def test_the_command_has_the_same_number_of_bullets_as_the_russian_one(self):
        self.assertEqual(len(bullets_of(self.text)), len(bullets_of(self.russian)))

    def test_the_command_keeps_the_argument_placeholder_of_the_cli(self):
        self.assertIn("$ARGUMENTS", self.text)

    def test_the_command_names_the_keys_and_the_default_it_refuses_to_reuse(self):
        for span in ("--agent", "--label", "opencode", "openai"):
            with self.subTest(span=span):
                self.assertIn(span, self.text)


class QuotedPhrasesTests(unittest.TestCase):
    """Правило проверки: цитата обязана быть подстрокой отрендеренного шаблона
    ключа, который ею владеет, а параметры ключа подставляются тестом. Поэтому
    цитата берётся из той части фразы, которая не меняется."""

    def rendered(self, owner: str, key: str, params: dict[str, object]) -> str:
        return CATALOGUES[owner].text("en", key, **params)

    def test_every_phrase_the_skills_quote_exists_in_the_english_catalogue(self):
        for phrase, owner, key, params in QUOTED:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.rendered(owner, key, params))

    def test_the_skills_quote_the_first_line_of_the_envelope_exactly(self):
        self.assertEqual(
            QUOTED[0][0], self.rendered(BROKER, "broker.envelope_open", {})
        )
        for cli in kit.CLIS:
            with self.subTest(cli=cli):
                self.assertIn(QUOTED[0][0], skill_of(cli, "en"))

    def test_both_skills_quote_the_refusal_that_holds_a_slot(self):
        for cli in kit.CLIS:
            with self.subTest(cli=cli):
                self.assertIn("has been connected since", skill_of(cli, "en"))

    def test_every_inline_span_is_a_command_a_flag_a_name_or_a_quoted_phrase(self):
        quoted = {phrase for phrase, _, _, _ in QUOTED}
        for cli in kit.CLIS:
            for span in sorted(set(SPAN.findall(skill_of(cli, "en")))):
                with self.subTest(cli=cli, span=span):
                    self.assertEqual(
                        not is_a_known_shape(span),
                        span in quoted,
                        f"{span} is neither a known shape nor a catalogue phrase",
                    )


if __name__ == "__main__":
    unittest.main()
