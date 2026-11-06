"""Manual hands-free browser regression check with mocked API, mic and speech.

Run against a local SARA/static server:
    python tests/ui_voice_session_smoke.py http://127.0.0.1:8765
No real microphone, AI service, or saved conversation is used.
"""
import sys

from playwright.sync_api import sync_playwright


def main():
    url = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765").rstrip("/")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        errors, pending_chats, submitted = [], [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.clock.install(time="2026-11-04T06:00:00Z")
        page.add_init_script("""
            localStorage.setItem('sara-auto-speak','true');
            localStorage.setItem('sara-wake','false');
            localStorage.setItem('sara-voice-mode','system');
            localStorage.setItem('sara-voice-uri','heera');
            const control=window.__voice={recognizers:[],utterances:[],speaking:false,pending:false,paused:false};
            class FakeRecognition {
              constructor(){this.aborted=false;this.starts=0;control.recognizers.push(this);}
              start(){this.starts++;}
              abort(){this.aborted=true;}
            }
            Object.defineProperty(window,'SpeechRecognition',{value:FakeRecognition});
            Object.defineProperty(window,'webkitSpeechRecognition',{value:FakeRecognition});
            control.startRecognition=i=>control.recognizers[i].onstart?.();
            control.endRecognition=i=>control.recognizers[i].onend?.();
            control.errorRecognition=(i,error)=>control.recognizers[i].onerror?.({error});
            control.result=(i,text)=>{const result=[{transcript:text}];result.isFinal=true;control.recognizers[i].onresult?.({resultIndex:0,results:[result]});};
            const voices=[
              {name:'Microsoft Heera',lang:'en-IN',voiceURI:'heera',default:true},
              {name:'Microsoft Kalpana',lang:'hi-IN',voiceURI:'kalpana'}
            ];
            Object.defineProperty(window,'speechSynthesis',{value:{
              get speaking(){return control.speaking;},get pending(){return control.pending;},get paused(){return control.paused;},
              getVoices:()=>voices,addEventListener:()=>{},resume:()=>{control.paused=false;},
              cancel:()=>{control.speaking=false;control.pending=false;control.paused=false;},
              speak:u=>{control.utterances.push(u);control.pending=true;}
            }});
            window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};
            control.startSpeech=i=>{control.pending=false;control.speaking=true;control.utterances[i].onstart?.();};
            control.endSpeech=i=>{control.pending=false;control.speaking=false;control.utterances[i].onend?.();};
            control.silentSpeechEnd=()=>{control.pending=false;control.speaking=false;};
            Object.defineProperty(navigator,'permissions',{value:{query:()=>Promise.resolve({state:'prompt',addEventListener:()=>{}})}});
        """)

        def api(route):
            path = route.request.url.split("/api/")[-1].split("?")[0]
            defaults = {"agenda": {"tasks": [], "events": [], "reminders": []}, "memories": [],
                        "conversations": [], "activity": [], "policy": {"stopped": False, "actions": {}},
                        "capabilities": {}, "health": {"ollama": True, "model": "mock", "natural_voice": False}}
            if path == "chat":
                submitted.append(route.request.post_data_json["message"])
                pending_chats.append(route)
            elif path == "speech-text":
                route.fulfill(json={"text": "Sara मदद dashboard ready है।", "segments": [
                    {"text": "Sara", "lang": "en-IN"}, {"text": "मदद", "lang": "hi-IN"},
                    {"text": "dashboard ready", "lang": "en-IN"}, {"text": "है।", "lang": "hi-IN"}],
                    "playback": [{"text": "सारा मदद डैशबोर्ड रेडी है।", "lang": "hi-IN"}]})
            else:
                route.fulfill(json=defaults.get(path, {}))

        page.route("**/api/**", api)
        page.goto(url)
        page.locator("#send-button:not([disabled])").wait_for()
        page.clock.pause_at("2026-11-04T07:00:00Z")

        def count():
            return page.evaluate("__voice.recognizers.length")

        def click_mic():
            page.locator("#mic-button").evaluate("node=>node.click()")

        def until(expression, description):
            # Active protocol queries let network promises settle while keeping
            # all application timers under the virtual clock's control.
            for _ in range(150):
                if page.evaluate(expression):
                    return
                page.clock.run_for(5)
            raise AssertionError(description)

        def reply(text):
            assert pending_chats, "No mocked chat request was submitted"
            pending_chats.pop(0).fulfill(json={"reply": text, "provider": "mock", "timing": {"total_ms": 10}})

        assert count() == 0, "Stored wake=false must not start recognition"
        click_mic()
        page.clock.run_for(1)
        assert count() == 1
        assert page.evaluate("localStorage.getItem('sara-wake')") == "true"
        # A recognizer that has not emitted onstart still owns the pending start.
        page.evaluate("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Shift'}))")
        page.clock.run_for(1000)
        assert count() == 1, "Pending recognition start spawned a duplicate instance"
        page.evaluate("__voice.startRecognition(0)")
        page.evaluate("__voice.result(0,'Tell me something useful')")
        until("document.querySelector('#send-button').disabled", "Transcript did not start chat")
        assert page.evaluate("__voice.recognizers[0].aborted")
        page.clock.run_for(1000)
        assert count() == 1, "Recognition restarted while AI reply was pending"
        reply("A useful first reply.")
        until("__voice.utterances.length===1", "Reply did not prepare one fluent playback utterance")
        assert page.evaluate("__voice.utterances[0].voice.name") == "Microsoft Kalpana"
        assert count() == 1, "Recognition resumed while speech was pending"
        page.evaluate("__voice.startSpeech(0)")
        page.clock.run_for(66000)
        assert count() == 1, "Valid long speech was cut off or mic resumed over it"
        page.evaluate("__voice.endSpeech(0)")
        page.clock.run_for(300)
        assert count() == 2, "Mic did not rearm automatically after long speech"
        page.evaluate("__voice.startRecognition(1)")
        page.evaluate("__voice.result(1,'And what next?')")
        until("document.querySelector('#send-button').disabled", "Direct follow-up was ignored after long reply")
        assert submitted == ["Tell me something useful", "And what next?"], submitted
        reply("A useful second reply.")
        until("__voice.utterances.length===2", "Second reply did not reach speech")
        page.evaluate("__voice.startSpeech(1)")
        page.clock.run_for(1000)
        page.evaluate("__voice.silentSpeechEnd()")
        page.clock.run_for(2500)
        assert count() == 3, "Idle speech engine without onend left microphone stuck"
        page.evaluate("__voice.startRecognition(2)")
        page.evaluate("__voice.errorRecognition(2,'network')")
        assert page.evaluate("localStorage.getItem('sara-wake')") == "true"
        page.clock.run_for(900)
        assert count() == 3, "Transient retry ignored backoff"
        page.clock.run_for(400)
        assert count() == 4, "Transient recognition failure required another click"
        page.evaluate("__voice.startRecognition(3)")
        click_mic()
        assert page.evaluate("localStorage.getItem('sara-wake')") == "false"
        page.evaluate("__voice.endRecognition(3); __voice.errorRecognition(3,'network'); __voice.startRecognition(3)")
        page.clock.run_for(10000)
        assert count() == 4, "Stale events restarted an explicitly stopped mic"
        assert page.locator("#mic-button").get_attribute("aria-pressed") == "false"
        click_mic()
        page.clock.run_for(1)
        assert count() == 5
        page.evaluate("__voice.startRecognition(4); __voice.errorRecognition(4,'not-allowed'); __voice.endRecognition(4)")
        assert page.evaluate("localStorage.getItem('sara-wake')") == "true"
        page.clock.run_for(20000)
        assert count() == 5, "Permission denial entered an automatic retry loop"
        click_mic()
        page.clock.run_for(1)
        assert count() == 6, "Explicit permission retry could not restart recognition"
        page.evaluate("__voice.startRecognition(5)")
        assert page.locator("#mic-button").get_attribute("aria-pressed") == "true"
        # When the direct-reply window expires, listening remains active and
        # the wake word opens the next turn without another mic click.
        page.clock.run_for(61000)
        assert count() == 6, "Idle follow-up expiry restarted or stopped recognition"
        assert "Sara" in page.locator("#voice-status").inner_text()
        assert page.locator("#mic-button").get_attribute("aria-pressed") == "true"
        before_expired_followup = len(submitted)
        page.evaluate("__voice.result(5,'A direct follow-up after expiry')")
        page.clock.run_for(500)
        assert len(submitted) == before_expired_followup, "Expired direct follow-up bypassed the wake word"
        page.evaluate("__voice.result(5,'Sara tell me what is next')")
        until("document.querySelector('#send-button').disabled", "Wake word was not accepted after idle expiry")
        assert submitted[-1] == "tell me what is next", submitted
        reply("A useful third reply.")
        until("__voice.utterances.length===3", "Wake-word reply did not reach speech")
        page.evaluate("__voice.startSpeech(2); __voice.endSpeech(2)")
        page.clock.run_for(300)
        assert count() == 7
        page.evaluate("__voice.startRecognition(6)")
        click_mic()
        assert not pending_chats
        assert not errors, errors
        print("PASS: one-click hands-free session, >65s speech follow-up, idle expiry stays in wake mode, one fluent utterance, native idle watchdog, transient reconnect, explicit stop, stale callbacks, pending-start guard, permission retry gate")
        browser.close()


if __name__ == "__main__":
    main()
