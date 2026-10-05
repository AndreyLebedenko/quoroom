"""Карточка local-installers-02: ключи установщика и порядок ролей."""

import unittest

from tests.installer_fakes import InstallerTestCase, Marker, option, role
from sessionchat.installer.main import DONE, USAGE, main
from sessionchat.installer.options import UsageError, parse

NO_ROLES = "в этой сборке нет ни одной роли: установщик без ролей делать нечего."


def both_roles():
    return (role("server"), role("participant"))


class RoleSelectionTests(InstallerTestCase):
    def test_the_flag_selects_that_role(self):
        plan = parse(["--role", "server"], self.boundaries(), both_roles())
        self.assertEqual(plan.roles, ("server",))

    def test_both_runs_the_server_first_on_install(self):
        plan = parse(["--role", "both"], self.boundaries(), both_roles())
        self.assertEqual(plan.roles, ("server", "participant"))

    def test_both_runs_the_participant_first_on_removal(self):
        plan = parse(["--role", "both", "--remove"], self.boundaries(), both_roles())
        self.assertEqual(plan.roles, ("participant", "server"))

    def test_without_the_flag_an_interactive_terminal_is_asked(self):
        plan = parse([], self.boundaries(stdin="2\n", interactive=True), both_roles())
        self.assertEqual(plan.roles, ("participant",))

    def test_the_question_lists_the_roles_and_both(self):
        given = self.boundaries(stdin="1\n", interactive=True)
        parse([], given, both_roles())
        listed = given.stdout.getvalue()
        self.assertIn("server", listed)
        self.assertIn("participant", listed)
        self.assertIn("both", listed)

    def test_the_question_can_be_answered_with_both(self):
        plan = parse(
            [], self.boundaries(stdin="both\n", interactive=True), both_roles()
        )
        self.assertEqual(plan.roles, ("server", "participant"))

    def test_a_name_typed_at_the_question_is_taken(self):
        plan = parse(
            [], self.boundaries(stdin="server\n", interactive=True), both_roles()
        )
        self.assertEqual(plan.roles, ("server",))

    def test_an_unreadable_answer_is_a_usage_error(self):
        with self.assertRaises(UsageError):
            parse([], self.boundaries(stdin="what?\n", interactive=True), both_roles())

    def test_without_the_flag_and_without_a_terminal_it_is_a_usage_error(self):
        with self.assertRaises(UsageError):
            parse([], self.boundaries(), both_roles())

    def test_an_unknown_role_is_a_usage_error(self):
        given = self.boundaries()
        with self.assertRaises(UsageError):
            parse(["--role", "nobody"], given, both_roles())

    def test_an_unknown_role_is_named_in_russian_with_the_alternatives(self):
        given = self.boundaries()
        with self.assertRaises(UsageError) as problem:
            parse(["--role", "nobody"], given, both_roles())
        self.assertEqual(
            str(problem.exception),
            "роль nobody неизвестна, доступны: both, server, participant",
        )

    def test_a_role_that_is_not_installed_is_rejected(self):
        with self.assertRaises(UsageError):
            parse(["--role", "server"], self.boundaries(), (role("participant"),))


class FlagCombinationTests(InstallerTestCase):
    def test_purge_without_remove_is_a_usage_error(self):
        with self.assertRaises(UsageError):
            parse(["--purge"], self.boundaries(), both_roles())

    def test_purge_with_remove_is_accepted(self):
        plan = parse(
            ["--role", "server", "--remove", "--purge"],
            self.boundaries(),
            both_roles(),
        )
        self.assertEqual((plan.remove, plan.purge), (True, True))

    def test_install_leaves_both_flags_down(self):
        plan = parse(["--role", "server"], self.boundaries(), both_roles())
        self.assertEqual((plan.remove, plan.purge), (False, False))


class RoleOptionTests(InstallerTestCase):
    def given_roles(self):
        return (
            role("server", add_options=option("--name")),
            role("participant", add_options=option("--clis", action="store_true")),
        )

    def parse_both(self, argv):
        return parse(argv, self.boundaries(), self.given_roles())

    def test_the_dest_is_derived_from_the_role_and_the_flag(self):
        plan = self.parse_both(["--role", "server", "--name", "chat.local"])
        self.assertEqual(plan.answers["server"], {"server_name": "chat.local"})

    def test_a_flag_default_is_none_not_false(self):
        plan = self.parse_both(["--role", "server"])
        self.assertEqual(plan.answers["server"], {"server_name": None})

    def test_a_store_true_option_defaults_to_false(self):
        plan = self.parse_both(["--role", "server"])
        self.assertEqual(plan.answers["participant"], {"participant_clis": False})

    def test_another_roles_option_keeps_its_default(self):
        plan = self.parse_both(["--role", "server", "--name", "chat.local"])
        self.assertEqual(plan.answers["participant"], {"participant_clis": False})

    def test_two_roles_with_the_same_option_name_keep_their_own_values(self):
        roles = (
            role("server", add_options=option("--name-x", default="one")),
            role("participant", add_options=option("--name_x", default="two")),
        )
        plan = parse(["--role", "both", "--name_x", "chosen"], self.boundaries(), roles)
        self.assertEqual(plan.answers["server"], {"server_name_x": "one"})
        self.assertEqual(plan.answers["participant"], {"participant_name_x": "chosen"})

    def test_a_caller_supplied_dest_is_a_code_defect(self):
        def add(options) -> None:
            options.add("--name", dest="name", default="x")

        with self.assertRaises(TypeError):
            parse(
                ["--role", "server"],
                self.boundaries(),
                (role("server", add_options=add),),
            )

    def test_the_core_flags_are_not_answers(self):
        plan = self.parse_both(["--role", "both"])
        self.assertEqual(set(plan.answers), {"server", "participant"})

    def test_a_role_flag_of_an_absent_role_is_rejected(self):
        with self.assertRaises(UsageError):
            parse(
                ["--role", "participant", "--name", "chat.local"],
                self.boundaries(),
                (role("participant"),),
            )


class MainOrderTests(InstallerTestCase):
    def roles(self):
        return (
            role(
                "server",
                install=(Marker("поставить сервер", self.log),),
                remove=(Marker("убрать сервер", self.log),),
            ),
            role(
                "participant",
                install=(Marker("поставить участника", self.log),),
                remove=(Marker("убрать участника", self.log),),
            ),
        )

    def test_both_installs_the_server_before_the_participant(self):
        given = self.boundaries()
        code = main(["--role", "both"], given, self.roles())
        self.assertEqual(code, DONE)
        self.assertEqual(
            self.log,
            [
                "check:поставить сервер",
                "apply:поставить сервер",
                "check:поставить сервер",
                "check:поставить участника",
                "apply:поставить участника",
                "check:поставить участника",
            ],
        )

    def test_both_removes_the_participant_before_the_server(self):
        given = self.boundaries()
        code = main(["--role", "both", "--remove"], given, self.roles())
        self.assertEqual(code, DONE)
        self.assertEqual(
            self.log,
            [
                "check:убрать участника",
                "apply:убрать участника",
                "check:убрать участника",
                "check:убрать сервер",
                "apply:убрать сервер",
                "check:убрать сервер",
            ],
        )

    def test_the_order_comes_from_the_plan_not_from_the_argument_order(self):
        given = self.boundaries()
        code = main(
            ["--role", "both", "--remove"], given, tuple(reversed(self.roles()))
        )
        self.assertEqual(code, DONE)
        self.assertEqual(self.log[0], "check:убрать участника")


class ExitCodeTests(InstallerTestCase):
    def test_help_exits_zero_and_prints_usage(self):
        given = self.boundaries()
        code = main(["--help"], given, both_roles())
        self.assertEqual(code, DONE)
        self.assertIn("--role", given.stdout.getvalue())

    def test_a_usage_error_exits_two_and_explains_on_stderr(self):
        given = self.boundaries()
        code = main(["--purge"], given, both_roles())
        self.assertEqual(code, USAGE)
        self.assertIn("--purge", given.stderr.getvalue())

    def test_a_build_without_roles_says_so_instead_of_pretending(self):
        given = self.boundaries()
        code = main([], given, ())
        self.assertEqual(code, USAGE)
        self.assertIn(NO_ROLES, given.stderr.getvalue())

    def test_help_works_in_a_build_without_roles(self):
        given = self.boundaries()
        code = main(["--help"], given, ())
        self.assertEqual(code, DONE)

    def test_a_successful_run_exits_zero(self):
        self.assertEqual(
            main(["--role", "server"], self.boundaries(), both_roles()), DONE
        )


if __name__ == "__main__":
    unittest.main()
