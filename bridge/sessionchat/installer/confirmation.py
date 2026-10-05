from __future__ import annotations

from collections.abc import Sequence

from .boundaries import Boundaries
from .catalogue import text
from .ownership import PurgeTarget
from .secrets import Secrets

WORD = "PURGE"


class Confirmation:
    def __init__(self, boundaries: Boundaries, secrets: Secrets) -> None:
        self.boundaries = boundaries
        self.secrets = secrets

    def ask(self, consequence: str, targets: Sequence[PurgeTarget]) -> bool:
        lang = self.boundaries.lang
        lines = [text(lang, "confirmation.heading")]
        lines += [f"    {target.role}: {target.kind} {target.id}" for target in targets]
        lines.append(text(lang, "confirmation.consequence", consequence=consequence))
        lines.append(text(lang, "confirmation.prompt", word=WORD))
        self.boundaries.stdout.write(self.secrets.scrub("\n".join(lines)) + "\n")
        return self.boundaries.stdin.readline().strip() == WORD
