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


STARTUP_FAILED_EXIT_CODE = 1


def exit_code_after_reporting(entry: Callable[[], int], report: FailureReport) -> int:
    try:
        return entry()
    except Exception as failure:
        try:
            report(failure)
        except Exception:
            pass
        return STARTUP_FAILED_EXIT_CODE
