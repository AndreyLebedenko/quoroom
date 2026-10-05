"""Task english-release-01: the shared catalogue loader and its contract helper."""

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import sessionchat.i18n as i18n_module
from sessionchat.i18n import DEFAULT_LANGUAGE, LANGUAGES, Catalogue
from tests.catalogue_contract import (
    CatalogueContract,
    cyrillic_in_english,
    empty_values,
    files_with_byte_order_mark,
    key_differences,
    malformed_templates,
    non_ascii_in_english,
    placeholder_differences,
    unsorted_files,
)

BRIDGE = Path(__file__).resolve().parent.parent


class CatalogueDirectory(tempfile.TemporaryDirectory):
    def __enter__(self) -> "CatalogueDirectory":
        super().__enter__()
        return self

    def write(self, lang: str, content: str | dict) -> None:
        text = content if isinstance(content, str) else json.dumps(content)
        Path(self.name, f"{lang}.json").write_text(text, encoding="utf-8")

    def catalogue(self) -> Catalogue:
        return Catalogue.from_path(Path(self.name))


def written(english: dict, russian: dict) -> CatalogueDirectory:
    directory = CatalogueDirectory()
    directory.write("en", english)
    directory.write("ru", russian)
    return directory


class LanguageConstantsTests(unittest.TestCase):
    def test_both_languages_are_known(self):
        self.assertEqual(LANGUAGES, ("en", "ru"))

    def test_english_is_the_default_language(self):
        self.assertEqual(DEFAULT_LANGUAGE, "en")


class LoadingFromAPackageTests(unittest.TestCase):
    def test_a_package_directory_is_loaded_for_every_language(self):
        catalogue = Catalogue("sessionchat.installer", "messages")
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                self.assertIn("steps.done", catalogue.templates(lang))

    def test_a_missing_directory_fails_when_the_catalogue_is_created(self):
        with self.assertRaises(FileNotFoundError):
            Catalogue("sessionchat.installer", "no_such_messages")

    def test_the_same_language_is_the_same_mapping_every_time(self):
        catalogue = Catalogue("sessionchat.installer", "messages")
        self.assertIs(catalogue.templates("en"), catalogue.templates("en"))

    def test_the_loaded_mapping_cannot_be_changed(self):
        catalogue = Catalogue("sessionchat.installer", "messages")
        with self.assertRaises(TypeError):
            catalogue.templates("en")["steps.done"] = "x"


class LoadingFromADirectoryTests(unittest.TestCase):
    def test_a_missing_language_file_fails_when_the_catalogue_is_created(self):
        with CatalogueDirectory() as directory:
            directory.write("en", {"a": "A"})
            with self.assertRaises(FileNotFoundError):
                directory.catalogue()

    def test_a_missing_directory_fails_when_the_catalogue_is_created(self):
        with CatalogueDirectory() as directory:
            missing = Path(directory.name, "absent")
        with self.assertRaises(FileNotFoundError):
            Catalogue.from_path(missing)

    def test_a_file_that_is_not_json_fails_when_the_catalogue_is_created(self):
        with written({"a": "A"}, {"a": "B"}) as directory:
            directory.write("ru", "{not json")
            with self.assertRaises(ValueError):
                directory.catalogue()

    def test_a_file_with_a_byte_order_mark_fails_when_the_catalogue_is_created(self):
        with written({"a": "A"}, {"a": "B"}) as directory:
            Path(directory.name, "en.json").write_bytes(b'\xef\xbb\xbf{"a": "A"}')
            with self.assertRaises(ValueError):
                directory.catalogue()

    def test_a_file_that_is_not_a_flat_mapping_fails_when_the_catalogue_is_created(
        self,
    ):
        for content in ('["a"]', '{"a": {"b": "c"}}', '{"a": 1}'):
            with self.subTest(content=content):
                with written({"a": "A"}, {"a": "B"}) as directory:
                    directory.write("en", content)
                    with self.assertRaises(ValueError):
                        directory.catalogue()

    def test_an_unknown_language_raises(self):
        with written({"a": "A"}, {"a": "B"}) as directory:
            with self.assertRaises(ValueError):
                directory.catalogue().templates("xx")
            with self.assertRaises(ValueError):
                directory.catalogue().text("xx", "a")


class RenderingTests(unittest.TestCase):
    def test_a_named_placeholder_is_filled_in_the_requested_language(self):
        with written({"k": "Hello, {name}."}, {"k": "Привет, {name}."}) as directory:
            catalogue = directory.catalogue()
            self.assertEqual(catalogue.text("en", "k", name="Ann"), "Hello, Ann.")
            self.assertEqual(catalogue.text("ru", "k", name="Ann"), "Привет, Ann.")

    def test_has_tells_whether_a_key_exists_in_a_language(self):
        with written({"k": "K"}, {"k": "K", "r": "R"}) as directory:
            catalogue = directory.catalogue()
            self.assertTrue(catalogue.has("en", "k"))
            self.assertFalse(catalogue.has("en", "r"))
            self.assertTrue(catalogue.has("ru", "r"))

    def test_an_unknown_key_raises(self):
        with written({"k": "K"}, {"k": "K"}) as directory:
            with self.assertRaises(KeyError):
                directory.catalogue().text("en", "no.such.key")

    def test_a_missing_placeholder_raises(self):
        with written({"k": "{name}"}, {"k": "{name}"}) as directory:
            with self.assertRaises(KeyError):
                directory.catalogue().text("en", "k")

    def test_a_missing_key_never_falls_back_to_another_language(self):
        with written({"only.here": "x"}, {"other": "y"}) as directory:
            with self.assertRaises(KeyError):
                directory.catalogue().text("ru", "only.here")

    def test_doubled_braces_render_as_literal_braces(self):
        with written({"k": "{{raw}} {name}"}, {"k": "{{raw}} {name}"}) as directory:
            self.assertEqual(directory.catalogue().text("en", "k", name="n"), "{raw} n")

    def test_a_placeholder_value_is_not_interpreted_as_a_template(self):
        with written({"k": "{name}"}, {"k": "{name}"}) as directory:
            self.assertEqual(
                directory.catalogue().text("en", "k", name="{name}"), "{name}"
            )


class ContractHelperDetectsBrokenCatalogueTests(unittest.TestCase):
    def test_a_key_missing_from_one_language_is_reported(self):
        with written({"a": "A", "b": "B"}, {"a": "A", "c": "C"}) as directory:
            self.assertEqual(
                key_differences(directory.catalogue()),
                ["only in en.json: b", "only in ru.json: c"],
            )

    def test_a_placeholder_that_differs_between_languages_is_reported(self):
        with written({"k": "{a} {b}"}, {"k": "{a}"}) as directory:
            self.assertEqual(
                placeholder_differences(directory.catalogue()),
                ["k: en ['a', 'b'] ru ['a']"],
            )

    def test_a_field_access_counts_as_its_root_placeholder(self):
        with written({"k": "{a.x} {b[0]}"}, {"k": "{a} {b}"}) as directory:
            self.assertEqual(placeholder_differences(directory.catalogue()), [])

    def test_a_template_str_format_cannot_parse_is_reported(self):
        with written({"k": "{open"}, {"k": "fine"}) as directory:
            self.assertEqual(len(malformed_templates(directory.catalogue())), 1)

    def test_a_cyrillic_value_in_the_english_file_is_reported(self):
        with written({"k": "Привет"}, {"k": "Привет"}) as directory:
            self.assertEqual(cyrillic_in_english(directory.catalogue()), ["k"])

    def test_typographic_punctuation_in_the_english_file_is_reported(self):
        with written({"k": "a — b"}, {"k": "a — b"}) as directory:
            self.assertEqual(non_ascii_in_english(directory.catalogue()), ["k"])

    def test_russian_text_in_the_russian_file_is_not_reported(self):
        with written({"k": "x"}, {"k": "Привет — мир"}) as directory:
            catalogue = directory.catalogue()
            self.assertEqual(cyrillic_in_english(catalogue), [])
            self.assertEqual(non_ascii_in_english(catalogue), [])

    def test_a_file_whose_keys_are_not_sorted_is_reported(self):
        with written({"b": "B", "a": "A"}, {"a": "A", "b": "B"}) as directory:
            self.assertEqual(unsorted_files(directory.catalogue()), ["en"])

    def test_an_empty_value_is_reported(self):
        with written({"a": ""}, {"a": "A"}) as directory:
            self.assertEqual(empty_values(directory.catalogue()), ["en:a"])

    def test_a_byte_order_mark_is_reported(self):
        with written({"a": "A"}, {"a": "A"}) as directory:
            catalogue = directory.catalogue()
            Path(directory.name, "ru.json").write_bytes(b"\xef\xbb\xbf{}")
            self.assertEqual(files_with_byte_order_mark(catalogue), ["ru"])

    def test_a_clean_catalogue_has_no_problem_of_any_kind(self):
        with written({"a": "A {x}", "b": "B"}, {"a": "А {x}", "b": "Б"}) as directory:
            catalogue = directory.catalogue()
            for check in (
                empty_values,
                key_differences,
                placeholder_differences,
                malformed_templates,
                cyrillic_in_english,
                non_ascii_in_english,
                unsorted_files,
                files_with_byte_order_mark,
            ):
                with self.subTest(check=check.__name__):
                    self.assertEqual(check(catalogue), [])


class CleanFakeCatalogueSatisfiesTheContractTests(CatalogueContract, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = written({"a": "A {x}", "b": "B"}, {"a": "А {x}", "b": "Б"})
        cls.catalogue = cls.directory.catalogue()

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()


class IndependenceTests(unittest.TestCase):
    def test_the_module_imports_cleanly_with_its_sibling_components_unimportable(
        self,
    ):
        probe = "\n".join(
            [
                "import sys, json",
                "for name in ('installer', 'broker', 'client'):",
                "    sys.modules['sessionchat.' + name] = None",
                "import sessionchat.i18n",
                "print(json.dumps(sorted(",
                "    m for m, loaded in sys.modules.items()",
                "    if m.startswith('sessionchat') and loaded is not None)))",
            ]
        )
        completed = subprocess.run(
            [sys.executable, "-S", "-c", probe],
            cwd=BRIDGE,
            env=dict(os.environ, PYTHONPATH=str(BRIDGE)),
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout), ["sessionchat", "sessionchat.i18n"]
        )

    def test_every_import_is_absolute_and_from_the_standard_library(self):
        tree = ast.parse(Path(i18n_module.__file__).read_text(encoding="utf-8"))
        imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        self.assertTrue(imports)
        for node in imports:
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            with self.subTest(line=node.lineno):
                self.assertEqual(getattr(node, "level", 0), 0)
                for name in names:
                    self.assertIn(name.split(".")[0], sys.stdlib_module_names)


if __name__ == "__main__":
    unittest.main()
