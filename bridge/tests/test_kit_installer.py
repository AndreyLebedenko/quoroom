import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sessionchat import client, client_language, kit
from sessionchat.installer import main as installer
from sessionchat.i18n import LANGUAGES
from sessionchat.kit import Action

CYRILLIC = re.compile("[\u0400-\u04ff]")
BRIDGE = Path(__file__).resolve().parents[1]
RUSSIAN = "ru"


def tree(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


class KitSandbox(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name).resolve()
        self.roots = {
            "claude": self.home / "claude",
            "opencode": self.home / "config" / "opencode",
        }
        for root in self.roots.values():
            root.mkdir(parents=True)
        self.manifest_path = self.home / "store" / "kit.json"

    def install(self, clis=kit.CLIS, force=False, lang=RUSSIAN):
        roots = {cli: self.roots[cli] for cli in clis}
        return kit.install(self.manifest_path, roots, force=force, lang=lang)

    def uninstall(self, clis=kit.CLIS, force=False):
        return kit.uninstall(self.manifest_path, self.roots, clis, force=force)

    def expected(self, cli: str) -> dict[Path, bytes]:
        variant, _ = kit.variant_of(RUSSIAN, cli)
        return {
            self.roots[cli].joinpath(*item.relative.parts): item.content
            for item in kit.kit_files(cli, variant)
        }

    def manifest(self) -> dict[Path, kit.Entry]:
        return kit.load_manifest(self.manifest_path)

    def actions(self, steps) -> dict[Path, Action]:
        return {step.target: step.action for step in steps}

    def plugin(self) -> Path:
        return self.roots["opencode"] / "plugins" / "agentschat.js"

    def claude_skill(self) -> Path:
        return self.roots["claude"] / "skills" / "chatlogin" / "SKILL.md"


class KitFilesTests(unittest.TestCase):
    def test_kit_files_of_each_cli_mirror_the_kit_tree_under_that_cli(self):
        relatives = {
            (item.cli, item.relative.as_posix())
            for cli in kit.CLIS
            for item in kit.kit_files(cli, kit.variant_of(RUSSIAN, cli)[0])
        }
        self.assertEqual(
            relatives,
            {
                ("claude", "skills/chatlogin/SKILL.md"),
                ("opencode", "skills/chatlogin/SKILL.md"),
                ("opencode", "command/chatlogin.md"),
                ("opencode", "plugins/agentschat.js"),
            },
        )

    def test_kit_files_are_read_from_whatever_kit_source_is_given(self):
        with tempfile.TemporaryDirectory() as scratch:
            source = Path(scratch)
            (source / "claude" / "deep" / "er").mkdir(parents=True)
            (source / "claude" / "deep" / "er" / "x.md").write_bytes(b"x\r\n")
            files = kit.kit_files("claude", source)
        self.assertEqual(
            [(item.relative.as_posix(), item.content) for item in files],
            [("deep/er/x.md", b"x\r\n")],
        )


class ChosenClisTests(unittest.TestCase):
    def test_neither_flag_chooses_both_clis(self):
        self.assertEqual(kit.chosen_clis(False, False), ("claude", "opencode"))

    def test_the_claude_flag_alone_chooses_only_claude(self):
        self.assertEqual(kit.chosen_clis(True, False), ("claude",))

    def test_the_opencode_flag_alone_chooses_only_opencode(self):
        self.assertEqual(kit.chosen_clis(False, True), ("opencode",))

    def test_both_flags_choose_both_clis(self):
        self.assertEqual(kit.chosen_clis(True, True), ("claude", "opencode"))


class TargetRootsTests(unittest.TestCase):
    def test_default_roots_are_the_user_directories_of_each_cli_in_the_home(self):
        self.assertEqual(
            kit.DEFAULT_ROOTS,
            {
                "claude": Path.home() / ".claude",
                "opencode": Path.home() / ".config" / "opencode",
            },
        )

    def test_a_cli_without_a_given_directory_targets_its_default_root(self):
        self.assertEqual(
            kit.target_roots(("claude", "opencode")),
            kit.DEFAULT_ROOTS,
        )

    def test_a_given_directory_replaces_the_default_root_of_its_cli_only(self):
        self.assertEqual(
            kit.target_roots(("claude", "opencode"), claude_dir="X:/elsewhere"),
            {
                "claude": Path("X:/elsewhere"),
                "opencode": kit.DEFAULT_ROOTS["opencode"],
            },
        )

    def test_only_the_chosen_clis_get_a_target_root(self):
        self.assertEqual(
            list(kit.target_roots(("opencode",), claude_dir="X:/elsewhere")),
            ["opencode"],
        )


class InstallTests(KitSandbox):
    def test_install_copies_every_kit_file_of_both_clis_creating_directories(self):
        self.install()
        for cli in kit.CLIS:
            for target, content in self.expected(cli).items():
                with self.subTest(target=target):
                    self.assertEqual(target.read_bytes(), content)

    def test_install_reports_each_new_file_as_installed(self):
        steps = self.install().steps
        expected = {**self.expected("claude"), **self.expected("opencode")}
        self.assertEqual(
            self.actions(steps), {target: Action.INSTALL for target in expected}
        )

    def test_install_with_only_claude_writes_nothing_under_the_opencode_root(self):
        self.install(clis=("claude",))
        self.assertTrue(self.claude_skill().is_file())
        self.assertEqual(tree(self.roots["opencode"]), {})

    def test_install_with_only_opencode_writes_nothing_under_the_claude_root(self):
        self.install(clis=("opencode",))
        self.assertTrue(self.plugin().is_file())
        self.assertEqual(tree(self.roots["claude"]), {})

    def test_the_manifest_records_each_written_file_by_absolute_path_sha256_and_cli(
        self,
    ):
        self.install()
        expected = {
            target: kit.Entry(cli, kit.digest(content))
            for cli in kit.CLIS
            for target, content in self.expected(cli).items()
        }
        self.assertEqual(self.manifest(), expected)
        self.assertTrue(all(target.is_absolute() for target in self.manifest()))

    def test_a_manifest_entry_holds_nothing_but_path_sha256_and_cli(self):
        self.install()
        stored = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(list(stored), ["files"])
        for item in stored["files"]:
            self.assertEqual(set(item), {"path", "sha256", "cli"})

    def test_a_file_listed_in_the_manifest_is_overwritten_as_an_update(self):
        self.install()
        self.plugin().write_text("// старая версия", encoding="utf-8")
        steps = self.install().steps
        self.assertEqual(self.actions(steps)[self.plugin()], Action.UPDATE)
        self.assertEqual(
            self.plugin().read_bytes(), self.expected("opencode")[self.plugin()]
        )

    def test_an_unlisted_identical_file_is_adopted_into_the_manifest_as_unchanged(
        self,
    ):
        content = self.expected("opencode")[self.plugin()]
        self.plugin().parent.mkdir(parents=True)
        self.plugin().write_bytes(content)
        steps = self.install().steps
        self.assertEqual(self.actions(steps)[self.plugin()], Action.UNCHANGED)
        self.assertEqual(
            self.manifest()[self.plugin()], kit.Entry("opencode", kit.digest(content))
        )

    def test_an_unlisted_different_file_refuses_the_install_naming_that_file(self):
        self.plugin().parent.mkdir(parents=True)
        self.plugin().write_text("// чужой плагин", encoding="utf-8")
        with self.assertRaises(kit.KitConflict) as refusal:
            self.install()
        self.assertEqual(refusal.exception.targets, [self.plugin()])
        self.assertIn(str(self.plugin()), str(refusal.exception))
        self.assertIn("--force", str(refusal.exception))

    def test_a_refused_install_writes_nothing_at_all_not_even_the_manifest(self):
        self.install(clis=("claude",))
        self.claude_skill().write_text("правка перед обновлением", encoding="utf-8")
        self.plugin().parent.mkdir(parents=True)
        self.plugin().write_text("// чужой плагин", encoding="utf-8")
        before = tree(self.home)
        with self.assertRaises(kit.KitConflict):
            self.install()
        self.assertEqual(tree(self.home), before)

    def test_force_overwrites_an_unlisted_different_file_and_adopts_it(self):
        self.plugin().parent.mkdir(parents=True)
        self.plugin().write_text("// чужой плагин", encoding="utf-8")
        steps = self.install(force=True).steps
        content = self.expected("opencode")[self.plugin()]
        self.assertEqual(self.actions(steps)[self.plugin()], Action.OVERWRITE)
        self.assertEqual(self.plugin().read_bytes(), content)
        self.assertEqual(
            self.manifest()[self.plugin()], kit.Entry("opencode", kit.digest(content))
        )

    def test_installing_twice_leaves_the_same_files_and_the_same_manifest(self):
        self.install()
        after_first = tree(self.home)
        steps = self.install().steps
        self.assertEqual(tree(self.home), after_first)
        self.assertEqual(
            set(self.actions(steps).values()),
            {Action.UNCHANGED},
        )

    def test_install_of_one_cli_keeps_the_manifest_entries_of_the_other(self):
        self.install()
        opencode_entries = {
            target: entry
            for target, entry in self.manifest().items()
            if entry.cli == "opencode"
        }
        self.install(clis=("claude",))
        for target, entry in opencode_entries.items():
            self.assertEqual(self.manifest()[target], entry)


class UninstallTests(KitSandbox):
    def test_uninstall_removes_every_file_it_installed_and_reports_it_removed(self):
        self.install()
        steps = self.uninstall().steps
        installed = {**self.expected("claude"), **self.expected("opencode")}
        self.assertEqual(
            self.actions(steps), {target: Action.REMOVE for target in installed}
        )
        self.assertFalse(any(target.exists() for target in installed))

    def test_uninstall_removes_directories_it_left_empty_but_never_the_root(self):
        self.install()
        self.uninstall()
        for root in self.roots.values():
            with self.subTest(root=root):
                self.assertTrue(root.is_dir())
                self.assertEqual(tree(root), {})

    def test_uninstall_keeps_a_directory_that_still_holds_an_unrelated_file(self):
        self.install()
        unrelated = self.claude_skill().parent / "notes.md"
        unrelated.write_text("моё", encoding="utf-8")
        self.uninstall()
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "моё")
        self.assertFalse(self.claude_skill().exists())

    def test_uninstall_keeps_an_unrelated_empty_directory_and_its_parents(self):
        self.install()
        (self.claude_skill().parent / "empty").mkdir()
        self.uninstall()
        self.assertTrue((self.claude_skill().parent / "empty").is_dir())

    def test_install_then_uninstall_leaves_the_target_tree_exactly_as_before(self):
        (self.roots["claude"] / "skills" / "graphify").mkdir(parents=True)
        (self.roots["claude"] / "skills" / "graphify" / "SKILL.md").write_text(
            "чужой навык", encoding="utf-8"
        )
        (self.roots["opencode"] / "plugins").mkdir()
        (self.roots["opencode"] / "plugins" / "graphify.js").write_text(
            "// чужой плагин", encoding="utf-8"
        )
        before = {cli: tree(root) for cli, root in self.roots.items()}
        self.install()
        self.uninstall()
        self.assertEqual({cli: tree(root) for cli, root in self.roots.items()}, before)

    def test_uninstall_removes_the_manifest_once_it_lists_nothing(self):
        self.install()
        self.uninstall()
        self.assertFalse(self.manifest_path.exists())

    def test_a_user_edited_file_is_kept_named_and_left_in_the_manifest(self):
        self.install()
        self.plugin().write_text("// моя правка", encoding="utf-8")
        entry = self.manifest()[self.plugin()]
        steps = self.uninstall().steps
        self.assertEqual(self.actions(steps)[self.plugin()], Action.KEEP)
        self.assertIn(str(self.plugin()), self.step(steps, self.plugin()).line(RUSSIAN))
        self.assertEqual(self.plugin().read_text(encoding="utf-8"), "// моя правка")
        self.assertEqual(self.manifest(), {self.plugin(): entry})

    def test_a_user_edited_file_does_not_stop_the_untouched_ones_being_removed(self):
        self.install()
        self.plugin().write_text("// моя правка", encoding="utf-8")
        self.uninstall()
        others = {**self.expected("claude"), **self.expected("opencode")}
        del others[self.plugin()]
        self.assertFalse(any(target.exists() for target in others))

    def test_force_removes_a_user_edited_file_too(self):
        self.install()
        self.plugin().write_text("// моя правка", encoding="utf-8")
        steps = self.uninstall(force=True).steps
        self.assertEqual(self.actions(steps)[self.plugin()], Action.REMOVE)
        self.assertFalse(self.plugin().exists())
        self.assertEqual(self.manifest(), {})

    def test_an_already_deleted_file_is_reported_gone_and_dropped_from_the_manifest(
        self,
    ):
        self.install()
        self.plugin().unlink()
        steps = self.uninstall().steps
        self.assertEqual(self.actions(steps)[self.plugin()], Action.GONE)
        self.assertEqual(self.manifest(), {})

    def test_uninstall_of_claude_only_leaves_opencode_files_and_entries(self):
        self.install()
        opencode_before = tree(self.roots["opencode"])
        self.uninstall(clis=("claude",))
        self.assertEqual(tree(self.roots["opencode"]), opencode_before)
        self.assertEqual(
            {entry.cli for entry in self.manifest().values()}, {"opencode"}
        )
        self.assertEqual(tree(self.roots["claude"]), {})

    def test_uninstall_without_a_manifest_removes_nothing_and_reports_nothing(self):
        self.plugin().parent.mkdir(parents=True)
        self.plugin().write_text("// не наш", encoding="utf-8")
        before = tree(self.home)
        self.assertEqual(self.uninstall().steps, ())
        self.assertEqual(tree(self.home), before)

    def test_a_listed_file_outside_its_root_is_removed_but_no_directory_is(self):
        self.install()
        elsewhere = {
            "claude": self.home / "elsewhere",
            "opencode": self.roots["opencode"],
        }
        kit.uninstall(self.manifest_path, elsewhere, ("claude",))
        self.assertFalse(self.claude_skill().exists())
        self.assertTrue(self.claude_skill().parent.is_dir())

    def step(self, steps, target):
        return next(step for step in steps if step.target == target)


class ReportTextTests(unittest.TestCase):
    def test_each_step_prints_as_its_russian_label_then_the_target_path(self):
        target = Path("C:/x/SKILL.md")
        labels = {
            Action.INSTALL: "установлен",
            Action.UPDATE: "обновлён",
            Action.OVERWRITE: "перезаписан",
            Action.UNCHANGED: "без изменений",
            Action.REMOVE: "удалён",
            Action.KEEP: "оставлен (изменён вручную)",
            Action.GONE: "уже нет",
        }
        for action, label in labels.items():
            with self.subTest(action=action):
                self.assertEqual(
                    kit.Step(action, target, "claude").line(RUSSIAN),
                    f"{label}  {target}",
                )

    def test_install_summary_tells_the_human_to_restart_open_sessions_of_each_cli(
        self,
    ):
        steps = [
            kit.Step(Action.INSTALL, Path("a"), "claude"),
            kit.Step(Action.UPDATE, Path("b"), "opencode"),
        ]
        summary = kit.install_summary(steps, RUSSIAN)
        self.assertIn("Перезапустите открытые сессии Claude Code и OpenCode", summary)

    def test_install_summary_names_only_the_clis_whose_files_changed(self):
        steps = [
            kit.Step(Action.OVERWRITE, Path("a"), "opencode"),
            kit.Step(Action.UNCHANGED, Path("b"), "claude"),
        ]
        summary = kit.install_summary(steps, RUSSIAN)
        self.assertIn("Перезапустите открытые сессии OpenCode:", summary)
        self.assertNotIn("Claude Code", summary)

    def test_install_summary_without_changes_asks_for_no_restart(self):
        steps = [kit.Step(Action.UNCHANGED, Path("a"), "claude")]
        self.assertNotIn("Перезапустите", kit.install_summary(steps, RUSSIAN))

    def test_uninstall_summary_tells_the_human_to_restart_after_a_removal(self):
        steps = [kit.Step(Action.REMOVE, Path("a"), "opencode")]
        self.assertIn(
            "Перезапустите открытые сессии OpenCode",
            kit.uninstall_summary(steps, RUSSIAN),
        )

    def test_uninstall_summary_points_to_force_when_an_edited_file_was_kept(self):
        steps = [kit.Step(Action.KEEP, Path("a"), "claude")]
        self.assertIn(
            "agentschat uninstall --force", kit.uninstall_summary(steps, RUSSIAN)
        )

    def test_uninstall_summary_with_nothing_installed_says_there_is_nothing(self):
        self.assertIn("удалять нечего", kit.uninstall_summary([], RUSSIAN))


class AgentschatCase(KitSandbox):
    def setUp(self):
        super().setUp()
        for item in (
            patch.object(client, "STORE", self.manifest_path.parent),
            patch.object(kit, "DEFAULT_ROOTS", self.roots),
            patch.object(client, "ROOM_LANGUAGE", client_language.RoomLanguage()),
        ):
            item.start()
            self.addCleanup(item.stop)

    def run_agentschat(self, *arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["agentschat", *arguments]):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                try:
                    client.main()
                except SystemExit as exit_code:
                    return stdout.getvalue(), stderr.getvalue(), exit_code.code
        return stdout.getvalue(), stderr.getvalue(), 0

    def dir_flags(self):
        return (
            "--claude-dir",
            str(self.roots["claude"]),
            "--opencode-dir",
            str(self.roots["opencode"]),
        )

    def every_target(self):
        return {(cli, target) for cli in kit.CLIS for target in self.expected(cli)}


class AgentschatCommandTests(AgentschatCase):
    def test_install_and_uninstall_through_the_cli_use_the_given_dirs_and_store(self):
        out, _, code = self.run_agentschat(
            "install", "--lang", RUSSIAN, *self.dir_flags()
        )
        self.assertEqual(code, 0)
        self.assertIn(f"установлен  {self.plugin()}", out)
        self.assertIn("Перезапустите", out)
        self.assertTrue((client.STORE / "kit.json").is_file())

        out, _, code = self.run_agentschat("uninstall", "--lang", RUSSIAN)
        self.assertEqual(code, 0)
        self.assertIn(f"удалён  {self.plugin()}", out)
        self.assertEqual(
            {cli: tree(root) for cli, root in self.roots.items()},
            {
                "claude": {},
                "opencode": {},
            },
        )

    def test_the_claude_flag_through_the_cli_installs_only_claude(self):
        self.run_agentschat("install", "--claude", *self.dir_flags())
        self.assertTrue(self.claude_skill().is_file())
        self.assertEqual(tree(self.roots["opencode"]), {})

    def test_a_refused_install_through_the_cli_exits_non_zero_naming_file_and_force(
        self,
    ):
        self.plugin().parent.mkdir(parents=True)
        self.plugin().write_text("// чужой плагин", encoding="utf-8")
        out, err, code = self.run_agentschat(
            "install", "--lang", RUSSIAN, *self.dir_flags()
        )
        self.assertEqual(code, client.FAILURE)
        self.assertEqual(out, "")
        self.assertIn(str(self.plugin()), err)
        self.assertIn("--force", err)
        self.assertFalse(self.claude_skill().exists())

    def test_force_through_the_cli_overwrites_the_unlisted_file(self):
        self.plugin().parent.mkdir(parents=True)
        self.plugin().write_text("// чужой плагин", encoding="utf-8")
        out, _, code = self.run_agentschat(
            "install", "--lang", RUSSIAN, "--force", *self.dir_flags()
        )
        self.assertEqual(code, 0)
        self.assertIn(f"перезаписан  {self.plugin()}", out)

    def test_uninstall_force_through_the_cli_removes_an_edited_file(self):
        self.run_agentschat("install", "--lang", RUSSIAN, *self.dir_flags())
        self.plugin().write_text("// моя правка", encoding="utf-8")
        out, _, _ = self.run_agentschat("uninstall", "--lang", RUSSIAN, "--opencode")
        self.assertIn(f"оставлен (изменён вручную)  {self.plugin()}", out)
        out, _, _ = self.run_agentschat(
            "uninstall", "--lang", RUSSIAN, "--opencode", "--force"
        )
        self.assertIn(f"удалён  {self.plugin()}", out)
        self.assertTrue(self.claude_skill().is_file())


class ReportTests(AgentschatCase):
    def document(self, *arguments, lang=RUSSIAN):
        out, err, code = self.run_agentschat(*arguments, "--json", "--lang", lang)
        return json.loads(out), err, code

    def steps_of(self, document):
        return {
            (step["action"], step["cli"], step["target"]) for step in document["steps"]
        }

    def refused_by(self, *arguments):
        self.plugin().parent.mkdir(parents=True)
        self.plugin().write_text("// чужой плагин", encoding="utf-8")
        return self.document(*arguments, *self.dir_flags())

    def cyrillic_roots(self):
        return {"claude": self.home / "Андрей", "opencode": self.home / "Олег"}

    def cyrillic_flags(self, roots):
        return [flag for cli in kit.CLIS for flag in (f"--{cli}-dir", str(roots[cli]))]

    def test_a_first_install_reports_every_file_as_installed(self):
        document, _, code = self.document("install", *self.dir_flags())
        self.assertEqual(code, 0)
        self.assertEqual(
            document,
            {
                "command": "install",
                "ok": True,
                "code": "none",
                "steps": [
                    {"action": "installed", "cli": cli, "target": str(target)}
                    for cli, target in sorted(self.every_target())
                ],
            },
        )

    def test_the_document_of_an_install_is_the_only_thing_on_stdout(self):
        out, _, _ = self.run_agentschat("install", "--json", *self.dir_flags())
        self.assertEqual(len(out.splitlines()), 1)
        self.assertIsNone(CYRILLIC.search(out), out)

    def test_a_cyrillic_path_reaches_the_document_of_an_install_as_ascii(self):
        roots = self.cyrillic_roots()
        out, _, code = self.run_agentschat(
            "install", "--json", *self.cyrillic_flags(roots)
        )
        self.assertEqual(code, 0)
        self.assertTrue(out.isascii(), out)
        self.assertIn(str(roots["claude"]), json.loads(out)["steps"][0]["target"])

    def test_a_cyrillic_path_reaches_the_document_of_a_removal_as_ascii(self):
        roots = self.cyrillic_roots()
        self.run_agentschat("install", *self.cyrillic_flags(roots))
        with patch.object(kit, "DEFAULT_ROOTS", roots):
            out, _, code = self.run_agentschat("uninstall", "--json")
        self.assertEqual(code, 0)
        self.assertTrue(out.isascii(), out)
        self.assertIn(str(roots["claude"]), json.loads(out)["steps"][0]["target"])

    def test_a_repeat_install_reports_every_file_as_unchanged(self):
        self.run_agentschat("install", *self.dir_flags())
        document, _, code = self.document("install", *self.dir_flags())
        self.assertEqual(code, 0)
        self.assertEqual({step["action"] for step in document["steps"]}, {"unchanged"})

    def test_an_updated_file_is_reported_as_updated(self):
        self.run_agentschat("install", *self.dir_flags())
        self.plugin().write_text("// старая версия", encoding="utf-8")
        document, _, _ = self.document("install", *self.dir_flags())
        self.assertIn(
            ("updated", "opencode", str(self.plugin())), self.steps_of(document)
        )

    def test_a_forced_overwrite_is_reported_as_overwritten(self):
        document, _, code = self.refused_by("install", "--force")
        self.assertEqual(code, 0)
        self.assertIn(
            ("overwritten", "opencode", str(self.plugin())), self.steps_of(document)
        )

    def test_a_refused_install_reports_the_conflict_in_the_document(self):
        document, err, code = self.refused_by("install")
        self.assertEqual(code, client.REFUSED)
        self.assertEqual(err, "")
        self.assertEqual(document["code"], "conflict")
        self.assertFalse(document["ok"])
        self.assertIn(
            ("conflict", "opencode", str(self.plugin())), self.steps_of(document)
        )

    def test_a_refused_install_names_only_the_file_it_refused(self):
        document, _, _ = self.refused_by("install")
        self.assertEqual(len(document["steps"]), 1)

    def test_an_uninstall_reports_the_command_it_belongs_to(self):
        self.run_agentschat("install", *self.dir_flags())
        document, _, code = self.document("uninstall")
        self.assertEqual(code, 0)
        self.assertEqual(document["command"], "uninstall")
        self.assertEqual(document["code"], "none")

    def test_an_uninstall_reports_an_edited_file_as_kept_and_the_rest_as_removed(self):
        self.run_agentschat("install", *self.dir_flags())
        self.plugin().write_text("// моя правка", encoding="utf-8")
        document, _, _ = self.document("uninstall")
        self.assertIn(("kept", "opencode", str(self.plugin())), self.steps_of(document))
        self.assertIn(
            ("removed", "claude", str(self.claude_skill())), self.steps_of(document)
        )

    def test_a_refusal_without_the_flag_still_names_the_file_and_force(self):
        self.plugin().parent.mkdir(parents=True)
        self.plugin().write_text("// чужой плагин", encoding="utf-8")
        out, err, code = self.run_agentschat(
            "install", "--lang", RUSSIAN, *self.dir_flags()
        )
        self.assertEqual(code, client.FAILURE)
        self.assertEqual(out, "")
        self.assertIn(str(self.plugin()), err)
        self.assertIn("--force", err)

    def test_the_document_apart_from_its_code_does_not_depend_on_the_language(self):
        russian, _, _ = self.document("install", *self.dir_flags())
        for root in self.roots.values():
            shutil.rmtree(root)
            root.mkdir()
        self.manifest_path.unlink(missing_ok=True)
        english, _, _ = self.document("install", lang="en", *self.dir_flags())
        self.assertEqual(self.without_code(english), self.without_code(russian))

    def without_code(self, document):
        return {key: value for key, value in document.items() if key != "code"}


class VariantChoiceTests(KitSandbox):
    def test_a_language_with_a_variant_reports_nothing_special(self):
        self.assertEqual(self.install().code, kit.CODE_NONE)

    def test_a_second_install_over_the_same_variant_changes_nothing(self):
        self.install()
        again = self.install()
        self.assertEqual({step.action for step in again.steps}, {Action.UNCHANGED})

    def test_a_manifest_written_by_the_layout_before_the_move_is_read_as_it_was(self):
        previous_content = b"the skill of the previous release\n"
        self.claude_skill().parent.mkdir(parents=True)
        self.claude_skill().write_bytes(previous_content)
        self.manifest_path.parent.mkdir(parents=True)
        self.manifest_path.write_text(
            json.dumps(
                {
                    "files": [
                        {
                            "path": str(self.claude_skill()),
                            "sha256": hashlib.sha256(previous_content).hexdigest(),
                            "cli": "claude",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        report = self.install(clis=("claude",))
        self.assertEqual(
            self.actions(report.steps), {self.claude_skill(): Action.UPDATE}
        )


class PartialEnglishVariantTests(KitSandbox):
    ENGLISH_SKILL = b"English skill of the Claude Code kit\n"

    def setUp(self):
        super().setUp()
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.source = Path(scratch.name) / "kit"
        shutil.copytree(str(kit.KIT), self.source)
        english = self.source / "en" / "claude" / "skills" / "chatlogin"
        english.mkdir(parents=True)
        (english / "SKILL.md").write_bytes(self.ENGLISH_SKILL)

    def install_from_partial(self, lang, clis=kit.CLIS):
        roots = {cli: self.roots[cli] for cli in clis}
        return kit.install(self.manifest_path, roots, source=self.source, lang=lang)

    def russian_bytes(self, cli, *parts):
        return (self.source / "ru" / cli).joinpath(*parts).read_bytes()

    def test_a_cli_that_has_the_variant_takes_it(self):
        self.install_from_partial("en")
        self.assertEqual(self.claude_skill().read_bytes(), self.ENGLISH_SKILL)

    def test_a_cli_without_the_variant_takes_russian_and_the_code_says_so(self):
        report = self.install_from_partial("en")
        self.assertEqual(report.code, kit.VARIANT_MISSING)
        self.assertEqual(
            (self.roots["opencode"] / "skills" / "chatlogin" / "SKILL.md").read_bytes(),
            self.russian_bytes("opencode", "skills", "chatlogin", "SKILL.md"),
        )
        self.assertEqual(
            (self.roots["opencode"] / "command" / "chatlogin.md").read_bytes(),
            self.russian_bytes("opencode", "command", "chatlogin.md"),
        )

    def test_asking_for_opencode_alone_installs_its_russian_files_and_says_so(self):
        report = self.install_from_partial("en", clis=("opencode",))
        self.assertEqual(report.code, kit.VARIANT_MISSING)
        self.assertEqual(
            {step.target.name for step in report.steps},
            {"SKILL.md", "chatlogin.md", "agentschat.js"},
        )

    def test_asking_for_claude_alone_has_nothing_to_report(self):
        report = self.install_from_partial("en", clis=("claude",))
        self.assertEqual(report.code, kit.CODE_NONE)

    def test_a_language_that_is_complete_reports_nothing_while_english_is_partial(
        self,
    ):
        self.assertEqual(self.install_from_partial(RUSSIAN).code, kit.CODE_NONE)

    def test_the_variant_files_land_at_the_paths_the_russian_ones_did(self):
        self.install_from_partial(RUSSIAN)
        russian_paths = set(tree(self.roots["claude"]))
        self.install_from_partial("en")
        self.assertEqual(set(tree(self.roots["claude"])), russian_paths)

    def test_the_manifest_lists_the_same_paths_whichever_variant_was_laid_down(self):
        self.install_from_partial(RUSSIAN)
        after_russian = set(self.manifest())
        self.install_from_partial("en")
        self.assertEqual(set(self.manifest()), after_russian)

    def test_changing_the_language_goes_through_the_update_path_and_back(self):
        self.install_from_partial(RUSSIAN)
        russian = self.claude_skill().read_bytes()
        english = self.install_from_partial("en")
        self.assertEqual(
            self.actions(english.steps)[self.claude_skill()], Action.UPDATE
        )
        self.assertEqual(self.claude_skill().read_bytes(), self.ENGLISH_SKILL)
        back = self.install_from_partial(RUSSIAN)
        self.assertEqual(self.actions(back.steps)[self.claude_skill()], Action.UPDATE)
        self.assertEqual(self.claude_skill().read_bytes(), russian)

    def test_changing_the_language_leaves_the_files_of_the_other_cli_alone(self):
        self.install_from_partial(RUSSIAN)
        english = self.install_from_partial("en")
        others = {step.action for step in english.steps if step.cli == "opencode"}
        self.assertEqual(others, {Action.UNCHANGED})

    def test_changing_the_language_back_and_forth_never_conflicts(self):
        self.install_from_partial(RUSSIAN)
        for lang in ("en", RUSSIAN, "en"):
            with self.subTest(lang=lang):
                report = self.install_from_partial(lang)
                self.assertNotIn(Action.CONFLICT, {s.action for s in report.steps})


class ReportReadTests(unittest.TestCase):
    def document(self, **changes) -> str:
        stored = {
            "command": "install",
            "ok": True,
            "code": "none",
            "steps": [{"action": "installed", "cli": "claude", "target": "a"}],
        }
        return json.dumps(stored | changes)

    def test_every_code_that_is_not_a_refusal_is_read_back_as_ok(self):
        for code in (kit.CODE_NONE, kit.VARIANT_MISSING):
            with self.subTest(code=code):
                report = kit.Report.read(self.document(code=code), "install")
                self.assertEqual(report.code, code)
                self.assertTrue(report.ok)

    def test_a_refusal_is_read_back_as_not_ok(self):
        report = kit.Report.read(
            self.document(code=kit.CODE_CONFLICT, ok=False), "install"
        )
        self.assertFalse(report.ok)

    def test_a_code_nobody_defined_is_not_read_even_when_it_claims_success(self):
        self.assertIsNone(kit.Report.read(self.document(code="mystery"), "install"))

    def test_a_known_code_with_the_wrong_ok_is_not_read(self):
        wrong = self.document(code=kit.VARIANT_MISSING, ok=False)
        self.assertIsNone(kit.Report.read(wrong, "install"))


class TemporaryVariantFallbackTests(KitSandbox):
    def test_a_language_without_a_variant_still_lays_the_kit_down(self):
        report = kit.install(self.manifest_path, self.roots, lang="en")
        self.assertEqual(report.code, kit.VARIANT_MISSING)
        self.assertTrue(report.ok)
        self.assertTrue(self.claude_skill().is_file())
        self.assertTrue(self.plugin().is_file())

    def test_the_fallback_lays_down_exactly_the_variant_that_exists(self):
        kit.install(self.manifest_path, self.roots, lang="en")
        expected = {
            self.roots[cli].joinpath(*item.relative.parts): item.content
            for cli in kit.CLIS
            for item in kit.kit_files(cli, kit.variant_of(kit.FALLBACK_VARIANT, cli)[0])
        }
        self.assertEqual({path: path.read_bytes() for path in expected}, expected)

    def test_the_human_is_told_that_the_variant_is_not_the_one_asked_for(self):
        out, err, code = self.agentschat("install", "--lang", "en")
        self.assertEqual(code, 0)
        self.assertIn("AGENTSCHAT: the Quoroom kit is installed.", out)
        self.assertIn("no Quoroom kit variant for en yet", err)
        self.assertIn("agentschat install --lang en", err)

    def test_the_document_carries_the_substitution_code(self):
        out, err, code = self.agentschat("install", "--lang", "en", "--json")
        self.assertEqual(code, 0)
        document = json.loads(out)
        self.assertEqual(document["code"], kit.VARIANT_MISSING)
        self.assertTrue(document["ok"])
        self.assertIn("no Quoroom kit variant for en yet", err)

    def test_a_language_with_a_variant_says_nothing_about_substitution(self):
        _, err, code = self.agentschat("install", "--lang", RUSSIAN)
        self.assertEqual(code, 0)
        self.assertEqual(err, "")

    def agentschat(self, *arguments) -> tuple[str, str, int]:
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = [
            "agentschat",
            *arguments,
            "--claude-dir",
            str(self.roots["claude"]),
            "--opencode-dir",
            str(self.roots["opencode"]),
        ]
        with patch.object(sys, "argv", argv):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                try:
                    client.main()
                except SystemExit as exit_code:
                    return stdout.getvalue(), stderr.getvalue(), exit_code.code
        return stdout.getvalue(), stderr.getvalue(), 0


class StepLineTests(unittest.TestCase):
    TABLE = {
        Action.INSTALL: {"ru": "установлен", "en": "installed"},
        Action.UPDATE: {"ru": "обновлён", "en": "updated"},
        Action.OVERWRITE: {"ru": "перезаписан", "en": "overwritten"},
        Action.UNCHANGED: {"ru": "без изменений", "en": "unchanged"},
        Action.CONFLICT: {
            "ru": "занят чужим файлом",
            "en": "taken by a foreign file",
        },
        Action.REMOVE: {"ru": "удалён", "en": "removed"},
        Action.KEEP: {
            "ru": "оставлен (изменён вручную)",
            "en": "left in place (edited by hand)",
        },
        Action.GONE: {"ru": "уже нет", "en": "already gone"},
    }

    def test_every_action_says_the_same_thing_in_both_languages(self):
        for action, words in self.TABLE.items():
            for lang in LANGUAGES:
                with self.subTest(action=action, lang=lang):
                    self.assertEqual(
                        kit.CATALOGUE.text(lang, kit.action_key(action)), words[lang]
                    )

    def test_every_action_of_a_step_has_a_word_in_both_languages(self):
        for action in kit.Action:
            for lang in LANGUAGES:
                with self.subTest(action=action, lang=lang):
                    self.assertTrue(kit.CATALOGUE.text(lang, kit.action_key(action)))

    def test_the_step_line_is_the_action_word_then_the_target_in_both_languages(self):
        step = kit.Step(Action.INSTALL, Path("C:/x/SKILL.md"), "claude")
        self.assertEqual(step.line(RUSSIAN), f"установлен  {Path('C:/x/SKILL.md')}")
        self.assertEqual(step.line("en"), f"installed  {Path('C:/x/SKILL.md')}")

    def test_the_russian_summary_lines_are_the_ones_the_client_always_printed(self):
        steps = [
            kit.Step(Action.INSTALL, Path("a"), "claude"),
            kit.Step(Action.UPDATE, Path("b"), "opencode"),
        ]
        self.assertEqual(
            kit.install_summary(steps, RUSSIAN),
            "AGENTSCHAT: набор Quoroom установлен.\n"
            "Перезапустите открытые сессии Claude Code и OpenCode: "
            "запущенные изменений не увидят.",
        )

    def test_the_english_install_summary_says_the_same_thing_in_english(self):
        steps = [
            kit.Step(Action.INSTALL, Path("a"), "claude"),
            kit.Step(Action.UPDATE, Path("b"), "opencode"),
        ]
        self.assertEqual(
            kit.install_summary(steps, "en"),
            "AGENTSCHAT: the Quoroom kit is installed.\n"
            "Restart the open Claude Code and OpenCode sessions: "
            "the running ones will not see the change.",
        )

    def test_an_install_with_nothing_to_do_says_it_in_both_languages(self):
        steps = [kit.Step(Action.UNCHANGED, Path("a"), "claude")]
        self.assertEqual(
            kit.install_summary(steps, RUSSIAN),
            "AGENTSCHAT: набор Quoroom уже на месте, менять нечего.",
        )
        self.assertEqual(
            kit.install_summary(steps, "en"),
            "AGENTSCHAT: the Quoroom kit is already in place, nothing to change.",
        )

    def test_an_empty_removal_says_it_in_both_languages(self):
        self.assertEqual(
            kit.uninstall_summary([], RUSSIAN),
            "AGENTSCHAT: установленного набора Quoroom нет, удалять нечего.",
        )
        self.assertEqual(
            kit.uninstall_summary([], "en"),
            "AGENTSCHAT: there is no installed Quoroom kit, nothing to remove.",
        )

    def test_a_kept_file_is_named_with_the_way_to_remove_it_in_both_languages(self):
        steps = [kit.Step(Action.KEEP, Path("a"), "claude")]
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                self.assertIn(
                    "agentschat uninstall --force",
                    kit.uninstall_summary(steps, lang),
                )

    def test_the_refusal_names_the_file_the_reason_and_the_way_out_in_both_languages(
        self,
    ):
        steps = [kit.Step(Action.CONFLICT, Path("C:/x/SKILL.md"), "claude")]
        said = {lang: str(kit.KitConflict(steps, lang)) for lang in LANGUAGES}
        for lang, refusal in said.items():
            with self.subTest(lang=lang):
                self.assertIn(str(Path("C:/x/SKILL.md")), refusal)
                self.assertIn("--force", refusal)
        self.assertIn("ничего не записано", said[RUSSIAN])
        self.assertIn("отличаются от набора Quoroom", said[RUSSIAN])
        self.assertIn("nothing was written", said["en"])
        self.assertIn("differ from the Quoroom kit", said["en"])

    def test_the_english_refusal_and_help_carry_no_cyrillic(self):
        said = [
            kit.CATALOGUE.text("en", key, **{"default": "x", "files": "f"})
            for key in (
                "kit.conflict",
                "kit.help_install",
                "kit.help_uninstall",
                "kit.help_claude_only",
                "kit.help_opencode_only",
                "kit.help_dir",
                "kit.help_force_install",
                "kit.help_force_uninstall",
                "kit.help_json",
                "kit.help_lang",
            )
        ]
        for line in said:
            with self.subTest(line=line):
                self.assertIsNone(CYRILLIC.search(line), line)


class HelpTests(AgentschatCase):
    def shown(self, *arguments) -> tuple[str, int]:
        stdout, stderr = io.StringIO(), io.StringIO()
        code = 0
        with patch.object(sys, "argv", ["agentschat", *arguments]):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                try:
                    client.main()
                except SystemExit as exit_code:
                    code = exit_code.code
        return stdout.getvalue() + stderr.getvalue(), code

    def helped(self, command: str) -> str:
        return self.shown(command, "--help")[0]

    def test_the_help_of_both_commands_names_the_language_flag(self):
        for command in ("install", "uninstall"):
            with self.subTest(command=command):
                self.assertIn("--lang", self.helped(command))

    def test_the_help_of_both_commands_says_which_languages_it_takes(self):
        for command in ("install", "uninstall"):
            with self.subTest(command=command):
                self.assertIn("language of the answer: en or ru", self.helped(command))

    def test_the_help_of_both_commands_offers_the_report_flag(self):
        for command in ("install", "uninstall"):
            with self.subTest(command=command):
                self.assertIn("--json", self.helped(command))

    def test_the_main_help_describes_both_commands_in_the_known_language(self):
        shown, code = self.shown("--help")
        self.assertEqual(code, 0)
        self.assertIn("put the Quoroom kit into the Claude Code", shown)
        self.assertIn("remove the installed Quoroom kit", shown)

    def test_the_remembered_language_decides_the_help(self):
        (client.STORE).mkdir(parents=True, exist_ok=True)
        (client.STORE / "language").write_text("ru\n", encoding="utf-8")
        self.assertIn("перезаписать чужие файлы", self.helped("install"))
        self.assertIn("удалить и изменённые вручную файлы", self.helped("uninstall"))
        self.assertIn("отчёт кодом, без предложений", self.helped("install"))
        self.assertIn("разложить набор Quoroom", self.shown("--help")[0])

    def test_an_unknown_language_is_refused_before_anything_is_installed(self):
        shown, code = self.shown("install", "--lang", "fr")
        self.assertEqual(code, 2)
        self.assertIn("invalid choice: 'fr'", shown)
        self.assertEqual(tree(self.roots["claude"]), {})


class RealClientTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name).resolve()

    def client(self, *arguments):
        return subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "sessionchat.client", *arguments],
            cwd=BRIDGE,
            env=dict(
                os.environ,
                PYTHONPATH=str(BRIDGE),
                HOME=str(self.home),
                USERPROFILE=str(self.home),
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            stdin=subprocess.DEVNULL,
            check=False,
        )

    def kit_files(self) -> list[Path]:
        return sorted(
            path
            for root in (self.home / ".claude", self.home / ".config" / "opencode")
            for path in root.rglob("*")
            if path.is_file()
        )

    def test_an_english_install_writes_the_kit_and_prints_only_ascii(self):
        done = self.client("install", "--lang", "en")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(self.kit_files())
        self.assertTrue(done.stdout.isascii(), done.stdout)
        self.assertTrue(done.stderr.isascii(), done.stderr)

    def test_an_english_removal_takes_the_kit_back_and_prints_only_ascii(self):
        self.client("install", "--lang", "en")
        done = self.client("uninstall", "--lang", "en")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.kit_files(), [])
        self.assertTrue(done.stdout.isascii(), done.stdout)
        self.assertTrue(done.stderr.isascii(), done.stderr)

    def test_a_russian_install_says_what_it_always_said(self):
        done = self.client("install", "--lang", "ru")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("AGENTSCHAT: набор Quoroom установлен.", done.stdout)
        self.assertIn(
            "Перезапустите открытые сессии Claude Code и OpenCode", done.stdout
        )

    def test_an_english_install_names_the_action_of_every_file_in_english(self):
        done = self.client("install", "--lang", "en")
        for path in self.kit_files():
            with self.subTest(path=path):
                self.assertIn(f"installed  {path}", done.stdout)

    def test_a_refused_english_install_says_why_in_ascii_and_exits_non_zero(self):
        foreign = self.home / ".claude" / "skills" / "chatlogin"
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("// not ours\n", encoding="utf-8")
        done = self.client("install", "--lang", "en")
        self.assertEqual(done.returncode, client.FAILURE)
        self.assertTrue(done.stderr.isascii(), done.stderr)
        self.assertIn("nothing was written", done.stderr)
        self.assertIn("--force", done.stderr)

    def test_a_refused_english_install_with_the_flag_reports_the_conflict_as_a_code(
        self,
    ):
        foreign = self.home / ".claude" / "skills" / "chatlogin"
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("// not ours\n", encoding="utf-8")
        done = self.client("install", "--lang", "en", "--json")
        self.assertEqual(done.returncode, client.REFUSED)
        self.assertEqual(json.loads(done.stdout)["code"], "conflict")
        self.assertEqual(done.stderr, "")


class ExitCodeTests(unittest.TestCase):
    def test_the_refusal_code_of_the_client_is_not_one_the_installer_uses(self):
        self.assertNotIn(client.REFUSED, set(installer.CODES.values()))

    def test_the_refusal_code_of_the_client_differs_from_a_plain_failure(self):
        self.assertNotEqual(client.REFUSED, client.FAILURE)


class ReportReadingTests(unittest.TestCase):
    def document(self, **changes) -> str:
        stored = {
            "command": kit.COMMAND_INSTALL,
            "ok": True,
            "code": kit.CODE_NONE,
            "steps": [{"action": "unchanged", "cli": "claude", "target": "a"}],
        }
        return json.dumps(stored | changes)

    def read(self, raw, command=kit.COMMAND_INSTALL):
        return kit.Report.read(raw, command)

    def test_a_document_of_the_asked_command_is_read(self):
        report = self.read(self.document())
        self.assertEqual(report.command, kit.COMMAND_INSTALL)
        self.assertEqual(report.code, kit.CODE_NONE)
        self.assertTrue(report.ok)
        self.assertEqual(report.steps[0].target, Path("a"))

    def test_a_document_of_another_command_is_no_document(self):
        self.assertIsNone(self.read(self.document(command=kit.COMMAND_UNINSTALL)))

    def test_a_document_that_contradicts_its_own_code_is_no_document(self):
        self.assertIsNone(self.read(self.document(ok=False)))

    def test_a_refusal_that_blames_no_file_is_no_document(self):
        self.assertIsNone(
            self.read(self.document(code=kit.CODE_CONFLICT, ok=False, steps=[]))
        )

    def test_an_empty_step_list_is_a_document_when_nothing_was_refused(self):
        self.assertEqual(self.read(self.document(steps=[])).steps, ())

    def test_words_around_the_document_are_no_document(self):
        self.assertIsNone(self.read(f"отчёт ниже:\n{self.document()}\nвсё."))

    def test_the_words_of_a_refusal_are_no_document(self):
        self.assertIsNone(self.read("установка отменена, ничего не записано."))

    def test_an_action_nobody_declared_is_no_document(self):
        self.assertIsNone(self.read(self.document(steps=[{"action": "written"}])))


if __name__ == "__main__":
    unittest.main()
