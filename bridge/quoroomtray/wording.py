from . import settings
from .actions import ActionKind
from .texts import TrayTexts
from .state import Colour, RedReason, StandState

ELLIPSIS = "..."


def reason_text(state: StandState, texts: TrayTexts) -> str:
    if state.reason is RedReason.ONLY_STACK_ANSWERS:
        return texts.text("tray.reason_stack_only")
    if state.reason is RedReason.ONLY_BROKER_ANSWERS:
        return texts.text("tray.reason_broker_only")
    failure = state.failure
    detail = failure.last_line or texts.text("tray.exit_code", code=failure.exit_code)
    key = (
        "tray.reason_start_failed"
        if failure.kind is ActionKind.START
        else "tray.reason_stop_failed"
    )
    return texts.text(key, detail=detail)


def status_text(state: StandState, texts: TrayTexts) -> str:
    if state.colour is Colour.GREY:
        return texts.text("tray.status_grey")
    if state.colour is Colour.GREEN:
        return texts.text("tray.status_green")
    if state.colour is Colour.YELLOW:
        key = (
            "tray.status_starting"
            if state.running is ActionKind.START
            else "tray.status_stopping"
        )
        return texts.text(key)
    return texts.text("tray.status_red", reason=reason_text(state, texts))


def tooltip_text(state: StandState, texts: TrayTexts) -> str:
    tooltip = f"{settings.APP_NAME}: {status_text(state, texts)}"
    if len(tooltip) <= settings.TOOLTIP_LIMIT:
        return tooltip
    return tooltip[: settings.TOOLTIP_LIMIT - len(ELLIPSIS)] + ELLIPSIS
