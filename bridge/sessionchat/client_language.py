import os
from pathlib import Path

from .i18n import DEFAULT_LANGUAGE, LANGUAGES

FILE_NAME = "language"


def valid(value: object) -> str | None:
    if isinstance(value, str) and value in LANGUAGES:
        return value
    return None


def remembered(store: Path) -> str | None:
    try:
        content = (store / FILE_NAME).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    return valid(content.strip())


def discard(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def remember(store: Path, language: str) -> None:
    if remembered(store) == language:
        return
    target = store / FILE_NAME
    temporary = store / f"{FILE_NAME}.{os.getpid()}.tmp"
    try:
        store.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(f"{language}\n".encode("ascii"))
        os.replace(temporary, target)
    except OSError:
        discard(temporary)


class RoomLanguage:
    def __init__(self) -> None:
        self.explicit: str | None = None
        self.answered: str | None = None

    def insist(self, language: object) -> None:
        self.explicit = valid(language)

    def learn(self, store: Path, language: object) -> None:
        known = valid(language)
        if known is None:
            return
        self.answered = known
        remember(store, known)

    def current(self, store: Path) -> str:
        return (
            valid(self.explicit)
            or valid(self.answered)
            or remembered(store)
            or DEFAULT_LANGUAGE
        )
