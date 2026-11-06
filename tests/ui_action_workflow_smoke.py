"""Browser regression check for reviewed actions, with every API request mocked.

Run against a local SARA/static server:
    python tests/ui_action_workflow_smoke.py http://127.0.0.1:8765
No actual application is opened, note is written, or conversation is saved.
"""

import re
import sys
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    url = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765").rstrip("/")
    proposal_id = "11111111-1111-4111-8111-111111111111"
    cancel_id = "22222222-2222-4222-8222-222222222222"
    note_proposal_id = "33333333-3333-4333-8333-333333333333"
    note_id = "a" * 32
    open_action = {"type": "open_app", "app": "notepad", "proposal_id": proposal_id}
    cancel_action = {"type": "open_app", "app": "calculator", "proposal_id": cancel_id}
    note_text = "Approved memory: I prefer concise Hinglish replies."
    note_action = {"type": "notepad_write", "text": note_text, "proposal_id": note_proposal_id}
    success_text = "Windows accepted the request to open Notepad. The visible window is not verified."
    partial_text = "The note was saved and verified, but Notepad could not be launched."

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 768})
        page = context.new_page()
        errors, posts, held_actions = [], [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script("""
            localStorage.setItem('sara-auto-speak','false');
            localStorage.setItem('sara-wake','false');
            Object.defineProperty(window,'speechSynthesis',{value:{
              getVoices:()=>[],addEventListener:()=>{},cancel:()=>{},resume:()=>{},
              speak:()=>{throw new Error('Action test must not speak.');}
            }});
            window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};
            class NoMicrophone {start(){throw new Error('Action test must not start a microphone.');}abort(){}}
            Object.defineProperty(window,'SpeechRecognition',{value:NoMicrophone});
            Object.defineProperty(window,'webkitSpeechRecognition',{value:NoMicrophone});
        """)

        def api(route):
            path = urlsplit(route.request.url).path.removeprefix("/api/")
            payload = route.request.post_data_json if route.request.method == "POST" else None
            if payload is not None:
                posts.append((path, payload))
            defaults = {
                "agenda": {"tasks": [], "events": [], "reminders": []}, "memories": [],
                "conversations": [], "activity": [], "policy": {"stopped": False, "actions": {}},
                "capabilities": {}, "health": {"ollama": True, "model": "mock", "natural_voice": False},
            }
            if path == "chat":
                message = payload["message"]
                if message == "Open Karo.":
                    reply = {"reply": "Review the same pending action; it has not executed.",
                             "provider": "action-state", "requires_confirmation": True,
                             "review_pending": True, "action": open_action}
                elif message == "Cancel this calculator request":
                    reply = {"reply": "Calculator is ready for review; it has not opened.",
                             "provider": "action-planner", "requires_confirmation": True,
                             "action": cancel_action}
                elif message == "Write my approved memories in Notepad":
                    reply = {"reply": "Review the exact note before saving it.",
                             "provider": "action-planner", "requires_confirmation": True,
                             "action": note_action}
                else:
                    reply = {"reply": "Notepad is ready for review; it has not opened.",
                             "provider": "action-planner", "requires_confirmation": True,
                             "action": open_action}
                route.fulfill(json=reply)
            elif path == "actions/open-app":
                # Keep approval in flight to verify simultaneous clicks cannot send twice.
                held_actions.append(route)
            elif path == "actions/cancel":
                route.fulfill(json={"ok": True, "cancelled": True})
            elif path == "actions/notepad-write":
                route.fulfill(status=502, json={
                    "ok": False, "file_written": True, "text_verified": True,
                    "launch_requested": False, "window_verified": False, "note_id": note_id,
                    "file_path": "D:\\SARA\\data\\notes\\mock.txt",
                    "result": partial_text, "error": "Mocked Notepad launch failure",
                    "recovery": "Read the saved note in its preview.",
                    "action_result": {"proposal_id": note_proposal_id, "type": "notepad_write", "status": "failed"},
                })
            elif path == "notes/" + note_id:
                route.fulfill(content_type="text/plain; charset=utf-8", body=note_text)
            else:
                route.fulfill(json=defaults.get(path, {}))

        context.route("**/api/**", api)
        page.goto(url)
        expect(page.locator("#send-button")).to_be_enabled()

        def send(message):
            page.locator("#message").fill(message)
            page.locator("#send-button").click()
            expect(page.locator("#send-button")).to_be_enabled()

        def action_buttons():
            return page.locator(".message.assistant button.message-action")

        send("Please open Notepad")
        expect(action_buttons()).to_have_count(1)
        expect(page.locator("#confirmation")).not_to_be_visible()
        assert not held_actions, "An unreviewed proposal executed"
        send("Open Karo.")
        expect(page.locator("#confirmation")).to_be_visible()
        expect(page.locator("#confirmation-details")).to_contain_text("notepad")
        expect(action_buttons()).to_have_count(2)
        assert not held_actions, "Text confirmation bypassed exact action review"

        with page.expect_request("**/api/actions/open-app"):
            page.locator("#approve-action").evaluate("button=>{button.click();button.click();}")
        expect(page.locator("#approve-action")).to_be_disabled()
        expect(page.locator("#cancel-action")).to_be_disabled()
        assert len(held_actions) == 1, "Double approval submitted duplicate action requests"
        action_posts = [(path, data) for path, data in posts if path == "actions/open-app"]
        assert len(action_posts) == 1, action_posts
        assert action_posts[0][1]["proposal_id"] == proposal_id
        assert action_posts[0][1]["app"] == "notepad"
        assert action_posts[0][1]["confirmed"] is True
        held_actions.pop().fulfill(json={
            "ok": True, "result": success_text,
            "action_result": {"proposal_id": proposal_id, "type": "open_app", "status": "completed"},
        })
        expect(page.locator("#confirmation")).not_to_be_visible()
        result = page.locator(".message.assistant").filter(has_text=success_text)
        expect(result).to_have_count(1)
        expect(result.locator(".message-author small")).to_contain_text(re.compile("tool", re.I))
        expect(action_buttons()).to_have_count(2)
        for button in action_buttons().all():
            expect(button).to_be_disabled()
        # Old copies of the proposal must remain inert after completion.
        action_buttons().first.evaluate("button=>button.click()")
        assert len([path for path, _ in posts if path == "actions/open-app"]) == 1

        send("Cancel this calculator request")
        action_buttons().last.click()
        expect(page.locator("#confirmation")).to_be_visible()
        expect(page.locator("#confirmation-details")).to_contain_text("calculator")
        with page.expect_request("**/api/actions/cancel"):
            page.locator("#cancel-action").click()
        expect(page.locator("#confirmation")).not_to_be_visible()
        cancel_posts = [data for path, data in posts if path == "actions/cancel"]
        assert len(cancel_posts) == 1 and cancel_posts[0]["proposal_id"] == cancel_id, cancel_posts
        expect(action_buttons().last).to_be_disabled()
        assert len([path for path, _ in posts if path == "actions/open-app"]) == 1

        send("Write my approved memories in Notepad")
        action_buttons().last.click()
        expect(page.locator("#confirmation-details")).to_contain_text(note_text)
        page.locator("#approve-action").click()
        partial = page.locator(".message.assistant").filter(has_text=partial_text)
        expect(partial).to_have_count(1)
        expect(partial.locator(".message-author small")).to_contain_text(re.compile("tool", re.I))
        preview = partial.locator('a[href="/api/notes/' + note_id + '"]')
        expect(preview).to_be_visible()
        expect(partial.locator(".message-text")).not_to_contain_text(re.compile(r"\bDone\b|\bcompleted\b", re.I))
        expect(action_buttons().last).to_be_disabled()
        note_posts = [data for path, data in posts if path == "actions/notepad-write"]
        assert len(note_posts) == 1, note_posts
        assert note_posts[0]["proposal_id"] == note_proposal_id
        assert note_posts[0]["text"] == note_text
        assert note_posts[0]["confirmed"] is True

        # The tab session also survives reload, rather than being regenerated per request.
        original_session = posts[0][1].get("session_id")
        assert original_session and page.evaluate(
            "session=>Object.values(sessionStorage).includes(session)", original_session
        ), "The dashboard session was not stored in sessionStorage"
        page.reload()
        expect(page.locator("#send-button")).to_be_enabled()
        send("Please open Notepad after reload")
        expect(action_buttons()).to_have_count(1)
        # Every mutation, including chat and cancellation, uses one stable tab session.
        sessions = {data.get("session_id") for _, data in posts}
        assert len(sessions) == 1 and next(iter(sessions)), posts
        allowed = {"chat", "actions/open-app", "actions/cancel", "actions/notepad-write"}
        assert not [path for path, _ in posts if path not in allowed], posts
        assert not errors, errors
        print("PASS: session-scoped review, follow-up confirmation, one execution, result evidence, cancellation, partial note recovery")
        browser.close()


if __name__ == "__main__":
    main()
