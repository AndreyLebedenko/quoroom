from __future__ import annotations

import json
from collections.abc import Mapping
from functools import cache
from importlib.resources import files
from types import MappingProxyType

LANGUAGES = ("en", "ru")
DEFAULT_LANGUAGE = "en"
STEP_PREFIX = "step."


@cache
def catalogue(lang: str) -> Mapping[str, str]:
    if lang not in LANGUAGES:
        raise ValueError(
            f"unknown language {lang!r}, available: {', '.join(LANGUAGES)}"
        )
    source = files(__package__) / "messages" / f"{lang}.json"
    return MappingProxyType(json.loads(source.read_text(encoding="utf-8")))


def has(lang: str, key: str) -> bool:
    return key in catalogue(lang)


def text(lang: str, key: str, **params: object) -> str:
    templates = catalogue(lang)
    if key not in templates:
        raise KeyError(f"no message {key!r} in language {lang!r}")
    try:
        return templates[key].format(**params)
    except KeyError as missing:
        raise KeyError(
            f"message {key!r} in language {lang!r} needs the parameter {missing}"
        ) from None


def step_label(lang: str, name: str) -> str:
    key = f"{STEP_PREFIX}{name}"
    return text(lang, key) if has(lang, key) else name
