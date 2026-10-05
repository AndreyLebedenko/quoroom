"""Task english-release-02: the server install writes the room language."""

import re
import yaml

from sessionchat.i18n import DEFAULT_LANGUAGE, LANGUAGES
from sessionchat.installer.main import DONE
from tests.test_installer_server import ADMIN, ROOM, ServerCase

LANGUAGE_LINES = re.compile(r"^language:.*$", re.M)


class RoomLanguageInstallCase(ServerCase):
    def written(self) -> dict:
        return yaml.safe_load(self.config().read_text(encoding="utf-8"))

    def language_lines(self) -> list[str]:
        return LANGUAGE_LINES.findall(self.config().read_text(encoding="utf-8"))

    def installed_in(self, *flags: str):
        code, given = self.install(
            "--admin-user", ADMIN, "--room-id", ROOM, *flags, secret=lambda p: "typed"
        )
        self.assertEqual(code, DONE, self.stderr(given))
        return given


class FreshInstallTests(RoomLanguageInstallCase):
    def test_a_fresh_install_writes_the_installers_own_language(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.setUp()
                self.installed_in("--lang", language)
                self.assertEqual(self.written()["language"], language)

    def test_the_language_flag_may_use_the_equals_form(self):
        self.installed_in("--lang=ru")
        self.assertEqual(self.written()["language"], "ru")

    def test_a_fresh_install_in_the_installers_default_language_writes_english(self):
        code, given = self.install(
            "--admin-user",
            ADMIN,
            "--room-id",
            ROOM,
            secret=lambda p: "t",
            lang=DEFAULT_LANGUAGE,
        )
        self.assertEqual(code, DONE, self.stderr(given))
        self.assertEqual(self.written()["language"], "en")

    def test_the_boundary_language_is_what_the_install_writes(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                self.setUp()
                code, given = self.install(
                    "--admin-user",
                    ADMIN,
                    "--room-id",
                    ROOM,
                    secret=lambda p: "t",
                    lang=language,
                )
                self.assertEqual(code, DONE, self.stderr(given))
                self.assertEqual(self.written()["language"], language)

    def test_the_language_appears_in_the_file_exactly_once(self):
        self.installed_in("--lang", "ru")
        self.assertEqual(self.language_lines(), ["language: ru"])

    def test_the_rest_of_the_example_is_left_as_it_was(self):
        self.installed_in("--lang", "ru")
        example = yaml.safe_load(
            self.path("bridge/config.example.yaml").read_text(encoding="utf-8")
        )
        written = self.written()
        for key in ("homeserver_url", "verify_ssl", "sessionchat_port", "max_depth"):
            self.assertEqual(written[key], example[key])

    def test_the_ownership_record_is_the_same_in_both_languages(self):
        self.installed_in("--lang", "en")
        english = self.recorded()
        self.setUp()
        self.installed_in("--lang", "ru")
        self.assertEqual(
            [kind for kind, _ in self.recorded()], [kind for kind, _ in english]
        )
        self.assertIn(("file", str(self.config())), self.recorded())


class ExistingConfigTests(RoomLanguageInstallCase):
    def existing(self, body: str) -> None:
        self.config().write_text(body, encoding="utf-8")

    def test_an_existing_value_survives_an_install_in_the_other_language(self):
        for stored, installer in (("ru", "en"), ("en", "ru")):
            with self.subTest(stored=stored, installer=installer):
                self.setUp()
                self.configure()
                self.edit_config({"language": stored})
                self.installed_in("--lang", installer)
                self.assertEqual(self.written()["language"], stored)

    def test_an_existing_config_without_the_key_is_not_given_one(self):
        self.existing(f'homeserver_url: "agentschat.local"\nroom_id: "{ROOM}"\n')
        self.install("--admin-user", ADMIN, "--room-id", ROOM, lang="ru")
        self.assertEqual(self.language_lines(), [])

    def test_a_rerun_never_flips_a_room_to_another_language(self):
        self.installed_in("--lang", "ru")
        self.installed_in("--lang", "en")
        self.installed_in("--lang", "en")
        self.assertEqual(self.written()["language"], "ru")

    def test_a_rerun_leaves_the_config_byte_for_byte_alone(self):
        self.installed_in("--lang", "ru")
        before = self.config().read_bytes()
        self.installed_in("--lang", "ru")
        self.assertEqual(self.config().read_bytes(), before)

    def test_a_rerun_records_the_config_once(self):
        self.installed_in("--lang", "ru")
        self.installed_in("--lang", "en")
        files = [id for kind, id in self.recorded() if id == str(self.config())]
        self.assertEqual(files, [str(self.config())])
