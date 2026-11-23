from pathlib import Path

import yaml

from sessionchat.i18n import DEFAULT_LANGUAGE


def tray_language(config: Path) -> str:
    try:
        loaded = yaml.safe_load(config.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError):
        return DEFAULT_LANGUAGE
    if isinstance(loaded, dict) and loaded.get("language") == "ru":
        return "ru"
    return DEFAULT_LANGUAGE
