import unittest

from sara_app.desktop import click_point, press_hotkey, type_text


class DesktopSafetyTests(unittest.TestCase):
    def test_type_requires_confirmation(self):
        result = type_text("hello")
        self.assertTrue(result["requires_confirmation"])

    def test_hotkey_requires_confirmation(self):
        result = press_hotkey(["ctrl", "c"])
        self.assertTrue(result["requires_confirmation"])

    def test_click_requires_confirmation(self):
        result = click_point(1, 1)
        self.assertTrue(result["requires_confirmation"])

    def test_invalid_hotkey_is_rejected(self):
        with self.assertRaises(ValueError):
            press_hotkey(["rm", "rf"])

    def test_out_of_bounds_click_is_rejected(self):
        with self.assertRaises(ValueError):
            click_point(-1, -1)


if __name__ == "__main__":
    unittest.main()
