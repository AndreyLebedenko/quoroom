"""Task english-release-17: register_account.py speaks English, and Russian on request."""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import register_account
import requests
from tests.catalogue_contract import CYRILLIC, CatalogueContract

BRIDGE = Path(__file__).resolve().parent.parent

REQUIRED = [
    "--homeserver",
    "https://agentschat.local",
    "--username",
    "bot",
    "--password",
    "pw",
    "--registration-token",
    "rt",
]
ACCOUNT = {
    "user_id": "@bot:agentschat.local",
    "access_token": "tok",
    "device_id": "DEV",
}
ACCOUNT_JSON = (
    '{\n  "user_id": "@bot:agentschat.local",\n  "access_token": "tok",\n'
    '  "device_id": "DEV"\n}\n'
)
YAML_BLOCK = 'user_id: "@bot:agentschat.local"\naccess_token: "tok"\ndevice_id: "DEV"\n'
CA_LINE = '    --ca-bundle "$(mkcert -CAROOT)\\rootCA.pem"\n'

OUTPUT = {
    "en": {
        "pasted": ACCOUNT_JSON
        + "\n--- paste into bridge/config.yaml ---\n"
        + YAML_BLOCK,
        "step_one": "Unexpected response at step 1: 500 boom\n",
        "no_session": "The server's response has no session: {}\n",
        "failed": "Registration failed: 403 refused\n",
        "certificate": (
            "\nCertificate verification failed. requests does not read the Windows "
            "system store where mkcert -install puts its root. Add:\n"
            + CA_LINE
            + "to the same command and run it again.\n"
        ),
    },
    "ru": {
        "pasted": ACCOUNT_JSON
        + "\n--- вставить в bridge/config.yaml ---\n"
        + YAML_BLOCK,
        "step_one": "Неожиданный ответ на шаге 1: 500 boom\n",
        "no_session": "В ответе сервера нет session: {}\n",
        "failed": "Регистрация не удалась: 403 refused\n",
        "certificate": (
            "\nОшибка проверки сертификата. requests не читает системное хранилище "
            "Windows, куда mkcert -install кладёт свой корень. Добавьте:\n"
            + CA_LINE
            + "к этой же команде и запустите заново.\n"
        ),
    },
}
HELP_LINES = {
    "en": (
        "Register an account on Continuwuity",
        "for example https://agentschat.local",
        "localpart, for example claude-code",
        'path to rootCA.pem from mkcert, for example "$(mkcert -CAROOT)\\rootCA.pem"',
        "turn certificate verification off completely (blunter than --ca-bundle)",
        "language of the messages (default: en)",
    ),
    "ru": (
        "Регистрация аккаунта на Continuwuity",
        "например https://agentschat.local",
        "localpart, например claude-code",
        'путь к rootCA.pem из mkcert, например "$(mkcert -CAROOT)\\rootCA.pem"',
        "полностью отключить проверку сертификата (грубее, чем --ca-bundle)",
        "язык сообщений (по умолчанию: en)",
    ),
}


class Reply:
    def __init__(self, status: int, body: dict | None = None, text: str = ""):
        self.status_code = status
        self._body = body if body is not None else {}
        self.text = text or str(self._body)

    def json(self):
        return self._body


def run(argv: list[str], replies=None, failure=None):
    posts = []

    def post(url, json=None, verify=None):
        posts.append({"url": url, "json": json, "verify": verify})
        if failure is not None:
            raise failure
        return replies.pop(0)

    out, err = io.StringIO(), io.StringIO()
    code = 0
    with (
        patch.object(register_account.requests, "post", post),
        redirect_stdout(out),
        redirect_stderr(err),
    ):
        try:
            register_account.main(argv)
        except SystemExit as stop:
            code = stop.code
    return code, out.getvalue(), err.getvalue(), posts


def with_language(language: str | None) -> list[str]:
    return REQUIRED + ([] if language is None else ["--lang", language])


class RegistrationInEachLanguageTests(unittest.TestCase):
    def check_each_language(self, replies, expected_key, stream, code):
        for language in ("en", "ru"):
            with self.subTest(language=language):
                got_code, out, err, _ = run(with_language(language), replies())
                self.assertEqual(code, got_code)
                shown = {"out": out, "err": err}
                self.assertEqual(OUTPUT[language][expected_key], shown[stream])
                other = {"out": err, "err": out}[stream]
                self.assertEqual("", other)

    def test_a_server_that_registers_at_once_prints_the_account_and_the_yaml(self):
        self.check_each_language(lambda: [Reply(200, ACCOUNT)], "pasted", "out", 0)

    def test_the_two_step_registration_prints_the_account_and_the_yaml(self):
        self.check_each_language(
            lambda: [Reply(401, {"session": "S1"}), Reply(200, ACCOUNT)],
            "pasted",
            "out",
            0,
        )

    def test_an_unexpected_answer_at_step_one_is_refused(self):
        self.check_each_language(
            lambda: [Reply(500, text="boom")], "step_one", "err", 1
        )

    def test_an_answer_without_a_session_is_refused(self):
        self.check_each_language(
            lambda: [Reply(401, {}, text="{}")], "no_session", "err", 1
        )

    def test_a_refusal_at_step_two_is_refused(self):
        self.check_each_language(
            lambda: [Reply(401, {"session": "S1"}), Reply(403, text="refused")],
            "failed",
            "err",
            1,
        )

    def test_a_certificate_failure_explains_mkcert(self):
        for language in ("en", "ru"):
            with self.subTest(language=language):
                code, out, err, _ = run(
                    with_language(language), failure=requests.exceptions.SSLError()
                )
                self.assertEqual(1, code)
                self.assertEqual("", out)
                self.assertEqual(OUTPUT[language]["certificate"], err)


class DefaultLanguageTests(unittest.TestCase):
    def test_without_the_flag_every_message_is_english(self):
        replies = {
            "pasted": [Reply(200, ACCOUNT)],
            "step_one": [Reply(500, text="boom")],
            "no_session": [Reply(401, {}, text="{}")],
            "failed": [Reply(401, {"session": "S1"}), Reply(403, text="refused")],
        }
        for key, queue in replies.items():
            with self.subTest(key):
                _, out, err, _ = run(REQUIRED, queue)
                self.assertEqual(OUTPUT["en"][key], out + err)

    def test_the_english_default_has_no_cyrillic_in_what_it_prints(self):
        _, out, err, _ = run(REQUIRED, failure=requests.exceptions.SSLError())
        self.assertIsNone(CYRILLIC.search(out + err))

    def test_a_language_other_than_en_or_ru_is_refused(self):
        code, out, err, posts = run(with_language("de"))
        self.assertEqual(2, code)
        self.assertEqual([], posts)
        self.assertIn("--lang", err)

    def test_the_language_flag_may_come_before_the_other_options(self):
        _, out, _, _ = run(["--lang", "ru"] + REQUIRED, [Reply(200, ACCOUNT)])
        self.assertIn("--- вставить в bridge/config.yaml ---", out)


class DataIsNotTranslatedTests(unittest.TestCase):
    def test_the_yaml_block_and_the_json_are_the_same_in_both_languages(self):
        printed = {}
        for language in ("en", "ru"):
            _, out, _, _ = run(with_language(language), [Reply(200, ACCOUNT)])
            before_heading, yaml_part = out.rsplit("---\n", 1)
            json_part = before_heading.split("\n\n")[0] + "\n"
            printed[language] = (json_part, yaml_part)
        self.assertEqual(printed["en"], printed["ru"])
        self.assertEqual((ACCOUNT_JSON, YAML_BLOCK), printed["en"])

    def test_the_json_printed_keeps_non_ascii_text_of_the_server(self):
        account = dict(ACCOUNT, display_name="Ж")
        _, out, _, _ = run(REQUIRED, [Reply(200, account)])
        self.assertIn('"display_name": "Ж"', out)


class RequestsAreUnchangedTests(unittest.TestCase):
    def test_the_two_steps_post_the_same_bodies_in_either_language(self):
        for language in ("en", "ru"):
            with self.subTest(language=language):
                _, _, _, posts = run(
                    with_language(language),
                    [Reply(401, {"session": "S1"}), Reply(200, ACCOUNT)],
                )
                url = "https://agentschat.local/_matrix/client/v3/register"
                base = {
                    "username": "bot",
                    "password": "pw",
                    "initial_device_display_name": "agentschat-bridge",
                }
                self.assertEqual(
                    [
                        {"url": url, "json": base, "verify": True},
                        {
                            "url": url,
                            "json": {
                                **base,
                                "auth": {
                                    "type": "m.login.registration_token",
                                    "token": "rt",
                                    "session": "S1",
                                },
                            },
                            "verify": True,
                        },
                    ],
                    posts,
                )

    def test_the_certificate_options_choose_what_requests_verifies(self):
        cases = {
            (): True,
            ("--ca-bundle", "root.pem"): "root.pem",
            ("--no-verify-ssl",): False,
            ("--ca-bundle", "root.pem", "--no-verify-ssl"): False,
        }
        for options, expected in cases.items():
            with self.subTest(options=options):
                _, _, _, posts = run(REQUIRED + list(options), [Reply(200, ACCOUNT)])
                self.assertEqual(expected, posts[0]["verify"])

    def test_the_device_name_and_a_trailing_slash_are_honoured(self):
        argv = [
            "--homeserver",
            "https://h/",
            "--username",
            "u",
            "--password",
            "p",
            "--registration-token",
            "t",
            "--device-name",
            "laptop",
        ]
        _, _, _, posts = run(argv, [Reply(200, ACCOUNT)])
        self.assertEqual("https://h/_matrix/client/v3/register", posts[0]["url"])
        self.assertEqual("laptop", posts[0]["json"]["initial_device_display_name"])


class HelpTests(unittest.TestCase):
    def help_text(self, language: str | None) -> str:
        argv = ["--help"] if language is None else ["--lang", language, "--help"]
        with patch.dict(os.environ, {"COLUMNS": "500"}):
            code, out, _, _ = run(argv)
        self.assertEqual(0, code)
        return out

    def test_the_help_is_english_by_default(self):
        text = self.help_text(None)
        self.assertIsNone(CYRILLIC.search(text))
        for line in HELP_LINES["en"]:
            self.assertIn(line, text)

    def test_the_help_is_russian_on_request_as_it_always_was(self):
        text = self.help_text("ru")
        for line in HELP_LINES["ru"]:
            self.assertIn(line, text)
        self.assertNotIn("Register an account", text)

    def test_the_help_lists_the_language_choices(self):
        self.assertIn("{en,ru}", self.help_text(None))


class StandaloneRunTests(unittest.TestCase):
    def test_the_script_runs_from_any_directory_without_a_python_path(self):
        env = {
            name: value for name, value in os.environ.items() if name != "PYTHONPATH"
        }
        with tempfile.TemporaryDirectory() as elsewhere:
            done = subprocess.run(
                [sys.executable, str(BRIDGE / "register_account.py"), "--help"],
                cwd=elsewhere,
                env=env,
                capture_output=True,
                encoding="utf-8",
            )
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Register an account on Continuwuity", done.stdout)


class RegisterCatalogueTests(CatalogueContract, unittest.TestCase):
    catalogue = register_account.CATALOGUE

    def test_it_sits_next_to_the_script(self):
        self.assertEqual(
            BRIDGE / "register_messages" / "ru.json",
            Path(str(self.catalogue.source("ru"))),
        )


if __name__ == "__main__":
    unittest.main()
