from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

from ..entries import TrayEntry, TraySnapshot
from ..icons import Rgb, icon_rgb
from ..shell_settings import ICON_MARGIN, ICON_SIZE, NOTIFICATION_TITLE
from ..state import Colour


def draw_icon(rgb: Rgb) -> Image.Image:
    image = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    far_edge = ICON_SIZE - ICON_MARGIN
    ImageDraw.Draw(image).ellipse(
        (ICON_MARGIN, ICON_MARGIN, far_edge, far_edge), fill=(*rgb, 255)
    )
    return image


def _action(on_select: Callable[[], None] | None):
    if on_select is None:
        return None
    return lambda: on_select()


def menu_item(entry: TrayEntry) -> pystray.MenuItem:
    return pystray.MenuItem(
        entry.text,
        _action(entry.on_select),
        default=entry.default,
        visible=entry.visible,
        enabled=entry.enabled,
    )


def menu_of(entries: tuple[TrayEntry, ...]) -> pystray.Menu:
    return pystray.Menu(*(menu_item(entry) for entry in entries))


class PystrayShell:
    def __init__(self):
        self._images = {colour: draw_icon(icon_rgb(colour)) for colour in Colour}
        self._icon: pystray.Icon | None = None

    def run(self, first: TraySnapshot, on_ready: Callable[[], None]) -> None:
        self._icon = pystray.Icon(
            NOTIFICATION_TITLE,
            self._images[first.colour],
            first.tooltip,
            menu_of(first.entries),
        )

        def setup(icon: pystray.Icon) -> None:
            icon.visible = True
            on_ready()

        self._icon.run(setup)

    def show(self, snapshot: TraySnapshot) -> None:
        self._icon.icon = self._images[snapshot.colour]
        self._icon.title = snapshot.tooltip
        self._icon.menu = menu_of(snapshot.entries)
        self._icon.update_menu()

    def notify(self, text: str) -> None:
        self._icon.notify(text, NOTIFICATION_TITLE)

    def stop(self) -> None:
        self._icon.stop()
