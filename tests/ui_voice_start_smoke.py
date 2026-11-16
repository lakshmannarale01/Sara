"""Conversation startup and local Windows audio fallback with mocked devices."""
from playwright.sync_api import expect, sync_playwright
from browser_fixture import dashboard_fixture


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        errors, greetings, windows_calls = [], [], []
        mode = {"windows": "success"}
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script("""
          localStorage.setItem('sara-auto-speak','false');localStorage.setItem('sara-wake','false');
          localStorage.setItem('sara-voice-uri','windows:kalpana-local');
          localStorage.setItem('sara-voice-name','Microsoft Kalpana');localStorage.setItem('sara-voice-lang','hi-IN');
          const c=window.__startVoice={audio:[],utterances:[],pending:false,speaking:false,recognitions:0};
          window.Audio=class {
            constructor(src){this.src=src;c.audio.push(this);} play(){return Promise.resolve();}
            pause(){} removeAttribute(){} load(){}
          };
          Object.defineProperty(window,'speechSynthesis',{value:{
            getVoices:()=>[{name:'Microsoft Kalpana',lang:'hi-IN',voiceURI:'browser-kalpana'}],
            addEventListener(){},removeEventListener(){},cancel(){c.pending=false;c.speaking=false;},resume(){},paused:false,
            get pending(){return c.pending;},get speaking(){return c.speaking;},
            speak(u){c.utterances.push(u);c.pending=true;}
          }});
          window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};
          window.SpeechRecognition=class {start(){c.recognitions++;this.onstart?.();}abort(){}};
          Object.defineProperty(navigator,'permissions',{value:{query:()=>Promise.resolve({state:'prompt',addEventListener(){}})}});
          c.startBrowser=()=>{c.pending=false;c.speaking=true;c.utterances.at(-1).onstart?.();};
          c.endBrowser=()=>{c.pending=false;c.speaking=false;c.utterances.at(-1).onend?.();};
        """)

        def api(route):
            path = route.request.url.split("/api/")[-1].split("?")[0]
            if path == "voices/windows":
                return route.fulfill(json={"available": True, "voices": [{"id": "kalpana-local", "name": "Microsoft Kalpana", "lang": "hi-IN"}]})
            if path == "check-in":
                greetings.append(route.request.post_data_json)
                return route.fulfill(json={"reply": "नमस्ते, मैं सारा हूँ। कैसे मदद करूँ?", "provider": "local-check-in"})
            if path == "speech-text":
                return route.fulfill(json={"text": "नमस्ते, मैं सारा हूँ। कैसे मदद करूँ?", "playback": [{"text": "नमस्ते, मैं सारा हूँ। कैसे मदद करूँ?", "lang": "hi-IN"}]})
            if path == "tts/windows":
                windows_calls.append(route.request.post_data_json)
                if mode["windows"] == "failure":
                    return route.fulfill(status=503, json={"error": "Mock Windows generation failure"})
                return route.fulfill(body=b"RIFF-mocked-wave", content_type="audio/wav")
            return route.fallback()

        page.route("**/api/**", api)
        page.goto(dashboard_fixture(page, "fixture"))
        expect(page.locator("#send-button")).to_be_enabled()
        page.wait_for_function("Array.from(document.querySelector('#voice-select').options).some(o=>o.value==='windows:kalpana-local')")
        page.locator("#start-conversation").click()
        page.wait_for_function("__startVoice.audio.length===1")
        assert greetings[0]["kind"] == "greeting", greetings
        assert windows_calls[0]["voice"] == "kalpana-local", windows_calls
        assert page.evaluate("localStorage.getItem('sara-auto-speak')") == "true"
        assert page.evaluate("localStorage.getItem('sara-wake')") == "true"
        assert page.locator("#character-stage").get_attribute("data-state") != "speaking"
        assert page.evaluate("__startVoice.utterances.length") == 0
        page.evaluate("__startVoice.audio[0].onplaying()")
        expect(page.locator("#character-stage")).to_have_attribute("data-state", "speaking")
        expect(page.locator("#voice-status")).to_contain_text("Microsoft Kalpana")
        page.evaluate("__startVoice.audio[0].onended()")
        expect(page.locator("#stop-speech")).to_be_hidden()

        mode["windows"] = "failure"
        page.locator("#start-conversation").click()
        page.wait_for_function("__startVoice.utterances.length===1")
        assert len(greetings) == 2 and len(windows_calls) == 2
        assert page.locator("#character-stage").get_attribute("data-state") != "speaking"
        page.evaluate("__startVoice.startBrowser()")
        expect(page.locator("#character-stage")).to_have_attribute("data-state", "speaking")
        page.evaluate("__startVoice.endBrowser()")
        expect(page.locator("#stop-speech")).to_be_hidden()
        expect(page.locator("#retry-voice")).to_be_hidden()
        assert not errors, errors
        print("PASS: Start conversation enables speech/wake and requests greeting; installed Windows voice used; HUD waits for actual audio onplaying; failed Windows generation falls back to browser voice onstart/end")
        browser.close()


if __name__ == "__main__":
    main()
