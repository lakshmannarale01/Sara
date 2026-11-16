"""Verify procedural HUD motion/state and accessibility with mocked SARA APIs."""
from playwright.sync_api import expect, sync_playwright
from browser_fixture import dashboard_fixture


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=3)
        errors, held_chats, requested = [], [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requested.append(request.url))
        page.add_init_script("""
            localStorage.setItem('sara-auto-speak','true');
            localStorage.setItem('sara-wake','false');
            const c=window.__hudTest={utterances:[],speaking:false,pending:false,recognizers:[]};
            window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};
            Object.defineProperty(window,'speechSynthesis',{value:{
              getVoices:()=>[{name:'Microsoft Kalpana',lang:'hi-IN',voiceURI:'kalpana'}],
              addEventListener:()=>{},cancel:()=>{c.speaking=false;c.pending=false;},resume:()=>{},
              get speaking(){return c.speaking;},get pending(){return c.pending;},paused:false,
              speak:u=>{c.utterances.push(u);c.pending=true;}
            }});
            class Recognition {constructor(){c.recognizers.push(this);}start(){this.onstart?.();}abort(){}}
            Object.defineProperty(window,'SpeechRecognition',{value:Recognition});
            Object.defineProperty(navigator,'permissions',{value:{query:()=>Promise.resolve({state:'prompt',addEventListener:()=>{}})}});
            c.startSpeech=()=>{c.pending=false;c.speaking=true;c.utterances.at(-1).onstart?.();};
        """)

        def api(route):
            path = route.request.url.split("/api/")[-1].split("?")[0]
            if path == "chat":
                held_chats.append(route)
                return
            if path == "speech-text":
                return route.fulfill(json={"text": "नमस्ते दोस्त।", "playback": [{"text": "नमस्ते दोस्त।", "lang": "hi-IN"}]})
            if path == "actions/cancel":
                return route.fulfill(json={"ok": True, "cancelled": True})
            return route.fallback()

        page.route("**/api/**", api)
        page.goto(dashboard_fixture(page, "fixture"))
        expect(page.locator("#send-button")).to_be_enabled()
        canvas = page.locator("#hud-canvas")
        page.wait_for_function("Number(document.querySelector('#hud-canvas').dataset.frame)>2")
        assert page.locator("#character-stage img, #character-stage video").count() == 0
        assert not any("sara-character" in url or "avatar-speaking" in url for url in requested)
        assert canvas.evaluate("c=>c.width<=Math.ceil(c.getBoundingClientRect().width*2)")
        first = canvas.evaluate("c=>c.toDataURL()")
        page.wait_for_timeout(180)
        assert canvas.evaluate("c=>c.toDataURL()") != first, "HUD is a still frame"

        page.locator("#message").fill("Explain the next step")
        page.locator("#send-button").click()
        expect(page.locator("#character-stage")).to_have_attribute("data-state", "thinking")
        assert held_chats
        held_chats.pop().fulfill(json={"reply": "नमस्ते दोस्त।", "provider": "mock"})
        page.wait_for_function("__hudTest.utterances.length===1")
        assert canvas.get_attribute("data-state") != "speaking", "HUD speaks before audio starts"
        page.evaluate("__hudTest.startSpeech()")
        expect(canvas).to_have_attribute("data-state", "speaking")
        page.locator("#stop-speech").click()
        expect(canvas).to_have_attribute("data-state", "ready")

        page.locator("#mic-button").click()
        expect(canvas).to_have_attribute("data-state", "listening")
        page.locator("#mic-button").click()
        expect(canvas).to_have_attribute("data-state", "ready")

        # Hidden views should stop rendering rather than consuming a frame loop.
        page.locator('button[data-view="settings"]').first.click()
        page.wait_for_timeout(120)
        hidden_frame = canvas.get_attribute("data-frame")
        page.wait_for_timeout(160)
        assert canvas.get_attribute("data-frame") == hidden_frame
        page.locator('button[data-view="chat"]').first.click()
        page.wait_for_function("c=>Number(document.querySelector('#hud-canvas').dataset.frame)>Number(c)", arg=hidden_frame)

        # Motion preference produces one stable native-rendered frame.
        page.emulate_media(reduced_motion="reduce")
        expect(canvas).to_have_attribute("data-motion", "reduced")
        frame = canvas.get_attribute("data-frame")
        reduced_image = canvas.evaluate("c=>c.toDataURL()")
        page.wait_for_timeout(180)
        assert canvas.get_attribute("data-frame") == frame
        assert canvas.evaluate("c=>c.toDataURL()") == reduced_image
        page.emulate_media(reduced_motion="no-preference")
        page.wait_for_function("c=>Number(document.querySelector('#hud-canvas').dataset.frame)>Number(c)", arg=frame)
        assert not errors, errors
        print("PASS: live canvas pixels, no portrait/video requests, device pixel cap, thinking/listening/TTS-start sync, hidden-view pause, reduced motion")
        browser.close()


if __name__ == "__main__":
    main()
