from __future__ import annotations

import json
from collections.abc import Mapping
from importlib.resources import files
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable

LANGUAGES = ("en", "ru")
DEFAULT_LANGUAGE = "en"


def read_templates(root: Traversable, lang: str) -> Mapping[str, str]:
    source = root / f"{lang}.json"
    loaded = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in loaded.items()
    ):
        raise ValueError(f"{source} must be a flat mapping of text to text")
    return MappingProxyType(loaded)


def render(
    templates: Mapping[str, str], lang: str, key: str, params: Mapping[str, object]
) -> str:
    if key not in templates:
        raise KeyError(f"no message {key!r} in language {lang!r}")
    try:
        return templates[key].format(**params)
    except KeyError as missing:
        raise KeyError(
            f"message {key!r} in language {lang!r} needs the parameter {missing}"
        ) from None


class Catalogue:
    def __init__(self, package: str, directory: str):
        self._adopt(files(package) / directory)

    @classmethod
    def from_path(cls, root: Traversable) -> Catalogue:
        catalogue = cls.__new__(cls)
        catalogue._adopt(root)
        return catalogue

    def _adopt(self, root: Traversable) -> None:
        self._root = root
        self._templates = {lang: read_templates(root, lang) for lang in LANGUAGES}

    def templates(self, lang: str) -> Mapping[str, str]:
        if lang not in self._templates:
            raise ValueError(
                f"unknown language {lang!r}, available: {', '.join(LANGUAGES)}"
            )
        return self._templates[lang]

    def source(self, lang: str) -> Traversable:
        self.templates(lang)
        return self._root / f"{lang}.json"

    def has(self, lang: str, key: str) -> bool:
        return key in self.templates(lang)

    def text(self, lang: str, key: str, **params: object) -> str:
        return render(self.templates(lang), lang, key, params)
