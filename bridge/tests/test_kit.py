import re
import unittest
from importlib.resources import files
from importlib.resources.abc import Traversable

from sessionchat import kit

EXPECTED_KIT_FILES = {
    "common/opencode/plugins/agentschat.js",
    "ru/claude/skills/chatlogin/SKILL.md",
    "ru/opencode/command/chatlogin.md",
    "ru/opencode/skills/chatlogin/SKILL.md",
}
BASE_DIGESTS = {
    "common/opencode/plugins/agentschat.js": (
        "e7174ac13507160eaab5e67765b8eb3e26c7dfef19502b81835e9cf8c9b3b323"
    ),
    "ru/claude/skills/chatlogin/SKILL.md": (
        "b1636a875c799a8330ffc6bb723acd092e73ff4bf9e369f2131c49998e3ac2d9"
    ),
    "ru/opencode/command/chatlogin.md": (
        "565d7bf44ee097c599fa640c97147218bc9f3b049bd279eb3a825bda5885673b"
    ),
    "ru/opencode/skills/chatlogin/SKILL.md": (
        "cacf11d43d4ca71c86678b113167a758adc935040feb50b57d1cfb39b5a18849"
    ),
}
QUOROOM_REPOSITORY_PATHS = (
    "bridge\\agentschat",
    "bridge/agentschat",
    ".opencode/plugins",
)


def kit_root() -> Traversable:
    return files("sessionchat") / "kit"


def variants() -> list[str]:
    return sorted(
        child.name
        for child in kit_root().iterdir()
        if child.is_dir() and child.name != kit.COMMON
    )


def files_under(node: Traversable, prefix: str = "") -> dict[str, Traversable]:
    found = {}
    for child in node.iterdir():
        relative = f"{prefix}{child.name}"
        if child.is_dir():
            found.update(files_under(child, f"{relative}/"))
        else:
            found[relative] = child
    return found


class KitContentsTests(unittest.TestCase):
    def test_the_kit_holds_exactly_the_files_each_cli_loads(self):
        self.assertEqual(set(files_under(kit_root())), EXPECTED_KIT_FILES)

    def test_each_expected_kit_file_is_reachable_as_package_data(self):
        for relative in sorted(EXPECTED_KIT_FILES):
            with self.subTest(file=relative):
                resource = kit_root().joinpath(*relative.split("/"))
                self.assertTrue(resource.is_file())
                self.assertTrue(resource.read_text(encoding="utf-8").strip())

    def test_the_moved_files_are_the_bytes_of_the_layout_before_the_move(self):
        found = files_under(kit_root())
        for relative, digest in sorted(BASE_DIGESTS.items()):
            with self.subTest(file=relative):
                self.assertEqual(kit.digest(found[relative].read_bytes()), digest)

    def test_the_plugin_is_the_one_file_every_language_shares(self):
        self.assertEqual(
            sorted(
                relative
                for relative in EXPECTED_KIT_FILES
                if relative.startswith(f"{kit.COMMON}/")
            ),
            ["common/opencode/plugins/agentschat.js"],
        )

    def test_every_variant_directory_holds_the_same_relative_paths_for_both_clis(self):
        for variant in sorted(variants()):
            with self.subTest(variant=variant):
                self.assertEqual(
                    {
                        relative.split("/", 1)[1]
                        for relative in EXPECTED_KIT_FILES
                        if relative.startswith(f"{variant}/")
                    },
                    {
                        "claude/skills/chatlogin/SKILL.md",
                        "opencode/command/chatlogin.md",
                        "opencode/skills/chatlogin/SKILL.md",
                    },
                )


class KitNamesNoQuoroomRepositoryPathTests(unittest.TestCase):
    def test_no_kit_file_mentions_a_path_inside_the_quoroom_repository(self):
        for relative, resource in sorted(files_under(kit_root()).items()):
            text = resource.read_text(encoding="utf-8")
            for path in QUOROOM_REPOSITORY_PATHS:
                with self.subTest(file=relative, path=path):
                    self.assertNotIn(path, text)


class SkillAgreementTests(unittest.TestCase):
    """Правило извлечения: подкоманда - токен сразу за словом `agentschat`,
    ключи вида `--flag` берутся из всего текста, кроме строк-ограждений.
    Правило механическое и одно на все языки и оба CLI, поэтому расхождение
    видно сразу."""

    COMMAND = re.compile(r"\bagentschat ([a-z][a-z-]*)")
    FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z-]*)")
    FENCE = "```"
    SHARED_COMMANDS = {"login", "say", "ask", "status"}

    def skill(self, lang: str, cli: str) -> str:
        resource = kit_root().joinpath(lang, cli, "skills", "chatlogin", "SKILL.md")
        return resource.read_text(encoding="utf-8")

    def mentions(self, text: str) -> tuple[set[str], set[str]]:
        body = "\n".join(
            line for line in text.splitlines() if not line.startswith(self.FENCE)
        )
        return set(self.COMMAND.findall(body)), set(self.FLAG.findall(body))

    def skills(self) -> dict[tuple[str, str], str]:
        return {
            (lang, cli): self.skill(lang, cli)
            for lang in variants()
            for cli in kit.CLIS
        }

    def test_the_languages_of_one_cli_name_the_same_commands_and_flags(self):
        skills = self.skills()
        for cli in kit.CLIS:
            said = [self.mentions(skills[(lang, cli)]) for lang in variants()]
            with self.subTest(cli=cli):
                self.assertEqual(said[1:], said[:-1])

    def test_every_language_and_cli_offers_the_commands_the_project_agrees_on(self):
        for (lang, cli), text in sorted(self.skills().items()):
            commands, _ = self.mentions(text)
            with self.subTest(lang=lang, cli=cli):
                self.assertTrue(self.SHARED_COMMANDS <= commands, commands)

    def test_the_listener_is_a_claude_command_and_lives_in_the_plugin_for_opencode(
        self,
    ):
        skills = self.skills()
        for lang in variants():
            with self.subTest(lang=lang):
                self.assertIn("wait", self.mentions(skills[(lang, "claude")])[0])
                self.assertNotIn("wait", self.mentions(skills[(lang, "opencode")])[0])


class TemporaryRussianOnlyVariantTests(unittest.TestCase):
    """Откат на ru и код kit_variant_missing удалит задача 15 вместе с
    английскими файлами; до неё вариант один."""

    def test_only_the_russian_variant_ships(self):
        self.assertEqual(variants(), [kit.FALLBACK_VARIANT])

    def test_the_language_that_has_a_variant_is_its_own(self):
        self.assertEqual(kit.variant_of(kit.FALLBACK_VARIANT)[1], kit.CODE_NONE)

    def test_a_language_without_a_variant_falls_back_and_says_so(self):
        root, code = kit.variant_of("en")
        self.assertEqual(code, kit.VARIANT_MISSING)
        self.assertEqual(root.name, kit.FALLBACK_VARIANT)

    def test_a_substituted_variant_is_not_a_refusal(self):
        self.assertNotIn(kit.VARIANT_MISSING, kit.REFUSALS)


if __name__ == "__main__":
    unittest.main()
