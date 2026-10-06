from __future__ import annotations

from collections.abc import Mapping

from ..i18n import DEFAULT_LANGUAGE, LANGUAGES, Catalogue, render

__all__ = (
    "DEFAULT_LANGUAGE",
    "INSTALLER_CATALOGUE",
    "LANGUAGES",
    "STEP_PREFIX",
    "catalogue",
    "has",
    "step_label",
    "text",
)

STEP_PREFIX = "step."

INSTALLER_CATALOGUE = Catalogue(__package__, "messages")


def catalogue(lang: str) -> Mapping[str, str]:
    return INSTALLER_CATALOGUE.templates(lang)


def has(lang: str, key: str) -> bool:
    return key in catalogue(lang)


def text(lang: str, key: str, **params: object) -> str:
    return render(catalogue(lang), lang, key, params)


def step_label(lang: str, name: str) -> str:
    key = f"{STEP_PREFIX}{name}"
    return text(lang, key) if has(lang, key) else name
