from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Left:
    text: str
    files: tuple[str, ...] = ()


def left_lines(items: Sequence[Left]) -> list[str]:
    return [
        line
        for item in items
        for line in (f"    {item.text}", *(f"        {path}" for path in item.files))
    ]
