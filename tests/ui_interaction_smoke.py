"""Browser regression check with mocked API/speech; no messages are saved."""
import json
import sys
from playwright.sync_api import sync_playwright


def main():
    url = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765").rstrip("/")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script("""
            window.__spoken = [];
            const voices = [
              {name:'Microsoft Ravi',lang:'en-IN',voiceURI:'ravi',default:true},
              {name:'Microsoft Heera',lang:'en-IN',voiceURI:'heera'},
              {name:'Microsoft Kalpana',lang:'hi-IN',voiceURI:'kalpana'}
            ];
            Object.defineProperty(window,'speechSynthesis',{value:{
              getVoices:()=>voices,addEventListener:()=>{},cancel:()=>{},resume:()=>{},
              speak:u=>{window.__spoken.push({text:u.text,lang:u.lang,voice:u.voice?.name});queueMicrotask(()=>{u.onstart?.();u.onend?.();});}
            }});
            window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};
            localStorage.setItem('sara-auto-speak','true');
            localStorage.setItem('sara-wake','false');
            localStorage.setItem('sara-voice-uri','heera');
        """)

        def api(route):
            path = route.request.url.split("/api/")[-1]
            payload = {"agenda": {"tasks": [], "events": [], "reminders": []}, "memories": [],
                       "conversations": [], "activity": [], "policy": {"stopped": False, "actions": {}},
                       "capabilities": {}, "health": {"ollama": True, "model": "test", "natural_voice": False}}
            if path == "chat":
                route.fulfill(content_type="application/x-ndjson", body="\n".join(json.dumps(item) for item in [
                    {"type": "start"}, {"type": "delta", "text": "SARA can "},
                    {"type": "delta", "text": "help quickly."},
                    {"type": "done", "reply": "SARA can help quickly.", "provider": "ollama", "timing": {"total_ms": 125, "first_token_ms": 20}}
                ]) + "\n")
            elif path == "speech-text":
                route.fulfill(json={"text": "Sara मदद application programming interface", "segments": [
                    {"text": "Sara", "lang": "en-IN"}, {"text": "मदद", "lang": "hi-IN"},
                    {"text": "application programming interface", "lang": "en-IN"}],
                    "playback": [{"text": "सारा मदद एप्लिकेशन प्रोग्रामिंग इंटरफ़ेस", "lang": "hi-IN"}]})
            else:
                route.fulfill(json=payload.get(path, {}))

        page.route("**/api/**", api)
        page.goto(url)
        page.locator("#send-button:not([disabled])").wait_for()
        # A prompt button must still work even though body itself has data-view.
        page.locator('.hero-actions button[data-prompt]').click()
        page.locator('.message.assistant .message-text').filter(has_text="SARA can help quickly.").wait_for()
        page.wait_for_function("window.__spoken.length === 1")
        spoken = page.evaluate("window.__spoken")
        assert [item["voice"] for item in spoken] == ["Microsoft Kalpana"], spoken
        assert page.locator('.message.assistant').count() == 1
        assert page.locator('#thinking').is_hidden()
        assert page.locator('#send-button').is_enabled()
        assert not errors, errors
        print("PASS: prompt navigation, streamed reply, no duplicate message, one continuous mixed-language phrase, idle controls")
        browser.close()


if __name__ == "__main__":
    main()
