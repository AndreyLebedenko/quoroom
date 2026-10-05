"""Карточка installer-bilingual: каталог сообщений, его полнота и чистота кода."""

import unittest
from pathlib import Path
from unittest.mock import patch

from sessionchat.installer import catalogue as catalogue_module
from sessionchat.installer.catalogue import (
    DEFAULT_LANGUAGE,
    INSTALLER_CATALOGUE,
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
from tests.catalogue_contract import CYRILLIC, CatalogueContract

INSTALLER = Path(catalogue_module.__file__).resolve().parent

PLANS = (
    (False, False),
    (True, False),
    (True, True),
)


def real_step_names() -> set[str]:
    return {
        step.name
        for role in built_in_roles()
        for remove, purge in PLANS
        for step in role.steps_for(Plan((role.name,), remove, purge))
    }


class CatalogueFilesTests(CatalogueContract, unittest.TestCase):
    catalogue = INSTALLER_CATALOGUE

    def test_both_languages_are_shipped(self):
        self.assertEqual(LANGUAGES, ("en", "ru"))

    def test_english_is_the_default_language(self):
        self.assertEqual(DEFAULT_LANGUAGE, "en")


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
