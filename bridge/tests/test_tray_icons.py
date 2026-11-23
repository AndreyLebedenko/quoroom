"""Task tray-03: icon colour selection."""

import unittest

from quoroomtray.icons import icon_rgb
from quoroomtray.state import Colour


class IconColourTests(unittest.TestCase):
    def test_every_state_colour_has_an_icon_colour(self):
        for colour in Colour:
            with self.subTest(colour=colour):
                self.assertEqual(3, len(icon_rgb(colour)))

    def test_the_four_icon_colours_differ_from_each_other(self):
        self.assertEqual(4, len({icon_rgb(colour) for colour in Colour}))

    def test_grey_has_equal_channels(self):
        red, green, blue = icon_rgb(Colour.GREY)

        self.assertEqual(red, green)
        self.assertEqual(green, blue)

    def test_green_is_dominated_by_the_green_channel(self):
        red, green, blue = icon_rgb(Colour.GREEN)

        self.assertGreater(green, red)
        self.assertGreater(green, blue)

    def test_red_is_dominated_by_the_red_channel(self):
        red, green, blue = icon_rgb(Colour.RED)

        self.assertGreater(red, green)
        self.assertGreater(red, blue)

    def test_yellow_has_strong_red_and_green_and_weak_blue(self):
        red, green, blue = icon_rgb(Colour.YELLOW)

        self.assertGreater(red, blue)
        self.assertGreater(green, blue)
        self.assertGreater(green, 150)

    def test_channels_are_valid_bytes(self):
        for colour in Colour:
            with self.subTest(colour=colour):
                self.assertTrue(all(0 <= value <= 255 for value in icon_rgb(colour)))


if __name__ == "__main__":
    unittest.main()
