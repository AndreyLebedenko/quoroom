import re
import unittest
from importlib.resources import files
from importlib.resources.abc import Traversable

from sessionchat import kit

EXPECTED_KIT_FILES = {
    "common/dsh/plugin/cordis.patch.yml",
    "common/dsh/plugin/package.json",
    "common/dsh/plugin/src/index.js",
    "common/opencode/plugins/agentschat.js",
    "en/claude/skills/chatlogin/SKILL.md",
    "en/dsh/skills/chatlogin/SKILL.md",
    "en/opencode/command/chatlogin.md",
    "en/opencode/skills/chatlogin/SKILL.md",
    "ru/claude/skills/chatlogin/SKILL.md",
    "ru/dsh/skills/chatlogin/SKILL.md",
    "ru/opencode/command/chatlogin.md",
    "ru/opencode/skills/chatlogin/SKILL.md",
}
BASE_DIGESTS = {
    "common/opencode/plugins/agentschat.js": (
        "8b41519313868e4fd79eac166de5c493af7ebb520eb6c9ec66dcf865d952a948"
    ),
    "ru/claude/skills/chatlogin/SKILL.md": (
        "49f9735c91fad908b07880635d99197cfaf24a1fb39bbcfab9e515ec12ff237c"
    ),
    "ru/opencode/command/chatlogin.md": (
        "7df809a5ce73db6cbe4c0515d6fe8bae28837b50e15b050d18c82620d8976176"
    ),
    "ru/opencode/skills/chatlogin/SKILL.md": (
        "547be19a4e7cb374249207cc8cf048c307c83203cafcb0048c34d8ad9c26dd13"
    ),
}
QUOROOM_REPOSITORY_PATHS = (
    "bridge\\agentschat",
    "bridge/agentschat",
    ".opencode/plugins",
)


def with_unix_line_ends(content: bytes) -> bytes:
    return content.replace(b"\r\n", b"\n")


def kit_root() -> Traversable:
    return files("sessionchat") / "kit"


def variants(root: Traversable | None = None) -> list[str]:
    return sorted(
        child.name
        for child in (root or kit_root()).iterdir()
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
                self.assertEqual(
                    kit.digest(with_unix_line_ends(found[relative].read_bytes())),
                    digest,
                )

    def test_the_digests_do_not_depend_on_the_line_ends_of_the_checkout(self):
        windows_checkout = b"first\r\nsecond\r\n"
        unix_checkout = b"first\nsecond\n"
        self.assertEqual(
            kit.digest(with_unix_line_ends(windows_checkout)),
            kit.digest(with_unix_line_ends(unix_checkout)),
        )

    def test_the_plugins_are_the_only_files_every_language_shares(self):
        self.assertEqual(
            sorted(
                relative
                for relative in EXPECTED_KIT_FILES
                if relative.startswith(f"{kit.COMMON}/")
            ),
            [
                "common/dsh/plugin/cordis.patch.yml",
                "common/dsh/plugin/package.json",
                "common/dsh/plugin/src/index.js",
                "common/opencode/plugins/agentschat.js",
            ],
        )


class KitNamesNoQuoroomRepositoryPathTests(unittest.TestCase):
    def test_no_kit_file_mentions_a_path_inside_the_quoroom_repository(self):
        for relative, resource in sorted(files_under(kit_root()).items()):
            text = resource.read_text(encoding="utf-8")
            for path in QUOROOM_REPOSITORY_PATHS:
                with self.subTest(file=relative, path=path):
                    self.assertNotIn(path, text)


class SkillAgreementTests(unittest.TestCase):
    COMMAND = re.compile(r"\bagentschat ([a-z][a-z-]*)")
    FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z-]*)")
    INLINE_CODE = re.compile(r"`([^`\n]+)`")
    FENCE = "```"
    SHARED_COMMANDS = {"say", "ask", "status"}
    EVERY_CLI_COMMANDS = {
        "claude": SHARED_COMMANDS | {"login", "wait", "logout"},
        "opencode": SHARED_COMMANDS | {"login", "logout"},
        "dsh": SHARED_COMMANDS,
    }

    def skill(self, lang: str, cli: str) -> str:
        resource = kit_root().joinpath(lang, cli, "skills", "chatlogin", "SKILL.md")
        return resource.read_text(encoding="utf-8")

    def code_of(self, text: str) -> str:
        fenced, prose, code = False, [], []
        for line in text.splitlines():
            if line.lstrip().startswith(self.FENCE):
                fenced = not fenced
            else:
                (code if fenced else prose).append(line)
        code.extend(self.INLINE_CODE.findall("\n".join(prose)))
        return "\n".join(code)

    def mentions(self, text: str) -> tuple[set[str], set[str]]:
        code = self.code_of(text)
        return set(self.COMMAND.findall(code)), set(self.FLAG.findall(code))

    ALL_CLIS = (*kit.CLIS, "dsh")

    def skills(self) -> dict[tuple[str, str], str]:
        return {
            (lang, cli): self.skill(lang, cli)
            for lang in variants()
            for cli in self.ALL_CLIS
        }

    def test_every_language_and_cli_pair_has_a_skill_to_compare(self):
        for lang in variants():
            for cli in self.ALL_CLIS:
                resource = kit_root().joinpath(
                    lang, cli, "skills", "chatlogin", "SKILL.md"
                )
                with self.subTest(lang=lang, cli=cli):
                    self.assertTrue(resource.is_file(), resource)

    def test_the_languages_of_one_cli_name_the_same_commands_and_flags(self):
        skills = self.skills()
        for cli in self.ALL_CLIS:
            said = [
                self.mentions(skills[(lang, cli)])
                for lang in variants()
                if (lang, cli) in skills
            ]
            with self.subTest(cli=cli):
                self.assertEqual(said[1:], said[:-1])

    def test_every_cli_names_the_commands_the_project_agrees_on(self):
        for (lang, cli), text in sorted(self.skills().items()):
            commands, _ = self.mentions(text)
            with self.subTest(lang=lang, cli=cli):
                self.assertTrue(self.EVERY_CLI_COMMANDS[cli] <= commands, commands)

    def test_the_listener_is_a_claude_command_and_lives_in_the_plugin_for_opencode(
        self,
    ):
        for (lang, cli), text in sorted(self.skills().items()):
            with self.subTest(lang=lang, cli=cli):
                commands, _ = self.mentions(text)
                self.assertEqual("wait" in commands, cli == "claude")

    def test_prose_that_names_the_tool_is_not_taken_for_a_command(self):
        text = "The agentschat tool prints the reply, see --help."
        self.assertEqual(self.mentions(text), (set(), set()))

    def test_a_command_in_inline_code_is_taken(self):
        text = "Run `agentschat say --agent me` first."
        self.assertEqual(self.mentions(text), ({"say"}, {"--agent"}))

    def test_a_command_in_a_fenced_block_is_taken(self):
        text = "Run:\n```bash\nagentschat ask --timeout 5\n```\nThe agentschat tool."
        self.assertEqual(self.mentions(text), ({"ask"}, {"--timeout"}))

    def test_an_extra_flag_in_one_language_is_caught(self):
        for (lang, cli), text in sorted(self.skills().items()):
            drifted = f"{text}\n`agentschat say --extra`\n"
            with self.subTest(lang=lang, cli=cli):
                self.assertNotEqual(self.mentions(drifted), self.mentions(text))

    def test_a_lost_timeout_flag_is_caught(self):
        for (lang, cli), text in sorted(self.skills().items()):
            drifted = text.replace("--timeout", "")
            with self.subTest(lang=lang, cli=cli):
                self.assertNotEqual(self.mentions(drifted), self.mentions(text))

    def test_a_renamed_agent_flag_is_caught(self):
        for (lang, cli), text in sorted(self.skills().items()):
            drifted = text.replace("--agent", "--name")
            with self.subTest(lang=lang, cli=cli):
                self.assertNotEqual(self.mentions(drifted), self.mentions(text))


class KitCompletenessTests(unittest.TestCase):
    FILES_OF_A_LANGUAGE = {
        "claude/skills/chatlogin/SKILL.md",
        "dsh/skills/chatlogin/SKILL.md",
        "opencode/command/chatlogin.md",
        "opencode/skills/chatlogin/SKILL.md",
    }

    def paths_of(self, lang: str) -> set[str]:
        found = files_under(kit_root().joinpath(lang))
        return {relative for relative in found}

    def test_every_language_ships_every_kit_file(self):
        for lang in variants():
            with self.subTest(lang=lang):
                self.assertEqual(self.paths_of(lang), self.FILES_OF_A_LANGUAGE)

    def test_every_language_ships_a_skill_for_both_clis(self):
        for lang in variants():
            with self.subTest(lang=lang):
                clis = {relative.split("/", 1)[0] for relative in self.paths_of(lang)}
                self.assertEqual(clis - {"dsh"}, set(kit.CLIS))
                self.assertIn("dsh", clis)

    def test_a_language_without_a_file_is_reported_as_missing(self):
        broken = self.paths_of("en") - {"opencode/command/chatlogin.md"}
        self.assertNotEqual(broken, self.FILES_OF_A_LANGUAGE)


if __name__ == "__main__":
    unittest.main()
