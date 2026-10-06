"""Task english-release-17: nothing Russian is left in runtime files outside the allowlist."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import cyrillic_scan
from tests.cyrillic_scan import (
    Allowed,
    GitUnavailable,
    Policy,
    allowlist_problems,
    findings,
    javascript_findings,
    javascript_without_comments,
    literal_findings,
    python_findings,
    tracked_files,
    unlisted_findings,
)

REPO = Path(__file__).resolve().parents[2]

KIT = "bridge/sessionchat/kit/"
CATALOGUE_REASON = (
    "the Russian catalogue of the room language ru; the loader tests pin its keys"
)
COMMENTS_REASON = (
    "Russian comments and docstrings only; translating them is outside the story,"
    " and the literal scan proves no message string is Russian"
)
WRAPPER_REASON = (
    "the Russian message table of the wrapper, printed when the room language is ru;"
    " the tests of the wrappers pin it"
)

ALLOWLIST = (
    Allowed(
        ".development/",
        "planning cards, reports and bug reports for contributors; not shipped",
    ),
    Allowed(
        "docs/",
        "guides; the Russian ones stay as the second language and the English"
        " ones quote Russian output; classified by the release gate, task 20",
    ),
    Allowed("README.ru.md", "the Russian README, the second language"),
    Allowed(
        "README.md",
        "the link to the Russian README and Russian sample prompts and bot"
        " answers quoted as data",
    ),
    Allowed(
        ".gitignore",
        "contributor file; its Russian comments are out of scope of the story",
    ),
    Allowed(
        ".gitattributes",
        "contributor file; its Russian comments are out of scope of the story",
    ),
    Allowed(
        "bridge/requirements.txt",
        "contributor file; its Russian comments are out of scope of the story",
    ),
    Allowed(
        "tools/linux-container/run.sh",
        "Cyrillic is the fixture: the copy path carries spaces and Cyrillic so"
        " that a path a ru-locale user has is proved to cross the Windows to"
        " docker.exe boundary",
    ),
    Allowed(
        "tools/linux-container/verify-shared-home.sh",
        "Cyrillic is the fixture: a file name the machine writes in Cyrillic"
        " proves that the engine bind mount carries it",
    ),
    Allowed(
        "bridge/tests/",
        "tests assert the Russian text that room language ru prints and use"
        " Russian fixtures",
    ),
    Allowed("bridge/sessionchat/broker_messages/ru.json", CATALOGUE_REASON),
    Allowed("bridge/sessionchat/client_messages/ru.json", CATALOGUE_REASON),
    Allowed("bridge/sessionchat/installer/messages/ru.json", CATALOGUE_REASON),
    Allowed("bridge/register_messages/ru.json", CATALOGUE_REASON),
    Allowed(
        f"{KIT}ru/",
        "the Russian variant of the kit, installed when the room language is ru",
    ),
    Allowed("bridge/sessionchat/__init__.py", COMMENTS_REASON),
    Allowed("bridge/sessionchat/broker.py", COMMENTS_REASON),
    Allowed("bridge/sessionchat/client.py", COMMENTS_REASON),
    Allowed("bridge/sessionchat/protocol.py", COMMENTS_REASON),
    Allowed(
        f"{KIT}common/opencode/plugins/agentschat.js",
        "Russian comments only; the plugin has no language knowledge and its"
        " strings, templates and regular expressions are scanned",
    ),
    Allowed("install.ps1", WRAPPER_REASON),
    Allowed("install.sh", WRAPPER_REASON),
    Allowed("start.ps1", WRAPPER_REASON),
    Allowed("start.sh", WRAPPER_REASON),
    Allowed("stop.ps1", WRAPPER_REASON),
    Allowed("stop.sh", WRAPPER_REASON),
)

NOT_RUNTIME = (
    "bridge/tests/",
    "docs/",
    ".development/",
)

POLICY = Policy(allowed=ALLOWLIST, not_runtime=NOT_RUNTIME)

KIT_VARIANTS_THAT_MUST_BE_ENGLISH = (
    f"{KIT}en/claude/skills/chatlogin/SKILL.md",
    f"{KIT}en/opencode/skills/chatlogin/SKILL.md",
    f"{KIT}en/opencode/command/chatlogin.md",
    f"{KIT}common/opencode/other.js",
    f"{KIT}common/anything.md",
)


class RepositoryScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.files = tracked_files(REPO)
        except GitUnavailable as why:
            raise unittest.SkipTest(f"the scan needs git ls-files: {why}") from None

    def test_no_tracked_file_holds_cyrillic_unless_it_is_allowlisted(self):
        self.assertEqual([], unlisted_findings(REPO, self.files, POLICY))

    def test_no_runtime_python_or_javascript_has_a_cyrillic_string_literal(self):
        self.assertEqual([], literal_findings(REPO, self.files, POLICY))

    def test_every_allowlist_entry_has_a_reason_and_a_file_that_needs_it(self):
        self.assertEqual([], allowlist_problems(REPO, self.files, POLICY))

    def test_the_scan_reads_the_runtime_code_it_is_meant_to_protect(self):
        runtime = [name for name in self.files if POLICY.is_runtime_code(name)]
        for expected in (
            "bridge/register_account.py",
            "bridge/sessionchat/broker.py",
            "bridge/sessionchat/client.py",
            f"{KIT}common/opencode/plugins/agentschat.js",
        ):
            self.assertIn(expected, runtime)


class AllowlistBoundaryTests(unittest.TestCase):
    def test_the_english_kit_and_the_shared_kit_cannot_hold_cyrillic(self):
        for name in KIT_VARIANTS_THAT_MUST_BE_ENGLISH:
            with self.subTest(name):
                self.assertFalse(POLICY.allows(name))

    def test_the_russian_kit_may_hold_cyrillic(self):
        self.assertTrue(POLICY.allows(f"{KIT}ru/claude/skills/chatlogin/SKILL.md"))

    def test_the_only_allowlisted_file_of_the_shared_kit_is_the_plugin(self):
        shared = [
            entry.path for entry in ALLOWLIST if entry.path.startswith(f"{KIT}common")
        ]
        self.assertEqual([f"{KIT}common/opencode/plugins/agentschat.js"], shared)

    def test_nothing_of_the_english_kit_is_allowlisted(self):
        self.assertEqual(
            [], [entry.path for entry in ALLOWLIST if entry.path.startswith(f"{KIT}en")]
        )

    def test_the_operator_script_is_not_allowlisted(self):
        self.assertFalse(POLICY.allows("bridge/register_account.py"))

    def test_a_prefix_entry_covers_the_files_below_it_and_nothing_else(self):
        entry = Allowed("docs/", "a reason")
        self.assertTrue(entry.covers("docs/INSTALL.md"))
        self.assertFalse(entry.covers("docs.md"))
        self.assertFalse(entry.covers("bridge/docs/INSTALL.md"))

    def test_a_file_entry_covers_that_file_only(self):
        entry = Allowed("README.ru.md", "a reason")
        self.assertTrue(entry.covers("README.ru.md"))
        self.assertFalse(entry.covers("README.ru.md.bak"))


class TemporaryTree:
    def __init__(self, testcase: unittest.TestCase):
        self.root = Path(tempfile.mkdtemp())
        testcase.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def write(self, name: str, text: str) -> str:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return name


class ScanOnATemporaryTreeTests(unittest.TestCase):
    def setUp(self):
        self.tree = TemporaryTree(self)
        self.policy = Policy(
            allowed=(
                Allowed("docs/", "documents"),
                Allowed("bridge/old.py", "Russian comments only"),
                Allowed("bridge/catalogue/ru.json", "the Russian catalogue"),
            ),
            not_runtime=("tests/", "docs/"),
        )

    def scan(self, files: dict[str, str]) -> list[str]:
        names = [self.tree.write(name, text) for name, text in files.items()]
        return findings(self.tree.root, names, self.policy)

    def test_a_stray_russian_message_in_runtime_python_is_found_twice(self):
        problems = self.scan({"bridge/new.py": 'print("Привет, мир")\n'})
        self.assertEqual(2, len(problems))
        self.assertTrue(any("not allowlisted" in line for line in problems))
        self.assertTrue(any("Cyrillic outside comments" in line for line in problems))

    def test_a_stray_russian_message_in_runtime_javascript_is_found(self):
        problems = self.scan({"bridge/new.js": 'const say = "Привет"\n'})
        self.assertTrue(any("Cyrillic outside comments" in line for line in problems))

    def test_a_russian_message_in_a_file_that_may_hold_comments_is_still_found(self):
        problems = self.scan({"bridge/old.py": 'message = "Привет"\n'})
        self.assertEqual(1, len(problems))
        self.assertIn("Cyrillic outside comments", problems[0])

    def test_russian_comments_in_an_allowlisted_python_file_are_not_a_problem(self):
        source = '"""Модуль."""\n\n# Комментарий.\nvalue = 1  # хвост\n'
        self.assertEqual([], self.scan({"bridge/old.py": source}))

    def test_russian_comments_in_a_file_not_on_the_list_are_found_as_unlisted(self):
        problems = self.scan({"bridge/new.py": "# Комментарий.\nvalue = 1\n"})
        self.assertEqual(1, len(problems))
        self.assertIn("not allowlisted", problems[0])

    def test_russian_text_in_an_allowlisted_document_is_not_a_problem(self):
        self.assertEqual([], self.scan({"docs/GUIDE.md": "Установка.\n"}))

    def test_a_python_file_under_a_non_runtime_tree_is_not_scanned_for_literals(self):
        self.assertEqual([], self.scan({"docs/tool.py": 'print("Привет")\n'}))

    def test_russian_text_in_a_file_of_a_non_code_kind_not_on_the_list_is_found(self):
        problems = self.scan({"bridge/text.md": "Привет\n"})
        self.assertEqual(
            ["bridge/text.md: Cyrillic in a file that is not allowlisted"], problems
        )

    def test_an_english_tree_has_no_findings(self):
        self.assertEqual(
            [],
            self.scan(
                {
                    "bridge/fine.py": 'print("hello")\n',
                    "bridge/fine.js": 'const say = "hello"\n',
                    "bridge/fine.md": "hello\n",
                }
            ),
        )

    def test_a_listed_catalogue_may_hold_cyrillic_and_is_not_a_code_file(self):
        self.assertEqual(
            [], self.scan({"bridge/catalogue/ru.json": '{"a": "Привет"}\n'})
        )

    def test_a_file_that_is_not_utf8_is_reported(self):
        (self.tree.root / "bridge").mkdir()
        (self.tree.root / "bridge" / "latin.py").write_bytes(b"x = '\xff\xfe'\n")
        problems = findings(self.tree.root, ["bridge/latin.py"], self.policy)
        self.assertEqual(["bridge/latin.py: not valid UTF-8"], problems)

    def test_a_listed_but_deleted_file_is_skipped(self):
        self.assertEqual([], findings(self.tree.root, ["bridge/gone.py"], self.policy))


class AllowlistHygieneOnATemporaryTreeTests(unittest.TestCase):
    def setUp(self):
        self.tree = TemporaryTree(self)

    def problems(self, entries: tuple[Allowed, ...], files: dict[str, str]):
        names = [self.tree.write(name, text) for name, text in files.items()]
        policy = Policy(allowed=entries, not_runtime=())
        return allowlist_problems(self.tree.root, names, policy)

    def test_an_entry_without_a_reason_is_reported(self):
        problems = self.problems((Allowed("a.md", "  "),), {"a.md": "Привет"})
        self.assertEqual(["a.md: no reason"], problems)

    def test_an_entry_that_covers_nothing_is_reported(self):
        problems = self.problems((Allowed("gone.md", "why"),), {"a.md": "Привет"})
        self.assertEqual(["gone.md: covers no tracked file"], problems)

    def test_a_file_entry_whose_file_lost_its_cyrillic_is_reported(self):
        problems = self.problems((Allowed("a.md", "why"),), {"a.md": "Hello"})
        self.assertEqual(["a.md: holds no Cyrillic, drop the entry"], problems)

    def test_a_prefix_entry_may_cover_files_without_cyrillic(self):
        self.assertEqual(
            [], self.problems((Allowed("docs/", "why"),), {"docs/a.md": "Hello"})
        )


class PythonLiteralTests(unittest.TestCase):
    def test_comments_and_docstrings_are_not_literals(self):
        source = (
            '"""Модуль."""\n\n\nclass A:\n    """Класс."""\n\n'
            '    def run(self):\n        """Метод."""\n        # Комментарий\n'
            "        return 1\n"
        )
        self.assertEqual([], python_findings(source))

    def test_a_string_assigned_or_passed_is_a_literal(self):
        for source in ('a = "Привет"\n', 'print("Привет")\n', "f(x='Привет')\n"):
            with self.subTest(source):
                self.assertEqual(1, len(python_findings(source)))

    def test_an_f_string_with_russian_text_is_a_literal(self):
        self.assertEqual(1, len(python_findings('a = f"Привет {name}"\n')))

    def test_a_string_in_a_default_argument_is_a_literal(self):
        self.assertEqual(1, len(python_findings('def f(a="Привет"):\n    return a\n')))

    def test_a_second_string_statement_is_a_literal_not_a_docstring(self):
        source = 'def f():\n    """Док."""\n    "Привет"\n'
        self.assertEqual(1, len(python_findings(source)))

    def test_a_russian_identifier_is_reported(self):
        self.assertEqual(["line 1: identifier привет"], python_findings("привет = 1\n"))

    def test_the_line_of_the_literal_is_reported(self):
        source = "a = 1\nb = 2\nc = 'Привет'\n"
        self.assertTrue(python_findings(source)[0].startswith("line 3:"))

    def test_a_file_that_cannot_be_parsed_is_reported_not_skipped(self):
        problems = python_findings("def (:\n")
        self.assertEqual(1, len(problems))
        self.assertIn("cannot be parsed", problems[0])

    def test_english_strings_are_not_reported(self):
        self.assertEqual([], python_findings('a = "hello"\n# Привет\n'))


class JavaScriptLiteralTests(unittest.TestCase):
    def test_the_stripper_keeps_strings_templates_and_regular_expressions(self):
        kept = javascript_without_comments(
            "\n".join(
                [
                    "// comment жжж",
                    "const a = 'http://x' // tail жжж",
                    '/* block жжж */ const b = `t ${ "ж" /* inner жжж */ } end`',
                    "const c = /[/']ж/.test(a)",
                ]
            )
        )
        self.assertEqual(2, sum(1 for char in kept if char == "ж"))
        self.assertIn("http://x", kept)
        for dropped in ("comment", "block", "inner", "tail"):
            self.assertNotIn(dropped, kept)

    def test_comments_are_not_literals(self):
        source = "// Привет\n/* Привет\nещё строка */\nconst a = 1\n"
        self.assertEqual([], javascript_findings(source))

    def test_a_string_template_and_regex_are_literals(self):
        for source in (
            'const a = "Привет"\n',
            "const a = 'Привет'\n",
            "const a = `Привет`\n",
            "const a = /Привет/\n",
        ):
            with self.subTest(source):
                self.assertEqual(1, len(javascript_findings(source)))

    def test_russian_inside_a_template_substitution_is_a_literal(self):
        self.assertEqual(
            1, len(javascript_findings('const a = `x ${f("Привет")} y`\n'))
        )

    def test_a_comment_marker_inside_a_string_does_not_hide_the_rest(self):
        self.assertEqual(1, len(javascript_findings('const a = "//" + "Привет"\n')))

    def test_a_block_comment_keeps_the_line_numbers_of_what_follows(self):
        source = "/* one\ntwo\nthree */\nconst a = 'Привет'\n"
        self.assertTrue(javascript_findings(source)[0].startswith("line 4:"))

    def test_an_unterminated_block_comment_ends_the_scan_without_hanging(self):
        self.assertEqual([], javascript_findings("const a = 1 /* Привет"))

    def test_english_strings_are_not_reported(self):
        self.assertEqual([], javascript_findings("const a = 'hello' // Привет\n"))


class TrackedFilesTests(unittest.TestCase):
    def setUp(self):
        self.tree = TemporaryTree(self)

    def git(self, *arguments: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.tree.root), *arguments],
            check=True,
            capture_output=True,
        )

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_it_lists_the_tracked_files_and_not_the_untracked_ones(self):
        self.git("init")
        self.tree.write("a.py", "a = 1\n")
        self.tree.write("sub/b.md", "b\n")
        self.tree.write("untracked.txt", "u\n")
        self.git("add", "a.py", "sub/b.md")
        self.assertEqual(["a.py", "sub/b.md"], tracked_files(self.tree.root))

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_a_directory_that_is_not_a_work_tree_is_reported_as_unavailable(self):
        with self.assertRaises(GitUnavailable):
            tracked_files(self.tree.root)

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_a_subdirectory_of_a_work_tree_is_not_scanned_as_if_it_were_the_root(self):
        self.git("init")
        self.tree.write("inner/a.py", "a = 1\n")
        self.git("add", "inner/a.py")
        with self.assertRaises(GitUnavailable):
            tracked_files(self.tree.root / "inner")

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_a_work_tree_with_nothing_tracked_is_reported_as_unavailable(self):
        self.git("init")
        with self.assertRaises(GitUnavailable):
            tracked_files(self.tree.root)

    def test_a_machine_without_git_is_reported_as_unavailable(self):
        with patch.object(
            cyrillic_scan.subprocess, "run", side_effect=FileNotFoundError("git")
        ):
            with self.assertRaises(GitUnavailable):
                tracked_files(self.tree.root)


if __name__ == "__main__":
    unittest.main()
