"""Task english-release-01: the checks every message catalogue must satisfy."""

import re
import string

from sessionchat.i18n import LANGUAGES, Catalogue

CYRILLIC = re.compile("[Ѐ-ӿ]")
PRINTABLE_ASCII = re.compile(r"[\x20-\x7e\n]*")


def placeholders(template: str) -> set[str]:
    return {
        name.split(".")[0].split("[")[0]
        for _, name, _, _ in string.Formatter().parse(template)
        if name is not None
    }


def empty_values(catalogue: Catalogue) -> list[str]:
    return [
        f"{lang}:{key}"
        for lang in LANGUAGES
        for key, value in catalogue.templates(lang).items()
        if not value
    ]


def key_differences(catalogue: Catalogue) -> list[str]:
    english, russian = set(catalogue.templates("en")), set(catalogue.templates("ru"))
    return [f"only in en.json: {key}" for key in sorted(english - russian)] + [
        f"only in ru.json: {key}" for key in sorted(russian - english)
    ]


def placeholder_differences(catalogue: Catalogue) -> list[str]:
    english, russian = catalogue.templates("en"), catalogue.templates("ru")
    return [
        f"{key}: en {sorted(placeholders(english[key]))}"
        f" ru {sorted(placeholders(russian[key]))}"
        for key in sorted(english.keys() & russian.keys())
        if placeholders(english[key]) != placeholders(russian[key])
    ]


def malformed_templates(catalogue: Catalogue) -> list[str]:
    problems = []
    for lang in LANGUAGES:
        for key, value in catalogue.templates(lang).items():
            try:
                list(string.Formatter().parse(value))
            except ValueError as error:
                problems.append(f"{lang}:{key}: {error}")
    return problems


def cyrillic_in_english(catalogue: Catalogue) -> list[str]:
    return [
        key
        for key, value in catalogue.templates("en").items()
        if CYRILLIC.search(value)
    ]


def non_ascii_in_english(catalogue: Catalogue) -> list[str]:
    return [
        key
        for key, value in catalogue.templates("en").items()
        if not PRINTABLE_ASCII.fullmatch(value)
    ]


def unsorted_files(catalogue: Catalogue) -> list[str]:
    return [
        lang
        for lang in LANGUAGES
        if list(catalogue.templates(lang)) != sorted(catalogue.templates(lang))
    ]


def files_with_byte_order_mark(catalogue: Catalogue) -> list[str]:
    return [
        lang
        for lang in LANGUAGES
        if catalogue.source(lang).read_bytes().startswith(b"\xef\xbb\xbf")
    ]


class CatalogueContract:
    catalogue: Catalogue

    def test_each_catalogue_is_a_flat_mapping_of_text_to_text(self):
        for lang in LANGUAGES:
            with self.subTest(lang=lang):
                self.assertTrue(self.catalogue.templates(lang))
        self.assertEqual(empty_values(self.catalogue), [])

    def test_the_two_catalogues_have_the_same_keys(self):
        self.assertEqual(key_differences(self.catalogue), [])

    def test_each_key_has_the_same_placeholders_in_both_languages(self):
        self.assertEqual(placeholder_differences(self.catalogue), [])

    def test_every_template_is_valid_for_str_format(self):
        self.assertEqual(malformed_templates(self.catalogue), [])

    def test_the_english_catalogue_has_no_cyrillic(self):
        self.assertEqual(cyrillic_in_english(self.catalogue), [])

    def test_the_english_catalogue_uses_only_ascii_punctuation(self):
        self.assertEqual(non_ascii_in_english(self.catalogue), [])

    def test_keys_are_sorted_so_that_parallel_additions_merge(self):
        self.assertEqual(unsorted_files(self.catalogue), [])

    def test_the_files_are_utf8_without_a_byte_order_mark(self):
        self.assertEqual(files_with_byte_order_mark(self.catalogue), [])
