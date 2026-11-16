"""Full dashboard check-ins with virtual time and synthetic canvas media only.

All requests are intercepted. No microphone, screen, camera or live model is used.
"""
from playwright.sync_api import Error, expect, sync_playwright
from browser_fixture import dashboard_fixture


class Session:
    def __init__(self, browser):
        self.page = browser.new_page(viewport={"width": 1366, "height": 768})
        self.page.emulate_media(reduced_motion="reduce")
        self.page.clock.install(time="2026-11-16T00:00:00Z")
        self.errors, self.checkins, self.chats, self.posts = [], [], [], []
        self.held_checkins, self.held_chats = [], []
        self.hold_checkins = self.hold_chats = self.review_chat = False
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.add_init_script("""
          localStorage.setItem('sara-auto-speak','false');
          localStorage.setItem('sara-wake','false');
          localStorage.setItem('sara-proactive','false');
          const c=window.__proactive={media:[],stops:0,snapshots:0};
          const encode=HTMLCanvasElement.prototype.toDataURL;
          HTMLCanvasElement.prototype.toDataURL=function(...args){
            if(this.width===320 && this.height===200)c.snapshots++;
            return encode.apply(this,args);
          };
          c.makeStream=()=>{
            const canvas=document.createElement('canvas');canvas.width=320;canvas.height=200;
            const ctx=canvas.getContext('2d');ctx.fillStyle='#08c';ctx.fillRect(0,0,320,200);
            const stream=canvas.captureStream(0);
            stream.getVideoTracks().forEach(track=>{
              const stop=track.stop.bind(track);track.stop=()=>{c.stops++;stop();};
              track.requestFrame();
            });
            c.canvas=canvas;return stream;
          };
          Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{
            getDisplayMedia:async()=>{c.media.push('screen');return c.makeStream();},
            getUserMedia:async()=>{c.media.push('camera');return c.makeStream();}
          }});
          c.paste=async()=>{
            const canvas=document.createElement('canvas');canvas.width=10;canvas.height=10;
            canvas.getContext('2d').fillRect(0,0,10,10);
            const data=new DataTransfer();
            data.items.add(new File([await new Promise(resolve=>canvas.toBlob(resolve,'image/png'))],'private-queued.png',{type:'image/png'}));
            document.querySelector('#message').dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));
          };
          c.hidden=value=>{
            Object.defineProperty(document,'hidden',{configurable:true,get:()=>value});
            document.dispatchEvent(new Event('visibilitychange'));
          };
        """)
        self.page.route("**/api/**", self.api)
        self.page.goto(dashboard_fixture(self.page, "fixture"))
        expect(self.page.locator("#send-button")).to_be_enabled()

    def api(self, route):
        path = route.request.url.split("/api/")[-1].split("?")[0]
        if route.request.method == "POST":
            self.posts.append(path)
        if path == "check-in":
            self.checkins.append(route.request.post_data_json)
            if self.hold_checkins:
                self.held_checkins.append(route)
                return
            return route.fulfill(json={"reply": "Helpful check-in " + str(len(self.checkins)), "provider": "local-check-in"})
        if path == "chat":
            self.chats.append(route.request.post_data_json)
            if self.hold_chats:
                self.held_chats.append(route)
                return
            if self.review_chat:
                return route.fulfill(json={"reply": "Review the proposed note", "provider": "action-planner", "requires_confirmation": True,
                                           "action": {"type": "notepad_write", "text": "Test only", "proposal_id": "p-test"}})
            return route.fulfill(json={"reply": "User request answered", "provider": "mock"})
        return route.fallback()

    def enable(self, visual=False):
        self.page.locator('button[data-view="settings"]').first.click()
        self.page.locator("#proactive-toggle").check()
        self.page.locator("#proactive-minutes").select_option("5")
        if visual:
            self.page.locator("#proactive-vision").check()
        self.page.locator('button[data-view="chat"]').first.click()

    def idle(self, minutes=6):
        self.page.clock.fast_forward(minutes * 60000)
        self.page.wait_for_timeout(30)

    def wait_count(self, count):
        # A short real event-loop turn lets route callbacks and fetch settle.
        self.page.wait_for_timeout(40)
        assert len(self.checkins) == count, self.checkins

    def release_checkin(self, reply):
        route = self.held_checkins.pop(0)
        try:
            route.fulfill(json={"reply": reply, "provider": "mock"})
        except Error as error:
            # Cancellation can retire the interception before its mock responds.
            if not any(marker in str(error).lower() for marker in ("invalid interception", "already handled", "request", "closed")):
                raise
        self.page.wait_for_timeout(50)
        expect(self.page.locator("#messages")).not_to_contain_text(reply)

    def send(self, text):
        self.page.locator("#message").fill(text)
        self.page.locator("#send-button").click()

    def close(self):
        assert not self.errors, self.errors
        assert set(self.posts) <= {"chat", "check-in"}, self.posts
        self.page.close()


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        plain = Session(browser)
        expect(plain.page.locator("#proactive-vision")).not_to_be_checked()
        plain.idle(10)
        plain.wait_count(0)
        assert plain.page.evaluate("__proactive.media.length") == 0
        plain.enable()
        plain.idle()
        plain.wait_count(1)
        assert plain.checkins[0]["kind"] == "suggestion"
        assert "attachments" not in plain.checkins[0] and "visual" not in plain.checkins[0]
        assert plain.page.evaluate("__proactive.media.length") == 0
        expect(plain.page.locator("#messages")).to_contain_text("Helpful check-in 1")
        plain.close()

        visual = Session(browser)
        visual.enable(visual=True)
        visual.idle()
        visual.wait_count(1)
        assert "attachments" not in visual.checkins[0], "Consent must never start media permission implicitly"
        assert visual.page.evaluate("__proactive.media") == []
        visual.page.evaluate("__proactive.paste()")
        expect(visual.page.locator(".attachment-card")).to_have_count(1)
        visual.page.locator("#share-screen").click()
        visual.page.wait_for_function("document.querySelector('#visual-video').videoWidth===320")
        visual.idle()
        visual.wait_count(2)
        body = visual.checkins[-1]
        assert body["visual"] is True and body["kind"] == "suggestion"
        assert len(body["attachments"]) == 1 and body["attachments"][0]["source"] == "screen", body
        assert body["attachments"][0]["data_url"].startswith("data:image/jpeg;base64,")
        assert visual.page.evaluate("__proactive.media") == ["screen"]
        expect(visual.page.locator(".attachment-card")).to_have_count(1)
        visual.hold_checkins = True
        visual.idle()
        visual.wait_count(3)
        visual.page.locator("#stop-visual").click()
        assert visual.page.evaluate("__proactive.stops") == 1
        visual.release_checkin("Stale reply after Stop")
        before = visual.page.evaluate("__proactive.snapshots")
        visual.hold_checkins = False
        visual.idle()
        visual.wait_count(4)
        assert "attachments" not in visual.checkins[-1]
        assert visual.page.evaluate("__proactive.snapshots") == before
        visual.page.locator("#share-screen").click()
        visual.page.wait_for_function("document.querySelector('#visual-video').videoWidth===320")
        visual.hold_checkins = True
        visual.idle()
        visual.wait_count(5)
        visual.page.locator('button[data-view="settings"]').first.click()
        visual.page.locator("#proactive-vision").uncheck()
        visual.release_checkin("Stale reply after visual consent revoked")
        before = visual.page.evaluate("__proactive.snapshots")
        visual.hold_checkins = False
        visual.idle()
        visual.wait_count(6)
        assert "attachments" not in visual.checkins[-1]
        assert visual.page.evaluate("__proactive.snapshots") == before
        visual.page.locator("#proactive-toggle").uncheck()
        visual.idle(10)
        visual.wait_count(6)
        visual.close()

        typing = Session(browser)
        typing.enable()
        typing.idle(4)
        typing.page.locator("#message").press("a")
        typing.idle(4)
        typing.wait_count(0)
        typing.idle()
        typing.wait_count(1)
        typing.close()

        hidden = Session(browser)
        hidden.enable()
        hidden.page.evaluate("__proactive.hidden(true)")
        hidden.idle(10)
        hidden.wait_count(0)
        hidden.page.evaluate("__proactive.hidden(false)")
        hidden.idle()
        hidden.wait_count(1)
        hidden.close()

        busy = Session(browser)
        busy.enable()
        busy.hold_chats = True
        busy.send("A request is still running")
        expect(busy.page.locator("#send-button")).to_be_disabled()
        # Move Date ahead without consuming the chat's 75-second timeout.
        busy.page.clock.set_system_time(busy.page.evaluate("Date.now()") + 6 * 60000)
        busy.page.clock.run_for(61000)
        busy.wait_count(0)
        busy.held_chats.pop().fulfill(json={"reply": "Busy reply finished", "provider": "mock"})
        expect(busy.page.locator("#send-button")).to_be_enabled()
        busy.close()

        review = Session(browser)
        review.enable()
        review.review_chat = True
        review.send("Prepare a reviewed note")
        review.page.locator(".message-action").last.click()
        expect(review.page.locator("#confirmation")).to_be_visible()
        review.idle(10)
        review.wait_count(0)
        review.close()

        concurrent = Session(browser)
        concurrent.enable()
        concurrent.hold_checkins = True
        concurrent.idle()
        concurrent.wait_count(1)
        concurrent.send("Answer my new question now")
        expect(concurrent.page.locator("#messages")).to_contain_text("User request answered")
        assert concurrent.chats[-1]["message"] == "Answer my new question now"
        concurrent.release_checkin("Stale reply after new question")
        concurrent.close()

        browser.close()
        print("PASS: opt-in idle check-ins; explicit shared-view consent; no queued-image leak or implicit capture; Stop/revocation drops stale replies; typing/hidden/busy/review suppression; new chat interrupts pending check-in")


if __name__ == "__main__":
    main()
