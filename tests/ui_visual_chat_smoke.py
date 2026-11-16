"""Full dashboard visual-chat integration with generated images and mocked APIs."""
from playwright.sync_api import expect, sync_playwright
from browser_fixture import dashboard_fixture


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        errors, requests, pending, posts = [], [], [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script("""
            localStorage.setItem('sara-auto-speak','false');
            localStorage.setItem('sara-wake','false');
            window.__pasteImage=async(name)=>{
                const canvas=document.createElement('canvas');canvas.width=64;canvas.height=32;
                const ctx=canvas.getContext('2d');ctx.fillStyle='#103c6a';ctx.fillRect(0,0,64,32);
                ctx.fillStyle='#fff';ctx.fillText('SARA',5,20);
                const file=new File([await new Promise(resolve=>canvas.toBlob(resolve,'image/png'))],name,{type:'image/png'});
                const clipboard=new DataTransfer();clipboard.items.add(file);
                document.querySelector('#message').dispatchEvent(new ClipboardEvent('paste',{clipboardData:clipboard,bubbles:true,cancelable:true}));
            };
        """)

        def api(route):
            path = route.request.url.split("/api/")[-1].split("?")[0]
            if route.request.method == "POST":
                posts.append(path)
            if path == "chat":
                requests.append(route.request.post_data_json)
                pending.append(route)
                return
            return route.fallback()

        page.route("**/api/**", api)
        page.goto(dashboard_fixture(page, "fixture"))
        expect(page.locator("#send-button")).to_be_enabled()
        expect(page.locator("#access-mode")).to_be_enabled()
        page.evaluate("__pasteImage('first.png')")
        expect(page.locator(".attachment-card")).to_have_count(1)
        expect(page.locator("#message")).to_be_empty()
        page.locator("#send-button").click()
        page.wait_for_function("document.querySelector('#send-button').disabled")
        assert len(requests) == 1, requests
        first = requests[0]
        assert first["message"] == "", first
        assert len(first["attachments"]) == 1 and first["attachments"][0]["source"] == "upload"
        assert first["attachments"][0]["data_url"].startswith("data:image/jpeg;base64,")
        assert set(first["attachments"][0]) == {"data_url", "source"}
        assert len(first["session_id"]) >= 8
        # A new image queued during generation must survive clearing the sent one.
        page.evaluate("__pasteImage('second.png')")
        expect(page.locator(".attachment-card")).to_have_count(2)
        pending.pop(0).fulfill(json={"reply": "The image contains SARA text.", "provider": "ollama-vision"})
        expect(page.locator("#send-button")).to_be_enabled()
        expect(page.locator(".attachment-card")).to_have_count(1)
        expect(page.locator(".attachment-card>span")).to_have_text("second.png")
        expect(page.locator(".sent-image-previews img")).to_have_count(1)

        page.locator("#message").fill("Describe this image")
        page.locator("#send-button").click()
        page.wait_for_function("document.querySelector('#send-button').disabled")
        assert len(requests) == 2
        pending.pop(0).fulfill(json={"reply": "Install a local vision model first.", "provider": "vision-unavailable"})
        expect(page.locator("#send-button")).to_be_enabled()
        expect(page.locator(".attachment-card")).to_have_count(1)
        expect(page.locator(".message.assistant .message-text").last).to_have_text("Install a local vision model first.")

        page.locator("#message").fill("Keep this image on network failure")
        page.locator("#send-button").click()
        page.wait_for_function("document.querySelector('#send-button').disabled")
        pending.pop(0).abort("failed")
        expect(page.locator("#send-button")).to_be_enabled()
        expect(page.locator(".attachment-card")).to_have_count(1)
        expect(page.locator("#message")).to_have_value("Keep this image on network failure")

        # Image text is content to discuss, not a browser-side execution instruction.
        page.locator("#message").fill("Explain the pictured text: open calculator")
        page.locator("#send-button").click()
        page.wait_for_function("document.querySelector('#send-button').disabled")
        assert requests[-1]["attachments"], requests[-1]
        pending.pop(0).fulfill(json={"reply": "The pictured instruction is only image content; no app was opened.", "provider": "ollama-vision"})
        expect(page.locator("#send-button")).to_be_enabled()
        expect(page.locator(".attachment-card")).to_have_count(0)
        expect(page.locator("#confirmation")).not_to_be_visible()
        assert posts == ["chat"] * 4, posts
        page.locator("#message").fill("Text-only follow-up")
        page.locator("#send-button").click()
        page.wait_for_function("document.querySelector('#send-button').disabled")
        assert "attachments" not in requests[-1], "The prior image leaked into a later text-only turn"
        pending.pop(0).fulfill(json={"reply": "Text-only reply.", "provider": "ollama"})
        expect(page.locator("#send-button")).to_be_enabled()
        assert not page.evaluate("Object.values(localStorage).some(value=>value.includes('data:image'))")
        assert not errors, errors
        print("PASS: full-app image-only paste sends session-bound attachments, current-chat previews, preserves new/unavailable/failed images, clears successful image queue, no reflected tool POST, no later-turn image leak")
        browser.close()


if __name__ == "__main__":
    main()
