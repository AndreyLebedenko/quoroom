import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sessionchat import client, kit
from sessionchat.installer import main as installer
from sessionchat.kit import Action

CYRILLIC = re.compile("[\u0400-\u04ff]")


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

    def install(self, clis=kit.CLIS, force=False):
        roots = {cli: self.roots[cli] for cli in clis}
        return kit.install(self.manifest_path, roots, force=force)

    def uninstall(self, clis=kit.CLIS, force=False):
        return kit.uninstall(self.manifest_path, self.roots, clis, force=force)

    def expected(self, cli: str) -> dict[Path, bytes]:
        return {
            self.roots[cli].joinpath(*item.relative.parts): item.content
            for item in kit.kit_files(cli)
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
            for item in kit.kit_files(cli)
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
        steps = self.install()
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
        steps = self.install()
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
        steps = self.install()
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
        steps = self.install(force=True)
        content = self.expected("opencode")[self.plugin()]
        self.assertEqual(self.actions(steps)[self.plugin()], Action.OVERWRITE)
        self.assertEqual(self.plugin().read_bytes(), content)
        self.assertEqual(
            self.manifest()[self.plugin()], kit.Entry("opencode", kit.digest(content))
        )

    def test_installing_twice_leaves_the_same_files_and_the_same_manifest(self):
        self.install()
        after_first = tree(self.home)
        steps = self.install()
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
        steps = self.uninstall()
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
        steps = self.uninstall()
        self.assertEqual(self.actions(steps)[self.plugin()], Action.KEEP)
        self.assertIn(str(self.plugin()), self.step(steps, self.plugin()).line())
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
        steps = self.uninstall(force=True)
        self.assertEqual(self.actions(steps)[self.plugin()], Action.REMOVE)
        self.assertFalse(self.plugin().exists())
        self.assertEqual(self.manifest(), {})

    def test_an_already_deleted_file_is_reported_gone_and_dropped_from_the_manifest(
        self,
    ):
        self.install()
        self.plugin().unlink()
        steps = self.uninstall()
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
        self.assertEqual(self.uninstall(), [])
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
                    kit.Step(action, target, "claude").line(), f"{label}  {target}"
                )

    def test_install_summary_tells_the_human_to_restart_open_sessions_of_each_cli(
        self,
    ):
        steps = [
            kit.Step(Action.INSTALL, Path("a"), "claude"),
            kit.Step(Action.UPDATE, Path("b"), "opencode"),
        ]
        summary = kit.install_summary(steps)
        self.assertIn("Перезапустите открытые сессии Claude Code и OpenCode", summary)

    def test_install_summary_names_only_the_clis_whose_files_changed(self):
        steps = [
            kit.Step(Action.OVERWRITE, Path("a"), "opencode"),
            kit.Step(Action.UNCHANGED, Path("b"), "claude"),
        ]
        summary = kit.install_summary(steps)
        self.assertIn("Перезапустите открытые сессии OpenCode:", summary)
        self.assertNotIn("Claude Code", summary)

    def test_install_summary_without_changes_asks_for_no_restart(self):
        steps = [kit.Step(Action.UNCHANGED, Path("a"), "claude")]
        self.assertNotIn("Перезапустите", kit.install_summary(steps))

    def test_uninstall_summary_tells_the_human_to_restart_after_a_removal(self):
        steps = [kit.Step(Action.REMOVE, Path("a"), "opencode")]
        self.assertIn(
            "Перезапустите открытые сессии OpenCode", kit.uninstall_summary(steps)
        )

    def test_uninstall_summary_points_to_force_when_an_edited_file_was_kept(self):
        steps = [kit.Step(Action.KEEP, Path("a"), "claude")]
        self.assertIn("agentschat uninstall --force", kit.uninstall_summary(steps))

    def test_uninstall_summary_with_nothing_installed_says_there_is_nothing(self):
        self.assertIn("удалять нечего", kit.uninstall_summary([]))


class AgentschatCase(KitSandbox):
    def setUp(self):
        super().setUp()
        for item in (
            patch.object(client, "STORE", self.manifest_path.parent),
            patch.object(kit, "DEFAULT_ROOTS", self.roots),
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
        out, _, code = self.run_agentschat("install", *self.dir_flags())
        self.assertEqual(code, 0)
        self.assertIn(f"установлен  {self.plugin()}", out)
        self.assertIn("Перезапустите", out)
        self.assertTrue((client.STORE / "kit.json").is_file())

        out, _, code = self.run_agentschat("uninstall")
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
        out, err, code = self.run_agentschat("install", *self.dir_flags())
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn(str(self.plugin()), err)
        self.assertIn("--force", err)
        self.assertFalse(self.claude_skill().exists())

    def test_force_through_the_cli_overwrites_the_unlisted_file(self):
        self.plugin().parent.mkdir(parents=True)
        self.plugin().write_text("// чужой плагин", encoding="utf-8")
        out, _, code = self.run_agentschat("install", "--force", *self.dir_flags())
        self.assertEqual(code, 0)
        self.assertIn(f"перезаписан  {self.plugin()}", out)

    def test_uninstall_force_through_the_cli_removes_an_edited_file(self):
        self.run_agentschat("install", *self.dir_flags())
        self.plugin().write_text("// моя правка", encoding="utf-8")
        out, _, _ = self.run_agentschat("uninstall", "--opencode")
        self.assertIn(f"оставлен (изменён вручную)  {self.plugin()}", out)
        out, _, _ = self.run_agentschat("uninstall", "--opencode", "--force")
        self.assertIn(f"удалён  {self.plugin()}", out)
        self.assertTrue(self.claude_skill().is_file())


class StepDisplayTests(unittest.TestCase):
    def test_every_action_of_a_step_has_a_display_word(self):
        self.assertEqual(set(kit.DISPLAY_RU), set(kit.Action))


class ReportTests(AgentschatCase):
    def document(self, *arguments):
        out, err, code = self.run_agentschat(*arguments, "--json")
        return json.loads(out), err, code

    def steps_of(self, document):
        return {
            (step["action"], step["cli"], step["target"]) for step in document["steps"]
        }

    def refused_by(self, *arguments):
        self.plugin().parent.mkdir(parents=True)
        self.plugin().write_text("// чужой плагин", encoding="utf-8")
        return self.document(*arguments, *self.dir_flags())

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
        out, err, code = self.run_agentschat("install", *self.dir_flags())
        self.assertEqual(code, client.FAILURE)
        self.assertEqual(out, "")
        self.assertIn(str(self.plugin()), err)
        self.assertIn("--force", err)


class ExitCodeTests(unittest.TestCase):
    def test_the_refusal_code_of_the_client_is_not_one_the_installer_uses(self):
        self.assertNotIn(client.REFUSED, set(installer.CODES.values()))

    def test_the_refusal_code_of_the_client_differs_from_a_plain_failure(self):
        self.assertNotEqual(client.REFUSED, client.FAILURE)


if __name__ == "__main__":
    unittest.main()
