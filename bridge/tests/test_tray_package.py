"""Task tray-02: where the tray package sits and what it may import."""

import ast
import tomllib
import unittest
from pathlib import Path

BRIDGE = Path(__file__).resolve().parent.parent
PACKAGE = BRIDGE / "quoroomtray"
FORBIDDEN_IN_THE_MODEL = ("pystray", "PIL")


def imported_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


class TrayPackageBoundaryTests(unittest.TestCase):
    def test_no_module_of_the_package_imports_pystray_or_pillow(self):
        for path in sorted(PACKAGE.glob("*.py")):
            with self.subTest(module=path.name):
                self.assertEqual(
                    set(), imported_modules(path) & set(FORBIDDEN_IN_THE_MODEL)
                )

    def test_the_package_is_not_part_of_the_installed_distribution(self):
        with open(BRIDGE / "pyproject.toml", "rb") as source:
            packages = tomllib.load(source)["tool"]["setuptools"]["packages"]

        self.assertNotIn("quoroomtray", packages)

    def test_the_package_reaches_into_sessionchat_only_for_the_catalogue_loader(self):
        reached = set()
        for path in sorted(PACKAGE.glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] == "sessionchat":
                        reached.add(node.module)

        self.assertEqual({"sessionchat.i18n"}, reached)

    def test_the_package_has_the_two_message_tables(self):
        self.assertTrue((PACKAGE / "messages" / "en.json").is_file())
        self.assertTrue((PACKAGE / "messages" / "ru.json").is_file())


if __name__ == "__main__":
    unittest.main()
