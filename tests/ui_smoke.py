"""Manual dashboard viewport smoke check against a running SARA server.

Usage: python tests/ui_smoke.py http://127.0.0.1:8765
"""

import sys

from playwright.sync_api import sync_playwright


def main():
    url = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765").rstrip("/")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width, height in ((1366, 768), (1024, 768), (1092, 614), (1024, 600), (800, 600)):
            page = browser.new_page(viewport={"width": width, "height": height})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url, wait_until="domcontentloaded")
            page.locator("#voice-mode").wait_for(state="attached", timeout=10000)
            metrics = page.evaluate("""() => ({
                documentHeight: document.documentElement.scrollHeight,
                viewportHeight: innerHeight,
                chatBottom: document.querySelector('#conversation-panel').getBoundingClientRect().bottom,
                heroBottom: document.querySelector('#hero').getBoundingClientRect().bottom,
                voiceRate: document.querySelector('#voice-rate').value
            })""")
            print(f"{width}x{height}: {metrics}; JS errors: {errors}")
            if errors:
                raise AssertionError(errors)
            if width >= 801 and (metrics["documentHeight"] > height or metrics["chatBottom"] > height):
                raise AssertionError("Desktop dashboard does not fit the window")
            if width >= 801:
                page.locator('button[data-view="chat"]').first.click()
                chat_height = page.evaluate("document.documentElement.scrollHeight")
                chat_bottom = page.locator("#conversation-panel").bounding_box()["y"] + page.locator("#conversation-panel").bounding_box()["height"]
                print(f"{width}x{height} chat view: scroll {chat_height}, chat bottom {chat_bottom:.1f}")
                if chat_height > height or chat_bottom > height:
                    raise AssertionError("Desktop conversation does not fit the window")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
