import unittest
from importlib.resources import files
from importlib.resources.abc import Traversable

EXPECTED_KIT_FILES = {
    "claude/skills/chatlogin/SKILL.md",
    "opencode/skills/chatlogin/SKILL.md",
    "opencode/command/chatlogin.md",
    "opencode/plugins/agentschat.js",
}
QUOROOM_REPOSITORY_PATHS = (
    "bridge\\agentschat",
    "bridge/agentschat",
    ".opencode/plugins",
)


def kit_root() -> Traversable:
    return files("sessionchat") / "kit"


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


class KitNamesNoQuoroomRepositoryPathTests(unittest.TestCase):
    def test_no_kit_file_mentions_a_path_inside_the_quoroom_repository(self):
        for relative, resource in sorted(files_under(kit_root()).items()):
            text = resource.read_text(encoding="utf-8")
            for path in QUOROOM_REPOSITORY_PATHS:
                with self.subTest(file=relative, path=path):
                    self.assertNotIn(path, text)


if __name__ == "__main__":
    unittest.main()
