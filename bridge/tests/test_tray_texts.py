"""Task tray-02: the ru/en string table and the choice of the tray language."""

import tempfile
import unittest
from pathlib import Path

from quoroomtray.language import tray_language
from quoroomtray.texts import TRAY_CATALOGUE, TrayTexts
from tests.catalogue_contract import CatalogueContract


class TrayCatalogueTests(CatalogueContract, unittest.TestCase):
    catalogue = TRAY_CATALOGUE


class TrayTextsTests(unittest.TestCase):
    def test_a_text_is_rendered_with_its_parameters(self):
        self.assertEqual("exit code 7", TrayTexts("en").text("tray.exit_code", code=7))

    def test_the_russian_table_renders_the_same_key_in_russian(self):
        self.assertEqual("Выход", TrayTexts("ru").text("tray.exit"))

    def test_an_unknown_language_is_refused_rather_than_guessed(self):
        with self.assertRaises(ValueError):
            TrayTexts("de").text("tray.exit")


class TrayLanguageTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.config = Path(directory.name, "config.yaml")

    def language_of(self, content: str | bytes) -> str:
        data = content.encode("utf-8") if isinstance(content, str) else content
        self.config.write_bytes(data)
        return tray_language(self.config)

    def test_ru_in_the_config_gives_russian(self):
        self.assertEqual("ru", self.language_of("room_id: x\nlanguage: ru\n"))

    def test_en_in_the_config_gives_english(self):
        self.assertEqual("en", self.language_of("language: en\n"))

    def test_a_quoted_ru_gives_russian_like_the_scripts_read_it(self):
        self.assertEqual("ru", self.language_of('language: "ru"  # room\n'))

    def test_any_other_value_gives_english(self):
        for value in ("de", "RU", "''", "42", "null"):
            with self.subTest(value=value):
                self.assertEqual("en", self.language_of(f"language: {value}\n"))

    def test_a_config_without_the_key_gives_english(self):
        self.assertEqual("en", self.language_of("room_id: x\n"))

    def test_a_missing_config_gives_english(self):
        self.assertEqual("en", tray_language(self.config))

    def test_a_config_that_is_not_valid_yaml_gives_english(self):
        self.assertEqual("en", self.language_of("language: [ru\n"))

    def test_a_config_that_is_not_utf8_gives_english(self):
        self.assertEqual("en", self.language_of(b"language: ru\n\xff\xfe"))

    def test_a_config_holding_a_list_gives_english(self):
        self.assertEqual("en", self.language_of("- language: ru\n"))


if __name__ == "__main__":
    unittest.main()
