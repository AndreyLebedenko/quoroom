from .state import Colour

Rgb = tuple[int, int, int]

ICON_RGB: dict[Colour, Rgb] = {
    Colour.GREY: (128, 128, 128),
    Colour.YELLOW: (240, 190, 20),
    Colour.GREEN: (40, 170, 70),
    Colour.RED: (215, 50, 50),
}


def icon_rgb(colour: Colour) -> Rgb:
    return ICON_RGB[colour]
