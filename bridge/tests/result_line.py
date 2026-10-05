"""Task english-release-08: reading the result line a session command ends with."""

import json

from sessionchat.client_result import PREFIX

MARK = f"{PREFIX} "


def result_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(MARK)]


def read_result(text: str) -> dict:
    return json.loads(result_lines(text)[-1][len(MARK) :])


def without_result(text: str) -> str:
    return "".join(
        line for line in text.splitlines(keepends=True) if not line.startswith(MARK)
    )
