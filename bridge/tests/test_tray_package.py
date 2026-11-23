"""Task tray-02: where the tray package sits and what it may import."""

import ast
import tomllib
import unittest
from pathlib import Path

BRIDGE = Path(__file__).resolve().parent.parent
PACKAGE = BRIDGE / "quoroomtray"
SHELL = PACKAGE / "shell"
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


class TrayShellBoundaryTests(unittest.TestCase):
    def test_only_the_pystray_adapter_imports_pystray_or_pillow(self):
        importers = {
            path.relative_to(PACKAGE).as_posix()
            for path in PACKAGE.rglob("*.py")
            if imported_modules(path) & set(FORBIDDEN_IN_THE_MODEL)
        }

        self.assertEqual({"shell/pystray_shell.py"}, importers)

    def test_no_test_imports_pystray_or_pillow(self):
        importers = {
            path.name
            for path in (BRIDGE / "tests").rglob("*.py")
            if imported_modules(path) & set(FORBIDDEN_IN_THE_MODEL)
        }

        self.assertEqual(set(), importers)

    def test_only_the_entry_point_reaches_into_the_shell_package(self):
        reaching = set()
        for path in sorted(PACKAGE.glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.level == 1:
                    if (node.module or "").split(".")[0] == "shell":
                        reaching.add(path.name)

        self.assertEqual({"__main__.py"}, reaching)

    def test_the_adapter_is_the_only_module_in_the_shell_package(self):
        self.assertEqual(
            {"__init__.py", "pystray_shell.py"},
            {path.name for path in SHELL.glob("*.py")},
        )

    def test_the_tray_requirements_pin_pystray_and_pillow_exactly(self):
        lines = [
            line.strip()
            for line in (BRIDGE / "requirements-tray.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.startswith("#")
        ]

        self.assertEqual(2, len(lines))
        self.assertTrue(lines[0].startswith("pystray=="))
        self.assertTrue(lines[1].startswith("Pillow=="))

    def test_the_runtime_requirements_do_not_mention_the_tray_libraries(self):
        runtime = (BRIDGE / "requirements.txt").read_text(encoding="utf-8").lower()

        self.assertNotIn("pystray", runtime)
        self.assertNotIn("pillow", runtime)


if __name__ == "__main__":
    unittest.main()
