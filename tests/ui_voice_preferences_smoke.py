"""Offline browser regressions for saved voices, pronunciation learning and startup.

No microphone, TTS provider, OS audio, server, or user data is used.
"""
from playwright.sync_api import expect, sync_playwright
from browser_fixture import dashboard_fixture


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        errors, prepared = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.clock.install(time="2026-11-13T08:00:00Z")
        page.add_init_script("""
            localStorage.setItem('sara-wake','false');
            localStorage.setItem('sara-auto-speak','true');
            localStorage.setItem('sara-voice-mode','system');
            localStorage.setItem('sara-voice-uri','old/Microsoft Kalpana Natural');
            localStorage.setItem('sara-voice-name','Microsoft Kalpana Natural');
            localStorage.setItem('sara-voice-lang','hi-IN');
            const c=window.__voice={voices:[],utterances:[],pending:false,speaking:false};
            const events=new EventTarget();
            Object.defineProperty(window,'speechSynthesis',{value:{
              getVoices:()=>c.voices,
              addEventListener:(...args)=>events.addEventListener(...args),
              removeEventListener:(...args)=>events.removeEventListener(...args),
              get speaking(){return c.speaking;},get pending(){return c.pending;},paused:false,
              resume:()=>{},cancel:()=>{c.pending=false;c.speaking=false;},
              speak:u=>{c.utterances.push(u);c.pending=true;}
            }});
            window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};
            c.emit=()=>events.dispatchEvent(new Event('voiceschanged'));
            c.start=()=>{c.pending=false;c.speaking=true;c.utterances.at(-1).onstart?.();};
            c.end=()=>{c.pending=false;c.speaking=false;c.utterances.at(-1).onend?.();};
            Object.defineProperty(navigator,'permissions',{value:{query:()=>Promise.resolve({state:'prompt',addEventListener:()=>{}})}});
        """)

        def api(route):
            path = route.request.url.split("/api/")[-1].split("?")[0]
            if path == "chat":
                teaching = route.request.post_data_json["message"] == "Teach pronunciation"
                reply = {"reply": "Review this pronunciation." if teaching else "नमस्ते दोस्त।", "provider": "mock"}
                if teaching:
                    reply.update(requires_confirmation=True, action={"type": "save_pronunciation", "word": "friend", "say_as": "दोस्त"})
                return route.fulfill(json=reply)
            if path == "speech-text":
                text = route.request.post_data_json["text"]
                prepared.append(text)
                return route.fulfill(json={"text": text, "playback": [{"text": text, "lang": "hi-IN"}]})
            if path == "pronunciations":
                return route.fulfill(json={"ok": True, "result": "Pronunciation saved"} if route.request.method == "POST" else [])
            return route.fallback()

        page.route("**/api/**", api)
        page.goto(dashboard_fixture(page, "fixture"))
        expect(page.locator("#send-button")).to_be_enabled()
        page.clock.pause_at("2026-11-13T09:00:00Z")

        def until(expression):
            for _ in range(200):
                if page.evaluate(expression):
                    return
                page.clock.run_for(10)
            raise AssertionError(expression)

        def send(message):
            page.locator("#message").fill(message)
            page.locator("#send-button").click()
            until("!document.querySelector('#send-button').disabled")

        send("First voice check")
        until("!document.querySelector('#stop-speech').hidden")
        assert not page.evaluate("__voice.utterances.length")
        # Delayed getVoices data without voiceschanged must still restore the
        # exact saved name, rather than a shorter substring or automatic choice.
        page.evaluate("""__voice.voices=[
            {name:'Microsoft Kalpana',lang:'hi-IN',voiceURI:'short'},
            {name:'Microsoft Kalpana Natural',lang:'hi-IN',voiceURI:'new-full'},
            {name:'Microsoft Ravi',lang:'en-IN',voiceURI:'ravi'}
        ]""")
        until("__voice.utterances.length===1")
        assert page.evaluate("__voice.utterances[0].voice.voiceURI") == "new-full"
        assert page.locator("#voice-select").input_value() == "new-full"
        assert page.locator("#character-stage").is_visible()
        assert page.locator("#character-stage").get_attribute("data-state") != "speaking"
        page.evaluate("__voice.start()")
        assert page.locator("#character-stage").get_attribute("data-state") == "speaking"
        page.evaluate("__voice.end()")
        assert page.locator("#character-stage").get_attribute("data-state") == "ready"

        page.locator('button[data-view="settings"]').first.click()
        page.locator("#voice-select").select_option("ravi")
        page.evaluate("__voice.emit()")
        assert page.locator("#voice-select").input_value() == "ravi", "Manual voice was rejected by recommendation scoring"
        assert page.evaluate("localStorage.getItem('sara-voice-name')") == "Microsoft Ravi"
        page.locator('button[data-view="chat"]').first.click()
        send("Repeat the same reply")
        until("__voice.utterances.length===2")
        assert prepared.count("नमस्ते दोस्त।") == 1
        page.evaluate("__voice.start();__voice.end()")

        page.locator("#speaker-toggle").click()
        send("Teach pronunciation")
        page.locator(".message.assistant button.message-action").last.click()
        page.locator("#approve-action").click()
        expect(page.locator("#confirmation")).not_to_be_visible()
        page.locator("#speaker-toggle").click()
        send("Repeat after learning")
        until("__voice.utterances.length===3")
        assert prepared.count("नमस्ते दोस्त।") == 2, "Pronunciation change left stale prepared speech cached"
        # A native queue stuck pending must recover, while the separate voice
        # session smoke still proves valid long speech is never cut off.
        page.clock.run_for(16000)
        assert page.locator("#stop-speech").is_hidden()
        assert "Voice failed" in page.locator("#voice-status").inner_text()
        assert page.locator("#character-stage").get_attribute("data-state") == "ready"
        assert not errors, errors
        print("PASS: delayed voices without event, exact saved voice restore, manual preference, avatar start/end sync, pronunciation cache refresh, stuck speech queue recovery")
        browser.close()


if __name__ == "__main__":
    main()
