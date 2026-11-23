from dataclasses import dataclass
from enum import Enum

from .actions import ActionKind
from .texts import TrayTexts
from .observation import Observation
from .state import Colour, StandState
from .wording import menu_item_text, status_text


class MenuRole(Enum):
    STATUS = "status"
    SESSION = "session"
    TOGGLE = "toggle"
    OPEN_LOG = "open_log"
    EXIT = "exit"


@dataclass(frozen=True)
class MenuItem:
    role: MenuRole
    text: str
    enabled: bool
    action: ActionKind | None = None


TOGGLE_TEXT_KEYS = {
    (ActionKind.START, False): "tray.start",
    (ActionKind.STOP, False): "tray.stop",
    (ActionKind.START, True): "tray.starting",
    (ActionKind.STOP, True): "tray.stopping",
}


def offered_action(state: StandState) -> ActionKind:
    if state.colour is Colour.YELLOW:
        return state.running
    if state.colour is Colour.GREEN:
        return ActionKind.STOP
    if state.failure is not None:
        return state.failure.kind
    return ActionKind.START


def toggle_item(state: StandState, texts: TrayTexts) -> MenuItem:
    action = offered_action(state)
    busy = state.colour is Colour.YELLOW
    text = texts.text(TOGGLE_TEXT_KEYS[(action, busy)])
    return MenuItem(MenuRole.TOGGLE, text, not busy, action)


def build_menu(
    state: StandState, observation: Observation, texts: TrayTexts
) -> tuple[MenuItem, ...]:
    sessions = observation.sessions or ()
    return (
        MenuItem(MenuRole.STATUS, menu_item_text(status_text(state, texts)), False),
        *(
            MenuItem(MenuRole.SESSION, menu_item_text(session.line), False)
            for session in sessions
        ),
        toggle_item(state, texts),
        MenuItem(MenuRole.OPEN_LOG, texts.text("tray.open_log"), True),
        MenuItem(MenuRole.EXIT, texts.text("tray.exit"), True),
    )
