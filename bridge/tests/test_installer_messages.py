"""Карточка installer-bilingual: каталог сообщений, его полнота и чистота кода."""

import json
import re
import string
import unittest
from pathlib import Path
from unittest.mock import patch

from sessionchat.installer import catalogue as catalogue_module
from sessionchat.installer.catalogue import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    STEP_PREFIX,
    catalogue,
    has,
    step_label,
    text,
)
from sessionchat.installer.main import PREPARE, REPORT
from sessionchat.installer.roles import built_in_roles
from sessionchat.installer.steps import Plan

INSTALLER = Path(catalogue_module.__file__).resolve().parent
MESSAGES = INSTALLER / "messages"

CYRILLIC = re.compile("[Ѐ-ӿ]")
PRINTABLE_ASCII = re.compile(r"[\x20-\x7e\n]*")

PLANS = (
    (False, False),
    (True, False),
    (True, True),
)


def raw(lang: str) -> dict[str, str]:
    return json.loads((MESSAGES / f"{lang}.json").read_text(encoding="utf-8"))


def placeholders(template: str) -> set[str]:
    return {
        name.split(".")[0].split("[")[0]
        for _, name, _, _ in string.Formatter().parse(template)
        if name is not None
    }


def real_step_names() -> set[str]:
    return {
        step.name
        for role in built_in_roles()
        for remove, purge in PLANS
        for step in role.steps_for(Plan((role.name,), remove, purge))
    }


class CatalogueFilesTests(unittest.TestCase):
    def test_both_languages_are_shipped(self):
        self.assertEqual(LANGUAGES, ("en", "ru"))

    def test_english_is_the_default_language(self):
        self.assertEqual(DEFAULT_LANGUAGE, "en")

    def test_each_catalogue_is_a_flat_mapping_of_text_to_text(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                loaded = raw(lang)
                self.assertTrue(loaded)
                for key, value in loaded.items():
                    self.assertIsInstance(key, str)
                    self.assertIsInstance(value, str)
                    self.assertTrue(value, key)

    def test_the_two_catalogues_have_the_same_keys(self):
        english, russian = set(raw("en")), set(raw("ru"))
        self.assertEqual(english - russian, set(), "keys only in en.json")
        self.assertEqual(russian - english, set(), "keys only in ru.json")

    def test_each_key_has_the_same_placeholders_in_both_languages(self):
        english, russian = raw("en"), raw("ru")
        for key in english.keys() & russian.keys():
            with self.subTest(key=key):
                self.assertEqual(placeholders(english[key]), placeholders(russian[key]))

    def test_every_template_is_valid_for_str_format(self):
        for lang in LANGUAGES:
            for key, value in raw(lang).items():
                with self.subTest(lang=lang, key=key):
                    list(string.Formatter().parse(value))

    def test_the_english_catalogue_has_no_cyrillic(self):
        for key, value in raw("en").items():
            with self.subTest(key=key):
                self.assertIsNone(CYRILLIC.search(value))

    def test_the_english_catalogue_uses_only_ascii_punctuation(self):
        for key, value in raw("en").items():
            with self.subTest(key=key):
                self.assertIsNotNone(PRINTABLE_ASCII.fullmatch(value), repr(value))

    def test_keys_are_sorted_so_that_parallel_additions_merge(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                keys = list(raw(lang))
                self.assertEqual(keys, sorted(keys))

    def test_the_files_are_utf8_without_a_byte_order_mark(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                data = (MESSAGES / f"{lang}.json").read_bytes()
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
                data.decode("utf-8")


class RendererTests(unittest.TestCase):
    def test_a_named_placeholder_is_filled(self):
        self.assertEqual(text("en", "steps.done", step="Install"), "Install: done.")

    def test_the_same_key_renders_in_the_requested_language(self):
        self.assertEqual(text("ru", "steps.done", step="Шаг"), "Шаг: готово.")

    def test_an_unknown_key_raises(self):
        with self.assertRaises(KeyError):
            text("en", "no.such.key")

    def test_a_missing_placeholder_raises(self):
        with self.assertRaises(KeyError):
            text("en", "steps.done")

    def test_an_unknown_language_raises(self):
        with self.assertRaises(ValueError):
            text("xx", "steps.done", step="x")

    def test_a_missing_key_never_falls_back_to_another_language(self):
        with patch.object(
            catalogue_module, "catalogue", lambda lang: {"only.here": "x"}
        ):
            with self.assertRaises(KeyError):
                text("ru", "steps.done", step="x")

    def test_doubled_braces_render_as_literal_braces(self):
        with patch.object(
            catalogue_module, "catalogue", lambda lang: {"k": "{{raw}} {name}"}
        ):
            self.assertEqual(text("en", "k", name="n"), "{raw} n")

    def test_a_placeholder_value_is_not_interpreted_as_a_template(self):
        self.assertEqual(text("en", "steps.done", step="{step}"), "{step}: done.")

    def test_the_catalogue_is_loaded_once_per_language(self):
        self.assertIs(catalogue("en"), catalogue("en"))


class StepLabelTests(unittest.TestCase):
    def test_a_catalogued_step_name_is_rendered_in_the_language(self):
        self.assertEqual(step_label("en", "prepare"), "run preparation")
        self.assertEqual(step_label("ru", "prepare"), "подготовка запуска")

    def test_a_name_without_an_entry_is_shown_as_it_is(self):
        self.assertFalse(has("en", f"{STEP_PREFIX}поставить пакет"))
        self.assertEqual(step_label("en", "поставить пакет"), "поставить пакет")

    def test_the_steps_of_the_installer_itself_are_catalogued(self):
        for lang in LANGUAGES:
            for name in (PREPARE, REPORT):
                with self.subTest(lang=lang, name=name):
                    self.assertTrue(has(lang, f"{STEP_PREFIX}{name}"))


class RussianStaysInTheCatalogueTests(unittest.TestCase):
    def test_no_installer_module_has_cyrillic_outside_the_catalogue(self):
        for path in sorted(INSTALLER.rglob("*.py")):
            relative = path.relative_to(INSTALLER).as_posix()
            with self.subTest(module=relative):
                self.assertIsNone(
                    CYRILLIC.search(path.read_text(encoding="utf-8")),
                    f"{relative} still has Russian text",
                )


class StepNameCoverageTests(unittest.TestCase):
    def test_every_real_step_name_is_catalogued_in_both_languages(self):
        for name in sorted(real_step_names()):
            for lang in LANGUAGES:
                with self.subTest(lang=lang, name=name):
                    self.assertTrue(has(lang, f"{STEP_PREFIX}{name}"))


if __name__ == "__main__":
    unittest.main()
