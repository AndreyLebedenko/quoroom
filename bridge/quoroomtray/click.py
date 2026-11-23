from dataclasses import dataclass

from . import settings
from .texts import TrayTexts
from .state import Colour, StandState


@dataclass(frozen=True)
class OpenElement:
    url: str


@dataclass(frozen=True)
class ShowNotification:
    text: str


def left_click(state: StandState, texts: TrayTexts) -> OpenElement | ShowNotification:
    if state.colour is Colour.GREEN:
        return OpenElement(settings.ELEMENT_URL)
    return ShowNotification(texts.text("tray.notification_not_running"))
