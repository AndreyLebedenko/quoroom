from collections.abc import Callable
from typing import Any

FailureReport = Callable[[Exception], None]


def guarded(action: Callable[..., Any], report: FailureReport) -> Callable[..., None]:
    def run(*args: Any, **kwargs: Any) -> None:
        try:
            action(*args, **kwargs)
        except Exception as failure:
            try:
                report(failure)
            except Exception:
                pass

    return run
