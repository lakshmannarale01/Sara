import unittest

from sara_app.browser_control import click_text, fill_text, open_page, whatsapp_send


class BrowserSafetyTests(unittest.TestCase):
    def test_open_requires_confirmation(self):
        result = open_page("https://example.com")
        self.assertTrue(result["requires_confirmation"])

    def test_click_requires_confirmation(self):
        result = click_text("https://example.com", "More information")
        self.assertTrue(result["requires_confirmation"])

    def test_fill_requires_confirmation(self):
        result = fill_text("https://example.com", "Email", "user@example.com")
        self.assertTrue(result["requires_confirmation"])

    def test_non_https_is_rejected(self):
        with self.assertRaises(ValueError):
            open_page("http://example.com")

    def test_whatsapp_send_requires_confirmation(self):
        result = whatsapp_send("919876543210", "hello")
        self.assertTrue(result["requires_confirmation"])


if __name__ == "__main__":
    unittest.main()
