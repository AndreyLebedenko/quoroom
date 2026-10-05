"""Task installer-bilingual, slice 3: the server role speaks English by default and Russian on request."""

import re
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tests.installer_fakes import completed
from tests.test_installer_participant_languages import RunSpy, watched
import tests.test_installer_server as server_tests
from tests.test_installer_server import ADMIN, ROLE, ROOM, RemovalCase
from sessionchat.installer import server
from sessionchat.installer.boundaries import Probe
from sessionchat.installer.catalogue import LANGUAGES, STEP_PREFIX, catalogue
from sessionchat.installer.main import CANCELLED, DONE, FAILED, HUMAN, main
from sessionchat.installer.server import (
    HostRefused,
    KIND_WORDS,
    SERVER_NAME,
    asked_admin_user,
    compose_failure,
    host_failure,
    hosts_instruction,
    mkcert_failure,
    server_consequence,
    server_role,
    trust_instruction,
    venv_failure,
)
from sessionchat.installer.ownership import PurgeTarget
from sessionchat.installer.steps import NeedsHuman, Outcome, State, execute

CYRILLIC = re.compile("[Ѐ-ӿ]")
STABLE_STEP_NAME = re.compile(r"[a-z]+(_[a-z]+)*")
SERVER_KEY = re.compile(r"""["'](server\.[a-z_]+)["']""")
REGISTRATION_TOKEN = re.compile(r'registration_token = "([^"]+)"')
ENGLISH_PROBE_ERRORS = {
    "continuwuity перезапускается": "continuwuity is restarting",
    "сертификат не подтверждён: self signed": "certificate not verified: self signed",
    "отказано в соединении": "connection refused",
}
HOSTS_WINDOWS = r"C:\Windows\System32\drivers\etc\hosts"
HOME_MASK = "<home>"
HIDDEN = {"en": "<hidden>", "ru": "<скрыто>"}
PASSWORD = "hunter2-secret"


class AsksForThePassword:
    name = "asks_for_the_password"

    def check(self, run) -> State:
        return State.TODO

    def apply(self, run) -> None:
        raise NeedsHuman(run.t("server.admin_password_needed", variable=PASSWORD))


class ServerLanguageCase(RemovalCase):
    def setUp(self):
        super().setUp()
        self.spy = RunSpy()

    def probe(self, url: str) -> Probe:
        answer = super().probe(url)
        return replace(
            answer, error=ENGLISH_PROBE_ERRORS.get(answer.error, answer.error)
        )

    def roles(self):
        self.spy = RunSpy()
        python = self.venv_python or sys.executable
        return (watched(server_role(python=python, sleep=self.slept.append), self.spy),)

    def everything(self, *flags, **values):
        return self.install("--admin-user", ADMIN, "--room-id", ROOM, *flags, **values)

    def installed_in(self, lang, **values):
        values.setdefault("secret", lambda prompt: "typed")
        code, given = self.everything(lang=lang, **values)
        self.assertEqual(code, DONE, given.stderr.getvalue())
        return given

    def run_in(self, lang, **values):
        return self.given(lang=lang, **values)

    def masked(self, shown: str) -> str:
        return shown.replace(str(self.home), HOME_MASK)

    def where(self, relative: str) -> str:
        return self.masked(str(self.path(relative)))

    def hand_built_toml(self, body: str) -> None:
        self.toml().parent.mkdir(parents=True, exist_ok=True)
        self.toml().write_text(body, encoding="utf-8")


class Scenarios(ServerLanguageCase):
    def docker_missing_on_linux(self, lang):
        self.machine.present["docker"] = False
        return self.install(lang=lang)

    def docker_missing_on_windows(self, lang):
        self.machine.present["docker"] = False
        return self.install(platform="windows", lang=lang)

    def daemon_stopped_on_linux(self, lang):
        self.machine.present["daemon"] = False
        return self.install(lang=lang)

    def daemon_stopped_on_windows(self, lang):
        self.machine.present["daemon"] = False
        return self.install(platform="windows", lang=lang)

    def compose_missing_on_linux(self, lang):
        self.machine.present["compose"] = False
        return self.install(lang=lang)

    def compose_missing_on_windows(self, lang):
        self.machine.present["compose"] = False
        return self.install(platform="windows", lang=lang)

    def mkcert_missing_on_linux(self, lang):
        self.machine.present["mkcert"] = False
        return self.install(lang=lang)

    def mkcert_missing_on_windows(self, lang):
        self.machine.present["mkcert"] = False
        return self.install(platform="windows", lang=lang)

    def name_that_does_not_resolve_on_linux(self, lang):
        self.resolved = ()
        return self.install(lang=lang)

    def name_that_does_not_resolve_on_windows(self, lang):
        self.resolved = ()
        return self.install(platform="windows", lang=lang)

    def name_that_resolves_off_loopback(self, lang):
        self.resolved = ("192.168.1.10",)
        return self.install(lang=lang)

    def pip_that_fails(self, lang):
        self.machine.fail_pip = True
        return self.everything(lang=lang)

    def libraries_that_never_come_back(self, lang):
        self.machine.missing_import = 99
        return self.everything(lang=lang)

    def env_file_for_another_server(self, lang):
        (self.path("docker/.env")).write_text(
            "SERVER_NAME=other.local\n", encoding="utf-8"
        )
        return self.install(lang=lang)

    def env_file_without_the_server_name(self, lang):
        (self.path("docker/.env")).write_text("# nothing here\n", encoding="utf-8")
        return self.install(lang=lang)

    def toml_with_the_example_token(self, lang):
        self.copy_example("docker/continuwuity/continuwuity.toml.example", self.toml())
        return self.install(lang=lang)

    def toml_without_a_token_line(self, lang):
        self.hand_built_toml("[global]\nallow_registration = true\n")
        return self.install(lang=lang)

    def toml_with_an_empty_token(self, lang):
        self.hand_built_toml(
            '[global]\nallow_registration = true\nregistration_token = ""\n'
        )
        return self.install(lang=lang)

    def server_that_never_answers(self, lang):
        self.probe_status = None
        return self.everything(lang=lang)

    def compose_that_cannot_start(self, lang):
        self.machine.fail_up = "443/tcp: address already in use"
        return self.everything(lang=lang)

    def untrusted_certificate_on_linux(self, lang):
        self.probe_untrusted = True
        return self.everything(lang=lang)

    def untrusted_certificate_on_windows(self, lang):
        self.probe_untrusted = True
        return self.everything(platform="windows", lang=lang)

    def broken_config(self, lang):
        self.config().write_text('homeserver_url: "x"\n\tbroken: [\n', encoding="utf-8")
        return self.install(lang=lang)

    def no_admin_user(self, lang):
        return self.install("--room-id", ROOM, lang=lang)

    def no_admin_password(self, lang):
        return self.everything(env={"PATH": "", "HOME": str(self.home)}, lang=lang)

    def toml_nobody_made(self, lang):
        self.hand_built_toml(
            '[global]\nallow_registration = true\nregistration_token = "mine"\n'
        )
        return self.everything(lang=lang)

    def closed_registration(self, lang):
        self.machine.registration_open = False
        return self.everything(lang=lang)

    def no_issued_token(self, lang):
        self.machine.only_issued = True
        self.machine.log_has_token = False
        return self.everything(lang=lang)

    def whole_install(self, lang):
        return self.everything(lang=lang)

    def whole_install_asking_the_admin_user(self, lang):
        return self.install(
            "--room-id", ROOM, stdin=f"{ADMIN}\n", interactive=True, lang=lang
        )

    def manual_bots_on_a_hand_built_toml(self, lang):
        self.machine.accounts[ADMIN] = "already"
        self.hand_built_toml(
            '[global]\nallow_registration = true\nregistration_token = "mine"\n'
        )
        return self.everything(lang=lang)

    def bot_account_with_an_unknown_password(self, lang):
        self.machine.accounts["claude-code"] = "someone-elses"
        return self.everything(lang=lang)

    def bot_account_with_a_wrong_saved_password(self, lang):
        self.machine.accounts["claude-code"] = "someone-elses"
        self.accounts_file().parent.mkdir(parents=True, exist_ok=True)
        self.accounts_file().write_text(
            '{"claude-code": {"password": "saved"}}', encoding="utf-8"
        )
        return self.everything(lang=lang)

    def broker_port_of_another_value(self, lang):
        self.settled()
        self.edit_config({"sessionchat_port": 9999})
        return self.everything(lang=lang)

    def homeserver_address_of_another_server(self, lang):
        self.settled()
        self.edit_config({"homeserver_url": "https://elsewhere.example"})
        return self.everything(lang=lang)

    def registration_that_the_server_keeps_open(self, lang):
        self.machine.closed_status = [401]
        return self.everything(lang=lang)

    def registration_to_close_on_a_hand_built_toml(self, lang):
        self.settled()
        self.hand_built_toml(
            '[global]\nallow_registration = true\nregistration_token = "mine"\n'
        )
        return self.everything(lang=lang)

    def registration_closed_on_a_hand_built_toml_without_a_restart(self, lang):
        self.settled()
        self.hand_built_toml(
            '[global]\nallow_registration = false\nregistration_token = "mine"\n'
        )
        self.machine.closed_status = [401]
        return self.everything(lang=lang)

    def room_not_given(self, lang):
        return self.install("--admin-user", ADMIN, lang=lang)

    def room_given_as_the_example(self, lang):
        return self.room_given(f"!REPLACE_ME:{SERVER_NAME}", lang)

    def room_given_without_a_prefix(self, lang):
        return self.room_given("agents", lang)

    def room_given_with_a_space(self, lang):
        return self.room_given(f"!ab cd:{SERVER_NAME}", lang)

    def room_given_without_a_name(self, lang):
        return self.room_given(f"!:{SERVER_NAME}", lang)

    def room_given_of_another_server(self, lang):
        return self.room_given("!AbCd:elsewhere.example", lang)

    def alias_given_without_a_server(self, lang):
        return self.room_given("#alias", lang)

    def room_given_after_another_was_stored(self, lang):
        self.everything(lang=lang)
        return self.room_given("!AnotherRoom", lang)

    def room_typed_in_a_terminal(self, lang):
        return self.install(
            "--admin-user", ADMIN, stdin=f"{ROOM}\n", interactive=True, lang=lang
        )

    def room_asked_in_a_terminal_and_not_answered(self, lang):
        return self.install(
            "--admin-user", ADMIN, stdin="", interactive=True, lang=lang
        )

    def config_without_the_room_key(self, lang):
        self.config().write_text(
            'homeserver_url: "https://agentschat.local"\n', encoding="utf-8"
        )
        return self.everything(lang=lang)

    def start_script_that_fails(self, lang):
        self.machine.start_code = 1
        self.machine.stdout_log = "start script failed here\n"
        return self.everything(lang=lang)

    def broker_that_stays_silent(self, lang):
        def silent(url: str) -> Probe:
            if url.endswith("/status"):
                return Probe(None, "connection refused")
            return Probe(200, None)

        return self.everything(probe=silent, lang=lang)

    def running_broker_beside_new_bot_tokens(self, lang):
        self.machine.broker_up = True
        self.config().write_text(
            self.path("bridge/config.example.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        self.edit_config({"room_id": ROOM}, owned=False)
        return self.everything(lang=lang)

    def first_account_that_becomes_the_administrator(self, lang):
        self.machine.only_issued = True
        return self.everything(lang=lang)

    def whole_install_on_windows(self, lang):
        return self.everything(platform="windows", lang=lang)

    def remove_everything(self, lang):
        self.installed_in(lang)
        return self.remove(lang=lang)

    def remove_everything_on_windows(self, lang):
        self.installed_in(lang, platform="windows")
        return self.remove(platform="windows", lang=lang)

    def remove_a_hand_built_stand(self, lang):
        self.hand_built_toml("registration_token = 'x'\n")
        self.accounts_file().parent.mkdir(parents=True, exist_ok=True)
        self.accounts_file().write_text("{}", encoding="utf-8")
        self.write_state()
        self.machine.volumes = {"docker_continuwuity-data"}
        return self.remove(lang=lang)

    def remove_with_the_daemon_down(self, lang):
        self.installed_in(lang)
        self.machine.broker_up = False
        self.machine.present["daemon"] = False
        return self.remove(lang=lang)

    def remove_with_a_broken_down(self, lang):
        self.installed_in(lang)
        self.machine.fail_down = "Error response from daemon: network not found"
        return self.remove(lang=lang)

    def remove_with_a_failing_stop_script(self, lang):
        self.installed_in(lang)
        self.machine.stop_code = 1
        self.machine.stop_log = "stop script failed here"
        return self.remove(lang=lang)

    def remove_with_a_broker_that_never_stops(self, lang):
        self.installed_in(lang)
        return self.remove(probe=lambda url: Probe(200, None), lang=lang)

    def remove_from_inside_the_venv(self, lang):
        self.installed_in(lang)
        self.venv_python = self.venv() / "Scripts" / "python.exe"
        return self.remove(lang=lang)

    def purge_everything(self, lang):
        self.installed_in(lang)
        return self.purge(lang=lang)

    def purge_refused(self, lang):
        self.installed_in(lang)
        return self.remove("--purge", stdin="\n", lang=lang)

    def purge_with_the_daemon_down(self, lang):
        self.installed_in(lang)
        self.machine.broker_up = False
        self.machine.present["daemon"] = False
        return self.purge(lang=lang)

    def purge_with_a_volume_in_use(self, lang):
        self.installed_in(lang)
        self.machine.busy_volumes = {"docker_caddy-data"}
        return self.purge(lang=lang)

    def room_given(self, room, lang):
        return self.install("--admin-user", ADMIN, "--room-id", room, lang=lang)

    TABLE = (
        ("docker_missing_on_linux", HUMAN),
        ("docker_missing_on_windows", HUMAN),
        ("daemon_stopped_on_linux", HUMAN),
        ("daemon_stopped_on_windows", HUMAN),
        ("compose_missing_on_linux", HUMAN),
        ("compose_missing_on_windows", HUMAN),
        ("mkcert_missing_on_linux", HUMAN),
        ("mkcert_missing_on_windows", HUMAN),
        ("name_that_does_not_resolve_on_linux", HUMAN),
        ("name_that_does_not_resolve_on_windows", HUMAN),
        ("name_that_resolves_off_loopback", HUMAN),
        ("pip_that_fails", FAILED),
        ("libraries_that_never_come_back", FAILED),
        ("env_file_for_another_server", FAILED),
        ("env_file_without_the_server_name", FAILED),
        ("toml_with_the_example_token", FAILED),
        ("toml_without_a_token_line", FAILED),
        ("toml_with_an_empty_token", FAILED),
        ("server_that_never_answers", FAILED),
        ("compose_that_cannot_start", FAILED),
        ("untrusted_certificate_on_linux", HUMAN),
        ("untrusted_certificate_on_windows", HUMAN),
        ("broken_config", FAILED),
        ("no_admin_user", HUMAN),
        ("no_admin_password", HUMAN),
        ("toml_nobody_made", HUMAN),
        ("closed_registration", HUMAN),
        ("no_issued_token", HUMAN),
        ("manual_bots_on_a_hand_built_toml", HUMAN),
        ("bot_account_with_an_unknown_password", HUMAN),
        ("bot_account_with_a_wrong_saved_password", HUMAN),
        ("broker_port_of_another_value", FAILED),
        ("homeserver_address_of_another_server", FAILED),
        ("registration_that_the_server_keeps_open", FAILED),
        ("registration_to_close_on_a_hand_built_toml", HUMAN),
        ("registration_closed_on_a_hand_built_toml_without_a_restart", HUMAN),
        ("room_not_given", HUMAN),
        ("room_given_as_the_example", HUMAN),
        ("room_given_without_a_prefix", HUMAN),
        ("room_given_with_a_space", HUMAN),
        ("room_given_without_a_name", HUMAN),
        ("room_given_of_another_server", HUMAN),
        ("alias_given_without_a_server", HUMAN),
        ("room_given_after_another_was_stored", DONE),
        ("room_typed_in_a_terminal", DONE),
        ("room_asked_in_a_terminal_and_not_answered", HUMAN),
        ("config_without_the_room_key", FAILED),
        ("start_script_that_fails", FAILED),
        ("broker_that_stays_silent", FAILED),
        ("running_broker_beside_new_bot_tokens", DONE),
        ("whole_install", DONE),
        ("whole_install_asking_the_admin_user", DONE),
        ("whole_install_on_windows", DONE),
        ("first_account_that_becomes_the_administrator", DONE),
        ("remove_everything", DONE),
        ("remove_everything_on_windows", DONE),
        ("remove_a_hand_built_stand", DONE),
        ("remove_with_the_daemon_down", DONE),
        ("remove_with_a_broken_down", FAILED),
        ("remove_with_a_failing_stop_script", FAILED),
        ("remove_with_a_broker_that_never_stops", FAILED),
        ("remove_from_inside_the_venv", HUMAN),
        ("purge_everything", DONE),
        ("purge_refused", CANCELLED),
        ("purge_with_the_daemon_down", FAILED),
        ("purge_with_a_volume_in_use", FAILED),
    )

    def run_fresh(self, name, lang):
        self.setUp()
        return getattr(self, name)(lang)

    def test_the_table_names_real_scenarios(self):
        for name, _ in self.TABLE:
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(self, name)))

    def test_the_installers_own_words_are_english_in_every_scenario(self):
        for name, expected in self.TABLE:
            with self.subTest(name=name):
                code, given = self.run_fresh(name, "en")
                self.assertEqual(code, expected, given.stderr.getvalue())
                shown = given.stdout.getvalue() + given.stderr.getvalue()
                self.assertTrue(shown)
                self.assertIsNone(CYRILLIC.search(shown), shown)

    def test_every_scenario_ends_the_same_way_in_both_languages(self):
        for name, expected in self.TABLE:
            with self.subTest(name=name):
                seen = {}
                for lang in LANGUAGES:
                    code, given = self.run_fresh(name, lang)
                    seen[lang] = (code, self.spy.completed_steps)
                    self.assertEqual(code, expected, given.stderr.getvalue())
                self.assertEqual(seen["en"], seen["ru"])

    def test_the_steps_a_stopped_run_changed_are_stable_english_keys_in_russian(self):
        self.run_fresh("untrusted_certificate_on_linux", "ru")
        self.assertEqual(
            self.spy.completed_steps,
            [
                "create_venv",
                "issue_certificate",
                "create_env_file",
                "create_toml_file",
            ],
        )

    def test_a_removal_completes_the_stable_keys_of_the_removal_steps(self):
        self.run_fresh("remove_everything", "ru")
        self.assertEqual(self.spy.completed_steps, ["stop_stand", "remove_venv"])

    def test_a_purge_completes_the_stable_keys_of_every_purge_step(self):
        self.installed_in("ru")
        self.write_state()
        self.purge(lang="ru")
        self.assertEqual(
            self.spy.completed_steps,
            [
                "stop_stand",
                "remove_venv",
                "remove_broker_state",
                "remove_stand_config",
                "remove_certificates",
                "remove_saved_passwords",
                "remove_stand_volumes",
            ],
        )

    def test_a_whole_install_completes_the_stable_keys_of_the_second_half(self):
        self.run_fresh("whole_install", "ru")
        self.assertEqual(
            self.spy.completed_steps[-4:],
            [
                "create_bot_accounts",
                "close_registration",
                "write_room",
                "start_stand",
            ],
        )


class EnglishOutputTests(ServerLanguageCase):
    def test_a_missing_docker_is_told_in_english_with_the_command(self):
        self.machine.present["docker"] = False
        code, given = self.install(platform="windows", lang="en")
        self.assertEqual(code, HUMAN)
        self.assertIn(
            "Install Docker Desktop: winget install Docker.DockerDesktop, start it "
            "and run this again.",
            self.stdout(given),
        )
        self.assertIn('Stopped at step "Find Docker"', self.stderr(given))

    def test_the_step_names_are_rendered_in_english(self):
        self.machine.present["mkcert"] = False
        _, given = self.install(lang="en")
        self.assertIn("Check Compose v2: already done.", self.stdout(given))

    def test_a_repeated_step_is_named_in_english_as_already_done(self):
        self.everything(lang="en")
        self.everything(lang="en")
        self.assertIn(
            "Check the server name: already done.", self.stdout(self.last_given)
        )

    def test_a_failed_venv_is_told_in_english_around_the_tools_last_line(self):
        self.machine.fail_pip = True
        code, given = self.everything(lang="en")
        self.assertEqual(code, FAILED)
        self.assertIn(
            "Reason: bridge/.venv could not be built: Could not find a version",
            self.stderr(given),
        )
        self.assertIn('Failed at step "Create bridge/.venv".', self.stderr(given))

    def test_a_helper_failure_names_the_command_the_code_and_the_line_in_english(self):
        self.machine.missing_import = 99
        code, given = self.everything(lang="en")
        self.assertEqual(code, FAILED)
        self.assertIn(
            "Reason: bridge/.venv failed at imports: code=aiohttp.", self.stderr(given)
        )

    def test_a_server_that_never_answers_is_told_in_english(self):
        self.probe_status = None
        code, given = self.everything(lang="en")
        self.assertEqual(code, FAILED)
        self.assertIn(f"{SERVER_NAME} did not answer within 60s: ", self.stderr(given))
        self.assertIn(". See docker compose -f", self.stderr(given))
        self.assertIn("logs continuwuity.", self.stderr(given))

    def test_a_compose_that_cannot_start_is_told_in_english_around_its_own_words(self):
        self.machine.fail_up = "443/tcp: address already in use"
        code, given = self.everything(lang="en")
        self.assertEqual(code, FAILED)
        self.assertIn(
            "Reason: docker compose up -d ended with code 1: "
            "443/tcp: address already in use",
            self.stderr(given),
        )

    def test_a_compose_that_says_nothing_is_told_as_no_output_in_english(self):
        self.machine.fail_up = " "
        code, given = self.everything(lang="en")
        self.assertEqual(code, FAILED)
        self.assertIn(
            "Reason: docker compose up -d ended with code 1: no output",
            self.stderr(given),
        )

    def test_a_conflicting_env_file_is_told_in_english(self):
        self.path("docker/.env").write_text(
            "SERVER_NAME=other.local\n", encoding="utf-8"
        )
        code, given = self.install(lang="en")
        self.assertEqual(code, FAILED)
        self.assertIn(
            "line 1 sets SERVER_NAME=other.local, but the stack is set up for "
            f"{SERVER_NAME}.",
            self.stderr(given),
        )

    def test_a_toml_without_the_token_is_told_in_english(self):
        self.hand_built_toml("[global]\nallow_registration = true\n")
        _, given = self.install(lang="en")
        self.assertIn(
            "there is no registration_token line, add it by hand.", self.stderr(given)
        )

    def test_a_toml_with_an_empty_value_is_told_in_english(self):
        self.hand_built_toml(
            '[global]\nallow_registration = true\nregistration_token = ""\n'
        )
        _, given = self.install(lang="en")
        self.assertIn(
            "line 3 (registration_token) is empty, fill it in by hand.",
            self.stderr(given),
        )

    def test_a_toml_with_the_example_token_is_told_in_english(self):
        self.copy_example("docker/continuwuity/continuwuity.toml.example", self.toml())
        _, given = self.install(lang="en")
        self.assertIn(
            "registration_token is still the example from "
            f"{server.TOML_EXAMPLE}, replace it with your own.",
            self.stderr(given),
        )

    def test_a_hand_built_toml_is_a_human_step_in_english(self):
        self.hand_built_toml(
            '[global]\nallow_registration = true\nregistration_token = "mine"\n'
        )
        code, given = self.everything(lang="en")
        self.assertEqual(code, HUMAN)
        self.assertIn("was not created by this installer", self.stdout(given))

    def test_a_missing_admin_user_names_the_flag_in_english(self):
        code, given = self.install("--room-id", ROOM, lang="en")
        self.assertEqual(code, HUMAN)
        self.assertIn("Run again with --admin-user <name>.", self.stdout(given))

    def test_a_missing_password_names_the_variable_in_english(self):
        code, given = self.everything(
            env={"PATH": "", "HOME": str(self.home)}, lang="en"
        )
        self.assertEqual(code, HUMAN)
        self.assertIn(
            f"Set the variable {server.PASSWORD_VARIABLE} or run the installer in a "
            "terminal",
            self.stdout(given),
        )

    def test_a_closed_registration_names_the_setting_in_english(self):
        self.machine.registration_open = False
        code, given = self.everything(lang="en")
        self.assertEqual(code, HUMAN)
        self.assertIn(
            "The server does not accept registrations (HTTP 403)", self.stdout(given)
        )
        self.assertIn("Set allow_registration = true in", self.stdout(given))

    def test_a_server_without_a_printed_token_names_the_log_command_in_english(self):
        self.machine.only_issued = True
        self.machine.log_has_token = False
        code, given = self.everything(lang="en")
        self.assertEqual(code, HUMAN)
        self.assertIn(
            "The server did not print its registration token.", self.stdout(given)
        )

    def test_the_question_about_the_admin_user_is_asked_in_english(self):
        code, given = self.install(
            "--room-id", ROOM, stdin=f"{ADMIN}\n", interactive=True, lang="en"
        )
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertEqual(
            self.stdout(given).count(
                "Name of the local account the human will sign in to Element with: "
            ),
            1,
        )

    def test_the_password_prompt_is_in_the_language_of_the_run(self):
        seen = {}
        for lang in LANGUAGES:
            self.setUp()
            prompts = []
            code, given = self.everything(
                env={"PATH": "", "HOME": str(self.home)},
                interactive=True,
                secret=lambda prompt: prompts.append(prompt) or "typed",
                lang=lang,
            )
            self.assertEqual(code, DONE, self.stderr(given))
            seen[lang] = prompts
        self.assertEqual(seen["en"], ["Password of the human account: "])
        self.assertEqual(seen["ru"], ["Пароль аккаунта человека: "])

    def test_the_flag_switches_a_run_that_started_english_to_russian(self):
        self.machine.present["docker"] = False
        code, given = self.install("--lang", "ru", lang="en")
        self.assertEqual(code, HUMAN)
        self.assertIn("Найти Docker", self.stderr(given))


class InstructionTests(ServerLanguageCase):
    def run_of(self, lang, platform="linux", **values):
        return self.run_for(self.given(lang=lang, platform=platform, **values))

    def test_the_hosts_instruction_on_linux_in_english(self):
        self.assertEqual(
            hosts_instruction(self.run_of("en")),
            f'Add the line "127.0.0.1 {SERVER_NAME}" to /etc/hosts (as root): the '
            f"name {SERVER_NAME} must resolve to the loopback address, otherwise "
            "the stand on the host will answer instead of the stack.",
        )

    def test_the_hosts_instruction_on_windows_in_english(self):
        self.assertEqual(
            hosts_instruction(self.run_of("en", "windows")),
            f'Add the line "127.0.0.1 {SERVER_NAME}" to {HOSTS_WINDOWS} (as '
            f"administrator): the name {SERVER_NAME} must resolve to the loopback "
            "address, otherwise the stand on the host will answer instead of the "
            "stack.",
        )

    def test_the_hosts_instruction_on_linux_in_russian_is_what_was_printed_before(self):
        self.assertEqual(
            hosts_instruction(self.run_of("ru")),
            f"Добавьте строку «127.0.0.1 {SERVER_NAME}» в /etc/hosts (от root): имя "
            f"{SERVER_NAME} должно резолвиться в адрес петли, иначе стенд на хосте "
            "ответит вместо стека.",
        )

    def test_the_hosts_instruction_on_windows_in_russian_is_what_was_printed_before(
        self,
    ):
        self.assertEqual(
            hosts_instruction(self.run_of("ru", "windows")),
            f"Добавьте строку «127.0.0.1 {SERVER_NAME}» в {HOSTS_WINDOWS} (от имени "
            f"администратора): имя {SERVER_NAME} должно резолвиться в адрес петли, "
            "иначе стенд на хосте ответит вместо стека.",
        )

    def test_the_trust_instruction_on_windows_in_english(self):
        self.assertEqual(
            trust_instruction(self.run_of("en", "windows"), ""),
            f"The browser and the broker must trust the certificate of {SERVER_NAME}. "
            "Run as administrator: mkcert -install. After that, run the same "
            "command again.",
        )

    def test_the_trust_instruction_on_linux_in_english_names_the_root_and_the_reason(
        self,
    ):
        run = self.run_of("en")
        self.assertEqual(
            trust_instruction(run, "certificate not verified"),
            f"The browser and the broker must trust the certificate of {SERVER_NAME}. "
            f'Run as administrator: CAROOT="{self.machine.caroot}" mkcert -install '
            "(as root). The server said: certificate not verified. After that, run "
            "the same command again.",
        )

    def test_the_trust_instruction_on_linux_in_russian_is_what_was_printed_before(self):
        run = self.run_of("ru")
        self.assertEqual(
            trust_instruction(run, "отказано"),
            f"Браузер и брокер должны доверять сертификату {SERVER_NAME}. Выполните "
            f'от администратора: CAROOT="{self.machine.caroot}" mkcert -install '
            "(от root). Сервер ответил: отказано. После этого повторите ту же "
            "команду.",
        )

    def test_the_trust_instruction_on_windows_in_russian_without_a_reason(self):
        self.assertEqual(
            trust_instruction(self.run_of("ru", "windows"), ""),
            f"Браузер и брокер должны доверять сертификату {SERVER_NAME}. Выполните "
            "от администратора: mkcert -install. После этого повторите ту же команду.",
        )

    def test_the_instructions_have_no_russian_in_english(self):
        for platform in ("linux", "windows"):
            run = self.run_of("en", platform)
            for said in (
                hosts_instruction(run),
                trust_instruction(run, ""),
                trust_instruction(run, "refused"),
            ):
                with self.subTest(platform=platform):
                    self.assertIsNone(CYRILLIC.search(said), said)


class FailureWordingTests(ServerLanguageCase):
    def run_of(self, lang):
        return self.run_for(self.given(lang=lang))

    def test_a_helper_failure_lists_only_the_facts_it_has(self):
        answers = {
            "en": "bridge/.venv failed at register: code=M_FORBIDDEN: HTTP=403: file=a.yaml: line=4.",
            "ru": "bridge/.venv не справилась с register: код=M_FORBIDDEN: HTTP=403: файл=a.yaml: строка=4.",
        }
        facts = {"errcode": "M_FORBIDDEN", "status": 403, "file": "a.yaml", "line": 4}
        for lang, expected in answers.items():
            with self.subTest(lang=lang):
                self.assertEqual(
                    host_failure(self.run_of(lang), "register", facts), expected
                )

    def test_a_helper_failure_without_facts_names_only_the_command(self):
        self.assertEqual(
            host_failure(self.run_of("en"), "imports", {}),
            "bridge/.venv failed at imports.",
        )
        self.assertEqual(
            host_failure(self.run_of("ru"), "imports", {}),
            "bridge/.venv не справилась с imports.",
        )

    def test_a_refused_helper_carries_the_message_and_the_answer(self):
        refused = HostRefused("message", {"status": 403})
        self.assertEqual(str(refused), "message")
        self.assertEqual(refused.answer, {"status": 403})

    def test_a_venv_failure_without_output_says_so_in_both_languages(self):
        silent = completed("", "", 1)
        self.assertEqual(
            venv_failure(self.run_of("en"), silent),
            "bridge/.venv could not be built: no output",
        )
        self.assertEqual(
            venv_failure(self.run_of("ru"), silent),
            "bridge/.venv не собралась: без вывода",
        )

    def test_a_mkcert_failure_keeps_the_tools_own_words(self):
        failed = completed("", "mkcert: no such luck", 1)
        self.assertEqual(
            mkcert_failure(self.run_of("en"), failed),
            "mkcert did not issue the certificate: mkcert: no such luck",
        )
        self.assertEqual(
            mkcert_failure(self.run_of("ru"), failed),
            "mkcert не выпустил сертификат: mkcert: no such luck",
        )

    def test_a_compose_failure_names_the_code_and_the_last_line_of_the_tool(self):
        failed = completed("first\nlast", "", 2)
        self.assertEqual(
            compose_failure(self.run_of("en"), "docker compose down", failed),
            "docker compose down ended with code 2: last",
        )
        self.assertEqual(
            compose_failure(self.run_of("ru"), "docker compose down", failed),
            "docker compose down закончился с кодом 2: last",
        )

    def test_the_mkcert_root_that_is_missing_is_told_in_both_languages(self):
        expected = {"en": "the mkcert root is missing", "ru": "нет корня mkcert"}
        for lang, phrase in expected.items():
            with self.subTest(lang=lang):
                with self.assertRaises(RuntimeError) as raised:
                    server.ca_bundle(self.run_of(lang))
                self.assertIn(phrase, str(raised.exception))

    def test_the_installer_logs_that_stay_are_told_in_both_languages(self):
        self.path("bridge/broker.log").write_text("log", encoding="utf-8")
        english = server.install_logs(self.run_of("en"))
        russian = server.install_logs(self.run_of("ru"))
        self.assertEqual(
            english[0].text,
            "the installer logs are left in place: the removal task card does not "
            "count them as part of the cleanup",
        )
        self.assertTrue(english[1].text.startswith("delete them: "))
        self.assertEqual(
            russian[0].text,
            "логи установщика остались: карточка снятия не относит их к очистке",
        )
        self.assertTrue(russian[1].text.startswith("удалить их: "))
        self.assertEqual(english[0].files, russian[0].files)


class SecretsInPlaceholdersTests(ServerLanguageCase):
    def token_leaking_probe(self):
        def probe(url: str) -> Probe:
            if url.endswith("/status"):
                return Probe(None, "connection refused")
            written = REGISTRATION_TOKEN.search(self.toml().read_text(encoding="utf-8"))
            return Probe(None, f"gateway echoed {written.group(1)}")

        return probe

    def test_a_registration_token_in_a_placeholder_is_hidden_in_both_languages(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                self.setUp()
                code, given = self.everything(
                    probe=self.token_leaking_probe(), lang=lang
                )
                self.assertEqual(code, FAILED)
                token = REGISTRATION_TOKEN.search(
                    self.toml().read_text(encoding="utf-8")
                ).group(1)
                shown = self.stdout(given) + self.stderr(given)
                self.assertNotIn(token, shown)
                self.assertIn(f"gateway echoed {HIDDEN[lang]}", shown)

    def test_a_start_failure_echoing_secrets_hides_them_in_both_languages(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                self.setUp()
                self.machine.only_issued = True
                self.machine.start_code = 1
                self.machine.stdout_log = (
                    f"start failed: password {PASSWORD}, bot token token-claude-code, "
                    f"issued token {server_tests.ISSUED}"
                )
                code, given = self.everything(
                    env={"PATH": "", "QUOROOM_ADMIN_PASSWORD": PASSWORD}, lang=lang
                )
                self.assertEqual(code, FAILED)
                shown = self.stdout(given) + self.stderr(given)
                for secret in (PASSWORD, "token-claude-code", server_tests.ISSUED):
                    self.assertNotIn(secret, shown)
                self.assertIn(f"start failed: password {HIDDEN[lang]}", shown)

    def test_a_password_in_a_human_step_is_hidden_in_both_languages(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                given = self.given(lang=lang)
                run = self.run_for(given)
                run.secrets.register(PASSWORD)
                self.assertEqual(execute([AsksForThePassword()], run), Outcome.HUMAN)
                self.assertNotIn(PASSWORD, self.stdout(given))
                self.assertIn(HIDDEN[lang], self.stdout(given))


class SecondHalfWordingTests(ServerLanguageCase):
    def run_of(self, lang, platform="linux"):
        return self.run_for(self.given(lang=lang, platform=platform))

    def told(self, build, english, russian, platform="linux"):
        for lang, expected in (("en", english), ("ru", russian)):
            with self.subTest(lang=lang):
                self.assertEqual(build(self.run_of(lang, platform)), expected)

    def compose(self) -> str:
        return str(server.compose_file(self.run_of("en")))

    def toml_file(self) -> str:
        return str(server.toml_path(self.run_of("en")))

    def config_file(self) -> str:
        return str(server.config_path(self.run_of("en")))

    def test_a_hand_built_toml_leaves_the_bots_to_the_human(self):
        config = self.config_file()
        self.told(
            server.manual_bots,
            "continuwuity.toml was not created by this installer, so the installer "
            "will not create the bots here. Enter the user_id, access_token and "
            f"device_id of each bot into {config} yourself - register_account.py "
            "shows the values.",
            "continuwuity.toml создан не этим установщиком, поэтому заводить ботов "
            "здесь он не будет. Впишите user_id, access_token и device_id каждого "
            f"бота в {config} сами - значения показывает register_account.py.",
        )

    def test_a_bot_with_an_unknown_password_is_told_in_both_languages(self):
        self.machine.accounts["claude-code"] = "someone-elses"
        _, english = self.everything(lang="en")
        self.assertIn(
            "The bot account claude-code already exists on the server, and the "
            "installer does not know its password: reset it in Element or delete "
            "the account, then run this again.",
            self.stdout(english),
        )
        self.setUp()
        self.machine.accounts["claude-code"] = "someone-elses"
        _, russian = self.everything(lang="ru")
        self.assertIn(
            "Аккаунт бота claude-code на сервере уже есть, а пароль от него "
            "установщику неизвестен: сбросьте его через Element или удалите "
            "аккаунт, затем повторите.",
            self.stdout(russian),
        )

    def test_a_bot_with_a_wrong_saved_password_is_told_in_both_languages(self):
        said = {}
        for lang in LANGUAGES:
            self.setUp()
            self.machine.accounts["claude-code"] = "someone-elses"
            self.accounts_file().parent.mkdir(parents=True, exist_ok=True)
            self.accounts_file().write_text(
                '{"claude-code": {"password": "saved"}}', encoding="utf-8"
            )
            _, given = self.everything(lang=lang)
            said[lang] = self.stdout(given)
        self.assertIn(
            "The saved password for claude-code did not fit the account on the "
            "server: bridge/.venv failed at login: code=M_FORBIDDEN: HTTP=403.. "
            "Reset the password in Element or delete the account, then run this "
            "again.",
            said["en"],
        )
        self.assertIn(
            "Сохранённый пароль для claude-code не подошёл к аккаунту на сервере: "
            "bridge/.venv не справилась с login: код=M_FORBIDDEN: HTTP=403.. "
            "Сбросьте пароль через Element или удалите аккаунт, затем повторите.",
            said["ru"],
        )

    def test_a_broker_port_of_another_value_is_told_in_both_languages(self):
        self.settled()
        self.edit_config({"sessionchat_port": 9999})
        config = self.config_file()
        self.told(
            server.broker_problem,
            f"{config} sets sessionchat_port=9999, but start.sh and start.ps1 bring "
            "the broker up on 8770, and the scripts must not be changed. Set "
            "sessionchat_port: 8770 in the configuration.",
            f"{config} задаёт sessionchat_port=9999, а start.sh и start.ps1 "
            "поднимают брокера на 8770, и скрипты менять нельзя. Поставьте в "
            "конфигурации sessionchat_port: 8770.",
        )

    def test_a_homeserver_address_of_another_server_is_told_in_both_languages(self):
        self.settled()
        self.edit_config({"homeserver_url": "https://elsewhere.example"})
        config = self.config_file()
        self.told(
            server.broker_problem,
            f"{config} sets homeserver_url=https://elsewhere.example, but the stack "
            f"is up at https://{SERVER_NAME}. Set homeserver_url: "
            f"https://{SERVER_NAME}.",
            f"{config} задаёт homeserver_url=https://elsewhere.example, а стек "
            f"поднят на https://{SERVER_NAME}. Поставьте homeserver_url: "
            f"https://{SERVER_NAME}.",
        )

    def test_a_fine_config_is_told_as_a_fine_config(self):
        self.settled()
        config = self.config_file()
        for lang, expected in (
            ("en", f"{config} is fine."),
            ("ru", f"{config} в порядке."),
        ):
            with self.subTest(lang=lang):
                given = self.given(lang=lang)
                with self.assertRaises(RuntimeError) as raised:
                    server.BrokerAddressStep().apply(self.run_for(given))
                self.assertEqual(str(raised.exception), expected)

    def test_a_registration_the_server_keeps_open_is_told_in_both_languages(self):
        compose = self.compose()
        self.told(
            server.closure_unconfirmed,
            "Registration is closed in the file, but the server did not confirm it: "
            "a trial registration with a deliberately wrong token was not refused "
            "with 403. Check that the container restarted with the new file, with "
            f'the command docker compose -f "{compose}" restart continuwuity.',
            "Регистрация закрыта в файле, но сервер этого не подтвердил: пробная "
            "регистрация с заведомо неверным токеном не получила отказ 403. "
            "Проверьте, что контейнер перезапустился с новым файлом, командой "
            f'docker compose -f "{compose}" restart continuwuity.',
        )

    def test_a_toml_to_edit_by_hand_is_told_in_both_languages(self):
        self.hand_built_toml("[global]\nallow_registration = true\n")
        toml, compose = self.toml_file(), self.compose()
        self.told(
            server.manual_close,
            "continuwuity.toml was not created by this installer, so the installer "
            "will not close registration here. Set allow_registration = false in "
            f'{toml} and run docker compose -f "{compose}" restart continuwuity.',
            "continuwuity.toml создан не этим установщиком, поэтому закрывать "
            "регистрацию здесь он не будет: Поставьте allow_registration = false в "
            f'{toml} и выполните docker compose -f "{compose}" restart continuwuity.',
        )

    def test_a_toml_closed_without_a_restart_is_told_in_both_languages(self):
        self.hand_built_toml("[global]\nallow_registration = false\n")
        toml, compose = self.toml_file(), self.compose()
        self.told(
            server.manual_close,
            f"{toml} already has allow_registration = false, but the server does "
            "not close registration: restart it with docker compose -f "
            f'"{compose}" restart continuwuity.',
            f"в {toml} уже стоит allow_registration = false, но сервер регистрацию "
            "не закрывает: перезапустите его командой docker compose -f "
            f'"{compose}" restart continuwuity.',
        )

    def test_every_refused_room_is_told_in_both_languages(self):
        alias = f"#alias:{SERVER_NAME}"
        cases = (
            (
                "",
                "The room identifier is not given.",
                "Не указан идентификатор комнаты.",
            ),
            (
                "agents",
                "The room identifier must start with ! or #, not with 'agents'.",
                "Идентификатор комнаты должен начинаться с ! или #, а не с 'agents'.",
            ),
            (
                "!ab cd",
                "The room identifier must not contain whitespace: '!ab cd'.",
                "В идентификаторе комнаты не должно быть пробела: '!ab cd'.",
            ),
            (
                "!:x",
                "The room identifier '!:x' has no name after ! or #.",
                "В идентификаторе комнаты '!:x' нет имени после ! или #.",
            ),
            (
                "#alias",
                "The room alias '#alias' must name the server: an alias is always "
                f"written as #name:{SERVER_NAME}.",
                "Псевдоним комнаты '#alias' должен называть сервер: псевдоним "
                f"всегда пишут как #имя:{SERVER_NAME}.",
            ),
            (
                "!a:elsewhere.example",
                "The room identifier '!a:elsewhere.example' points to the server "
                f"'elsewhere.example', but the stand runs on {SERVER_NAME}.",
                "Идентификатор комнаты '!a:elsewhere.example' указывает на сервер "
                f"'elsewhere.example', а стенд работает на {SERVER_NAME}.",
            ),
            (
                "!REPLACE_ME",
                "The room identifier is still the example from "
                "config.example.yaml: '!REPLACE_ME'.",
                "Идентификатор комнаты всё ещё пример из config.example.yaml: "
                "'!REPLACE_ME'.",
            ),
            (alias, "", ""),
        )
        for room, english, russian in cases:
            with self.subTest(room=room):
                self.told(lambda run: server.room_problem(run, room), english, russian)

    def test_the_room_instruction_names_the_invited_bots_in_both_languages(self):
        self.settled()
        who = f"@claude-code:{SERVER_NAME}, @opencode:{SERVER_NAME}"
        self.told(
            server.room_instruction,
            "Create a room in Element under your account and invite "
            f"{who} to it. The broker accepts the invitation itself. Then open "
            "Room settings -> Advanced -> Internal room ID and pass the value to "
            "the installer through --room-id as it is: it starts with !, and the "
            f"domain, if there is one, must be {SERVER_NAME}.",
            "Создайте комнату в Element под своим аккаунтом и пригласите в неё "
            f"{who}. Приглашение брокер примет сам. Затем Room settings -> "
            "Advanced -> Internal room ID, и передайте значение установщику через "
            "--room-id как есть: оно начинается с !, а домен, если он есть, должен "
            f"быть {SERVER_NAME}.",
        )

    def test_another_room_than_the_stored_one_is_warned_about_in_both_languages(self):
        said = {}
        for lang in LANGUAGES:
            self.setUp()
            self.everything(lang=lang)
            _, given = self.install(
                "--admin-user", ADMIN, "--room-id", "!AnotherRoom", lang=lang
            )
            said[lang] = self.masked(self.stderr(given))
        config = self.where("bridge/config.yaml")
        self.assertIn(
            f"config.yaml already holds the room {ROOM}, and this run was given "
            "!AnotherRoom. The first one is kept: the installer does not overwrite "
            f"a recorded value. Change room_id in {config} and run this again.",
            said["en"],
        )
        self.assertIn(
            f"В config.yaml уже стоит комната {ROOM}, а в этом запуске передана "
            "!AnotherRoom. Оставлена первая: записанное значение установщик сам не "
            f"затирает. Поменяйте room_id в {config} и повторите.",
            said["ru"],
        )

    def test_a_config_that_refuses_a_value_is_told_in_both_languages(self):
        said = {}
        for lang in LANGUAGES:
            self.setUp()
            self.config().write_text(
                'homeserver_url: "https://agentschat.local"\n', encoding="utf-8"
            )
            _, given = self.everything(lang=lang)
            said[lang] = self.masked(self.stderr(given))
        config = self.where("bridge/config.yaml")
        self.assertIn(f"{config}: could not write room_id.", said["en"])
        self.assertIn("Enter the values yourself and run this again.", said["en"])
        self.assertIn(f"{config}: записать room_id не вышло.", said["ru"])
        self.assertIn("Впишите значения сами и повторите.", said["ru"])


class StartAndStopWordingTests(ServerLanguageCase):
    def said_by(self, scenario, lang):
        self.setUp()
        _, given = scenario(lang)
        return self.masked(self.stdout(given) + self.stderr(given))

    def test_a_broker_that_stays_silent_is_told_in_both_languages(self):
        def silent(lang):
            return self.everything(
                probe=lambda url: (
                    Probe(None, "connection refused")
                    if url.endswith("/status")
                    else Probe(200, None)
                ),
                lang=lang,
            )

        self.assertIn(
            "Reason: The broker did not answer at http://127.0.0.1:8770/status "
            "within 15s. See bridge/broker.log and restart the stand.",
            self.said_by(silent, "en"),
        )
        self.assertIn(
            "Причина: Брокер не ответил на http://127.0.0.1:8770/status за 15с. "
            "Смотрите bridge/broker.log и перезапустите стенд.",
            self.said_by(silent, "ru"),
        )

    def test_a_failing_start_script_names_the_log_in_both_languages(self):
        def failing(lang):
            self.machine.start_code = 1
            self.machine.stdout_log = "start script failed here\n"
            return self.everything(lang=lang)

        log = self.where("bridge/logs/start.log")
        self.assertIn(
            "Reason: start script ended with code 1: start script failed here. "
            f"Full output: {log}",
            self.said_by(failing, "en"),
        )
        self.assertIn(
            "Причина: стартовый скрипт закончился с кодом 1: start script failed "
            f"here. Полный вывод: {log}",
            self.said_by(failing, "ru"),
        )

    def test_a_running_broker_beside_new_tokens_is_warned_about_in_both_languages(
        self,
    ):
        def running(lang):
            self.machine.broker_up = True
            self.config().write_text(
                self.path("bridge/config.example.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            self.edit_config({"room_id": ROOM}, owned=False)
            return self.everything(lang=lang)

        self.assertIn(
            "The broker already answers, and this run wrote the bot tokens: restart "
            "the stand by hand (stop and start) so that it picks up the new ones.",
            self.said_by(running, "en"),
        )
        self.assertIn(
            "Брокер уже отвечает, а токены ботов записал этот запуск: перезапустите "
            "стенд вручную (stop и start), чтобы он взял новые.",
            self.said_by(running, "ru"),
        )

    def test_a_failing_stop_script_names_the_log_in_both_languages(self):
        def failing(lang):
            self.everything(lang=lang)
            self.machine.stop_code = 1
            self.machine.stop_log = "stop script failed here"
            return self.remove(lang=lang)

        log = self.where("bridge/logs/stop.log")
        self.assertIn(
            "Reason: stop script ended with code 1: stop script failed here. "
            f"Full output: {log}",
            self.said_by(failing, "en"),
        )
        self.assertIn(
            "Причина: стоп-скрипт закончился с кодом 1: stop script failed here. "
            f"Полный вывод: {log}",
            self.said_by(failing, "ru"),
        )

    def test_a_broker_that_never_stops_names_the_script_in_both_languages(self):
        def stubborn(lang):
            self.everything(lang=lang)
            return self.remove(probe=lambda url: Probe(200, None), lang=lang)

        self.assertIn(
            "The broker did not stop answering at http://127.0.0.1:8770/status "
            "within 15s: stop it yourself with stop.sh and run this again.",
            self.said_by(stubborn, "en"),
        )
        self.assertIn(
            "Брокер не перестал отвечать на http://127.0.0.1:8770/status за 15с: "
            "остановите его сам stop.sh и повторите.",
            self.said_by(stubborn, "ru"),
        )

    def test_a_daemon_that_does_not_answer_is_warned_about_in_both_languages(self):
        def silent(lang):
            self.everything(lang=lang)
            self.machine.broker_up = False
            self.machine.present["daemon"] = False
            return self.remove(lang=lang)

        english = self.said_by(silent, "en")
        for phrase in (
            "The Docker daemon does not answer, the stand containers were not "
            "checked: there is nothing to take them down and make sure with, and "
            "the broker is already silent.",
            "the stand volumes are left in place: the Docker daemon does not "
            "answer, there is nothing to read them with.",
            "The stand containers are left in place: the Docker daemon did not "
            "answer, there was nothing to take them down with.",
        ):
            self.assertIn(phrase, english)
        russian = self.said_by(silent, "ru")
        for phrase in (
            "Docker-демон не отвечает, контейнеры стенда не проверены: снять их и "
            "убедиться нечем, а брокер уже молчит.",
            "тома стенда остались: Docker-демон не отвечает, прочитать их нечем.",
            "Контейнеры стенда остались: Docker-демон не отвечал, снять их было нечем.",
        ):
            self.assertIn(phrase, russian)

    def test_a_docker_that_cannot_be_started_is_warned_about_in_both_languages(self):
        compose_down = server.StopStandStep().down
        for lang, phrase in (
            ("en", "docker is not available, the stand was not taken down: boom"),
            ("ru", "docker недоступен, стенд не опущен: boom"),
        ):
            with self.subTest(lang=lang):
                given = self.given(lang=lang)
                given = replace(
                    given,
                    run=lambda argv, **kwargs: (_ for _ in ()).throw(OSError("boom")),
                )
                compose_down(self.run_for(given))
                self.assertIn(phrase, self.stderr(given))

    def test_a_daemon_that_stops_answering_after_down_is_warned_about(self):
        step = server.StopStandStep()
        for lang, phrase in (
            (
                "en",
                "The Docker daemon does not answer, the stand containers are left running.",
            ),
            ("ru", "Docker-демон не отвечает, контейнеры стенда остались поднятыми."),
        ):
            with self.subTest(lang=lang):
                self.setUp()
                self.everything(lang=lang)
                self.machine.present["daemon"] = False
                given = self.given(lang=lang)
                step.down(self.run_for(given))
                self.assertIn(phrase, self.stderr(given))

    def test_a_venv_under_the_installer_is_told_in_both_languages(self):
        interpreter = self.where("bridge/.venv/Scripts/python.exe")
        for lang, phrase in (
            (
                "en",
                "bridge/.venv cannot be removed: the installer is running on its "
                f"own interpreter {interpreter}. Leave this environment and run the "
                "same command again.",
            ),
            (
                "ru",
                "bridge/.venv убрать нельзя: установщик запущен её же "
                f"интерпретатором {interpreter}. Выйдите из этого окружения и "
                "повторите ту же команду.",
            ),
        ):
            with self.subTest(lang=lang):
                self.setUp()
                self.venv_python = self.venv() / "Scripts" / "python.exe"
                self.everything(lang=lang)
                code, given = self.remove(lang=lang)
                self.assertEqual(code, HUMAN)
                self.assertIn(phrase, self.masked(self.stdout(given)))


class PurgeWordingTests(ServerLanguageCase):
    def stopped_daemon(self, lang):
        self.everything(lang=lang)
        self.machine.broker_up = False
        self.machine.present["daemon"] = False
        return self.purge(lang=lang)

    def test_the_volumes_kept_by_a_silent_daemon_are_told_in_both_languages(self):
        _, english = self.stopped_daemon("en")
        self.assertIn(
            "the stand volumes are not deleted (docker_caddy-config, "
            "docker_caddy-data, docker_continuwuity-data): the Docker daemon does not "
            "answer and the containers are still running, so the files mounted "
            "into them are left in place too. Start Docker and run the same "
            "command again: the purge will finish the rest.",
            self.stderr(english),
        )
        self.setUp()
        _, russian = self.stopped_daemon("ru")
        self.assertIn(
            "тома стенда не удалены (docker_caddy-config, docker_caddy-data, "
            "docker_continuwuity-data): Docker-демон не отвечает, и контейнеры остались "
            "поднятыми, поэтому файлы, смонтированные в них, тоже оставлены. "
            "Запустите Docker и повторите ту же команду: очистка доделает остальное.",
            self.stderr(russian),
        )

    def test_a_file_the_running_stand_needs_is_told_in_both_languages(self):
        _, english = self.stopped_daemon("en")
        toml = self.where("docker/continuwuity/continuwuity.toml")
        self.assertIn(
            f"Remove the stand configuration: {toml} is left in place: the stand "
            "containers are up, and they need this file: it is mounted into them "
            "or defines the compose project.",
            self.masked(self.stderr(english)),
        )
        self.setUp()
        _, russian = self.stopped_daemon("ru")
        self.assertIn(
            f"Убрать конфигурацию стенда: {toml} оставлен: контейнеры стенда "
            "подняты, а этот файл им нужен: он смонтирован внутрь или задаёт "
            "проект compose.",
            self.masked(self.stderr(russian)),
        )

    def test_a_volume_in_use_is_told_in_both_languages(self):
        for lang, phrase in (
            ("en", ". The volume is left in the system."),
            ("ru", ". Том остался в системе."),
        ):
            with self.subTest(lang=lang):
                self.setUp()
                self.everything(lang=lang)
                self.machine.busy_volumes = {"docker_caddy-data"}
                code, given = self.purge(lang=lang)
                self.assertEqual(code, FAILED)
                self.assertIn(phrase, self.stderr(given))

    def test_the_consequence_of_each_kind_is_told_in_both_languages(self):
        files = [PurgeTarget(ROLE, "file", "a")]
        volumes = [PurgeTarget(ROLE, "volume", "docker_caddy-data")]
        venv = [PurgeTarget(ROLE, "venv", "b")]
        cases = (
            (
                files,
                "server configuration files will be gone; the conversation in the "
                "room on the server will stay in place.",
                "файлы конфигурации сервера исчезнут; переписка в комнате на сервере "
                "останется на месте.",
            ),
            (
                venv + volumes,
                "the bridge/.venv environment will be gone; the compose volumes "
                "with the room data will be gone: the conversation will be deleted "
                "for good.",
                "окружение bridge/.venv исчезнут; тома compose с данными комнаты "
                "исчезнут: переписка будет удалена безвозвратно.",
            ),
            (
                volumes,
                "the compose volumes with the room data will be gone: the "
                "conversation will be deleted for good.",
                "тома compose с данными комнаты исчезнут: переписка будет удалена "
                "безвозвратно.",
            ),
            (
                [PurgeTarget("participant", "session", "x")],
                "the conversation in the room on the server will stay in place.",
                "переписка в комнате на сервере останется на месте.",
            ),
        )
        for targets, english, russian in cases:
            with self.subTest(english=english):
                self.assertEqual(server_consequence(targets, "en"), english)
                self.assertEqual(server_consequence(targets, "ru"), russian)

    def test_a_purge_question_shows_the_server_consequence_in_both_languages(self):
        for lang, phrase in (
            ("en", "Consequence: "),
            ("ru", "Последствие: "),
        ):
            with self.subTest(lang=lang):
                self.setUp()
                self.everything(lang=lang)
                _, given = self.remove("--purge", stdin="\n", lang=lang)
                self.assertIn(phrase, self.stdout(given))


class ReportWordingTests(ServerLanguageCase):
    def reported(self, lang, **values):
        given = self.installed_in(lang, **values)
        return self.stdout(given)

    def test_the_install_report_is_told_in_english(self):
        shown = self.reported("en")
        self.assertIn("Broker for participants: http://127.0.0.1:8770", shown)
        self.assertIn(f"Matrix server and Element Web: https://{SERVER_NAME}", shown)
        self.assertIn(
            "To renew it: mkcert -cert-file "
            f"{self.path('docker/caddy/certs/agentschat.local.pem')} -key-file "
            f"{self.path('docker/caddy/certs/agentschat.local-key.pem')} "
            f'{SERVER_NAME}, then docker compose -f "'
            f'{self.path("docker/docker-compose.yml")}" restart caddy.',
            shown,
        )
        self.assertEqual(
            shown.splitlines()[-1],
            "Next, call /chatlogin in each CLI session. To stop everything: stop.sh",
        )

    def test_the_install_report_is_told_in_russian_as_before(self):
        shown = self.reported("ru")
        self.assertIn("Брокер для участников: http://127.0.0.1:8770", shown)
        self.assertIn(f"Сервер Matrix и Element Web: https://{SERVER_NAME}", shown)
        self.assertEqual(
            shown.splitlines()[-1],
            "Дальше в каждой сессии CLI вызвать /chatlogin. Остановить всё: stop.sh",
        )

    def test_the_windows_report_names_the_powershell_stop_script(self):
        for lang, last in (
            (
                "en",
                "Next, call /chatlogin in each CLI session. To stop everything: stop.ps1",
            ),
            (
                "ru",
                "Дальше в каждой сессии CLI вызвать /chatlogin. Остановить всё: stop.ps1",
            ),
        ):
            with self.subTest(lang=lang):
                self.setUp()
                shown = self.reported(lang, platform="windows")
                self.assertEqual(shown.splitlines()[-1], last)

    def test_the_first_account_becoming_an_administrator_is_told_in_both_languages(
        self,
    ):
        for lang, phrase in (
            (
                "en",
                "The first account became the server administrator and received an "
                "invitation to the admin room.",
            ),
            (
                "ru",
                "Первый аккаунт стал администратором сервера и получил приглашение "
                "в административную комнату.",
            ),
        ):
            with self.subTest(lang=lang):
                self.setUp()
                self.machine.only_issued = True
                self.assertIn(phrase, self.reported(lang))

    def test_the_certificate_expiry_is_told_in_both_languages(self):
        server_tests.RegistryTests.pem_with(
            self,
            validity=server_tests.der(
                0x30,
                server_tests.utc("260204120000Z") + server_tests.utc("290215304500Z"),
            ),
        )
        for lang, sentence in (
            ("en", "The certificate expires on 15.02.2029. To renew it: mkcert"),
            ("ru", "Сертификат истекает 15.02.2029. Обновить его: mkcert"),
        ):
            with self.subTest(lang=lang):
                self.assertIn(
                    sentence,
                    server.certificate_note(self.run_for(self.given(lang=lang))),
                )

    def test_a_removal_without_leftovers_is_told_in_both_languages(self):
        for lang, phrase in (
            ("en", "The stand is stopped, the server installation is removed."),
            ("ru", "Стенд остановлен, установка сервера снята."),
        ):
            with self.subTest(lang=lang):
                run = self.run_for(self.given(lang=lang))
                with patch.object(server, "kept_items", return_value=[]):
                    lines = server.removal_lines(run, server.Stand())
                self.assertEqual(lines[0], phrase)

    def test_a_removal_tells_what_it_left_in_english(self):
        self.everything(lang="en")
        self.path("bridge/broker.log").write_text("log", encoding="utf-8")
        _, given = self.remove(lang="en")
        shown = self.stdout(given)
        for phrase in (
            "Not everything was removed, left in the system:",
            "    installer records are left in place: --purge removes them",
            "    the compose volumes with the server data are left in place: "
            "--purge removes them",
            "    the installer logs are left in place: the removal task card does "
            "not count them as part of the cleanup",
            "The stand containers and its network are taken down although they "
            "were not recorded: they are not data, start creates and brings them "
            "up.",
            'CAROOT="' + str(self.home / "mkcert") + '" mkcert -uninstall (as root)',
            "but that will break all other mkcert certificates and leave files in",
            f'The line "127.0.0.1 {SERVER_NAME}" in /etc/hosts is left in place: '
            "remove it if the machine no longer needs the name.",
            "The stand images are left in place: ",
            "They are shared with other projects, so the installer does not "
            "delete them.",
            "To remove them: docker image rm ",
            "To install again: install.sh --role server",
        ):
            self.assertIn(phrase, shown)

    def test_a_removal_tells_what_it_left_in_russian_as_before(self):
        self.everything(lang="ru")
        _, given = self.remove(lang="ru")
        shown = self.stdout(given)
        for phrase in (
            "Убрано не всё, осталось в системе:",
            "    остались записи установщика: их удалит --purge",
            "    тома compose с данными сервера оставлены: их удалит --purge",
            "Контейнеры стенда и его сеть сняты, хотя они и не записывались: это "
            "не данные, их создаёт и поднимает start.",
            f"Строка «127.0.0.1 {SERVER_NAME}» в /etc/hosts осталась: уберите её, "
            "если имя больше не нужно машине.",
            "Образы стенда остались: ",
            ". Они общие для других проектов, поэтому установщик их не удаляет.",
            "Убрать их: docker image rm ",
            "Поставить обратно: install.sh --role server",
        ):
            self.assertIn(phrase, shown)

    def test_a_hand_built_stand_tells_what_it_left_in_both_languages(self):
        phrases = {
            "en": (
                "    left in place: the stand was built by hand, the installer did "
                "not record them",
                "    the stand volumes are not recorded by the installer, so they "
                "are left in place",
                "    the broker state is left in place: the broker creates these "
                "files, the installer does not record them and deletes them only "
                "next to a recorded continuwuity.toml",
            ),
            "ru": (
                "    остались: стенд собран вручную, установщик их не записывал",
                "    тома стенда не записаны за установщиком, поэтому оставлены",
                "    состояние брокера осталось: эти файлы создаёт брокер, "
                "установщик их не записывает и удаляет только рядом с записанным "
                "continuwuity.toml",
            ),
        }
        for lang, expected in phrases.items():
            with self.subTest(lang=lang):
                self.setUp()
                self.hand_built_toml("registration_token = 'x'\n")
                self.accounts_file().parent.mkdir(parents=True, exist_ok=True)
                self.accounts_file().write_text("{}", encoding="utf-8")
                self.write_state()
                self.machine.volumes = {"docker_continuwuity-data"}
                _, given = self.remove(lang=lang)
                for phrase in expected:
                    self.assertIn(phrase, self.stdout(given))

    def test_the_windows_removal_names_the_windows_hosts_file_and_the_entry(self):
        self.everything(lang="en", platform="windows")
        _, given = self.remove(platform="windows", lang="en")
        shown = self.stdout(given)
        self.assertIn(f"in {HOSTS_WINDOWS} is left in place", shown)
        self.assertIn("mkcert -uninstall", shown)
        self.assertNotIn("CAROOT", shown)
        self.assertIn("To install again: install.ps1 --role server", shown)


class HelpOfTheServerOptionsTests(ServerLanguageCase):
    def helped(self, lang):
        given = self.given(lang=lang)
        code = main(["--help"], given, self.roles())
        self.assertEqual(code, DONE)
        return " ".join(self.stdout(given).split())

    def test_the_server_options_are_described_in_english(self):
        shown = self.helped("en")
        self.assertIn("the human's local account in Element", shown)
        self.assertIn(f"room identifier, for example !AbCdEf:{SERVER_NAME}", shown)
        self.assertIsNone(CYRILLIC.search(shown), shown)

    def test_the_server_options_are_described_in_russian_as_before(self):
        shown = self.helped("ru")
        self.assertIn("локальный аккаунт человека в Element", shown)
        self.assertIn(f"идентификатор комнаты, например !AbCdEf:{SERVER_NAME}", shown)


class StableIdentityTests(unittest.TestCase):
    def names(self):
        role = server_role()
        steps = role.install + role.remove + role.purge
        return {step.name for step in steps}

    def test_no_two_steps_of_the_server_role_share_a_name(self):
        role = server_role()
        steps = role.install + role.remove + role.purge
        self.assertEqual(len(self.names()), len(steps))

    def test_the_old_russian_names_are_the_russian_labels(self):
        labels = {
            "create_bot_accounts": "Завести аккаунты ботов",
            "check_broker_address": "Проверить адрес брокера",
            "close_registration": "Закрыть регистрацию",
            "write_room": "Записать комнату",
            "start_stand": "Запустить стенд",
            "stop_stand": "Остановить брокер и стенд",
            "remove_venv": "Убрать bridge/.venv",
            "remove_broker_state": "Удалить состояние брокера",
            "remove_stand_config": "Убрать конфигурацию стенда",
            "remove_certificates": "Убрать сертификаты",
            "remove_saved_passwords": "Убрать сохранённые пароли",
            "remove_stand_volumes": "Удалить тома стенда",
        }
        for name, label in labels.items():
            with self.subTest(name=name):
                self.assertEqual(catalogue("ru")[f"{STEP_PREFIX}{name}"], label)
                self.assertIn(name, self.names())

    def test_every_migrated_server_step_name_is_a_stable_english_identifier(self):
        for name in self.names():
            with self.subTest(name=name):
                self.assertRegex(name, STABLE_STEP_NAME)

    def test_every_migrated_server_step_name_has_a_label_in_both_languages(self):
        for lang in LANGUAGES:
            for name in self.names():
                with self.subTest(lang=lang, name=name):
                    self.assertIn(f"{STEP_PREFIX}{name}", catalogue(lang))

    def test_the_labels_differ_between_the_languages(self):
        for name in self.names():
            with self.subTest(name=name):
                key = f"{STEP_PREFIX}{name}"
                self.assertNotEqual(catalogue("en")[key], catalogue("ru")[key])

    def test_every_server_message_is_used_by_the_module(self):
        source = Path(server.__file__).read_text(encoding="utf-8")
        used = set(SERVER_KEY.findall(source))
        defined = {key for key in catalogue("en") if key.startswith("server.")}
        self.assertEqual(defined - used, set(), "messages nobody prints")
        self.assertEqual(used - defined, set(), "messages nobody wrote")

    def test_the_kinds_of_the_purge_consequence_are_catalogued_in_both_languages(self):
        for lang in LANGUAGES:
            for kind, key in KIND_WORDS.items():
                with self.subTest(lang=lang, kind=kind):
                    self.assertIn(key, catalogue(lang))

    def test_the_consequence_names_the_kinds_in_the_language(self):
        targets = [PurgeTarget(ROLE, "cert", "a"), PurgeTarget(ROLE, "state", "b")]
        self.assertIn("certificates, broker state", server_consequence(targets, "en"))
        self.assertIn(
            "сертификаты, состояние брокера", server_consequence(targets, "ru")
        )


class AskedAdminUserTests(ServerLanguageCase):
    def test_the_question_is_said_once_in_the_language_of_the_run(self):
        words = {
            "en": "Name of the local account the human will sign in to Element with: ",
            "ru": "Имя локального аккаунта человека, под которым он войдёт в Element: ",
        }
        for lang, question in words.items():
            with self.subTest(lang=lang):
                given = self.given(lang=lang, stdin=f"{ADMIN}\n", interactive=True)
                run = self.run_for(given)
                self.assertEqual(asked_admin_user(run), ADMIN)
                self.assertEqual(self.stdout(given), question + "\n")


if __name__ == "__main__":
    unittest.main()
