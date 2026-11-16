"""Exercise actual dashboard ability review/result flows with mocked APIs only."""
import re
from urllib.parse import urlsplit
from playwright.sync_api import expect, sync_playwright
from browser_fixture import dashboard_fixture


def main():
    routine_id, revision, proposal_id = "a" * 32, "v1-reviewed-steps", "22222222-2222-4222-8222-222222222222"
    steps = [{"type": "open_app", "app": "notepad"}, {"type": "media_control", "command": "set_volume", "level": 30}, {"type": "youtube_play", "query": "Instrumental focus music"}]
    partial_text = "Routine 'Work mode': 1/3 steps completed. Audio step failed; later steps were not requested."
    partial = {"ok": False, "partial": True, "result": partial_text, "routine_id": routine_id, "revision": revision,
               "completed_steps": 1, "attempted_steps": 2, "total_steps": 3,
               "step_results": [
                   {"index": 1, "action": steps[0], "status": "completed", "result": {"ok": True, "result": "Notepad launch requested; window not verified."}},
                   {"index": 2, "action": steps[1], "status": "failed", "result": {"ok": False, "result": "Audio device unavailable."}},
               ]}
    stale_text = "The saved routine changed after review. Reload it before retrying."
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1024, "height": 600})
        page.emulate_media(reduced_motion="reduce")
        page.add_init_script("""
          localStorage.setItem('sara-auto-speak','false');localStorage.setItem('sara-wake','false');
          Object.defineProperty(window,'speechSynthesis',{value:{getVoices:()=>[],addEventListener(){},cancel(){},resume(){},speak(){throw new Error('No audio in ability regression');}}});
          window.SpeechSynthesisUtterance=class {constructor(text){this.text=text;}};
          window.SpeechRecognition=class {start(){throw new Error('No microphone in ability regression');}abort(){}};
        """)
        errors, posts = [], []
        state = {"routines": [], "history": [], "mode": "partial"}
        page.on("pageerror", lambda error: errors.append(str(error)))

        def api(route):
            path = urlsplit(route.request.url).path.removeprefix("/api/")
            method = route.request.method
            payload = route.request.post_data_json if method == "POST" else None
            if payload is not None:
                posts.append((path, payload))
            if path == "audio/status":
                return route.fulfill(json={"available": True, "volume": 45, "muted": False})
            if path == "routines" and method == "GET":
                return route.fulfill(json={"routines": state["routines"]})
            if path == "conversations":
                return route.fulfill(json=state["history"])
            if path == "routines" and method == "POST":
                record = {"id": routine_id, "revision": revision, "name": payload["name"], "steps": payload["steps"]}
                state["routines"] = [record]
                return route.fulfill(json={"ok": True, "routine": record, "result": "Routine 'Work mode' saved with 3 steps."})
            if path == "routines/" + routine_id + "/run":
                return route.fulfill(status=409, json={"ok": False, "error": stale_text, "result": stale_text})
            if path == "chat":
                text = payload["message"]
                if text.startswith("volume "):
                    answer = "Windows volume readback: 30%."
                    state["history"].append({"question": text, "answer": answer, "provider": "trusted-tool"})
                    return route.fulfill(json={"reply": answer, "provider": "trusted-tool", "requires_confirmation": False, "tool_result": {"ok": True, "result": answer, "volume": 30}})
                if text == 'run routine "Work mode"' and state["mode"] == "partial":
                    state["history"].append({"question": text, "answer": partial_text, "provider": "trusted-tool", "step_results": partial["step_results"], "total_steps": 3})
                    return route.fulfill(json={"reply": partial_text, "provider": "trusted-tool", "requires_confirmation": False, "action_status": "failed", "tool_result": partial})
                if text == 'run routine "Work mode"' and state["mode"] == "review":
                    return route.fulfill(json={"reply": "Review the exact saved steps before running.", "provider": "routine-planner", "requires_confirmation": True,
                                              "action": {"type": "run_routine", "id": routine_id, "name": "Work mode", "revision": revision, "steps": steps, "proposal_id": proposal_id}})
                return route.fulfill(status=400, json={"error": "Unexpected mocked ability command."})
            return route.fallback()

        page.route("**/api/**", api)
        page.goto(dashboard_fixture(page, "fixture"))
        expect(page.locator("#send-button")).to_be_enabled()

        def settings():
            page.locator('button[data-view="settings"]').first.click()
            expect(page.locator("#assistant-abilities")).to_be_visible()

        settings()
        expect(page.locator("#abilities-audio-status")).to_contain_text("45%")
        page.locator("#abilities-volume").fill("30")
        page.locator("#abilities-volume-apply").click()
        expect(page.locator(".message.assistant").filter(has_text="Windows volume readback: 30%.")).to_have_count(1)
        assert posts[0][0] == "chat" and posts[0][1]["message"] == "volume 30 percent karo", posts
        assert not any(path == "actions/media-control" for path, _ in posts), "The quick control bypassed chat policy"

        settings()
        page.locator("#routine-name").fill("Work mode")
        page.locator("#routine-add-step").click()
        row = page.locator(".routine-step").nth(1)
        row.locator('[data-role="kind"]').select_option("media_control")
        row.locator('[data-role="level"]').fill("30")
        page.locator("#routine-add-step").click()
        row = page.locator(".routine-step").nth(2)
        row.locator('[data-role="kind"]').select_option("youtube_play")
        row.locator('[data-role="query"]').fill("Instrumental focus music")
        page.locator("#routine-save").click()
        expect(page.locator("#confirmation")).to_be_visible()
        details = page.locator("#confirmation-details")
        expect(details).to_contain_text("Work mode")
        expect(details).to_contain_text("1. open app")
        expect(details).to_contain_text("notepad")
        expect(details).to_contain_text("2. media control")
        expect(details).to_contain_text("set_volume")
        expect(details).to_contain_text("30")
        expect(details).to_contain_text("3. youtube play")
        expect(details).to_contain_text("Instrumental focus music")
        expect(details).not_to_contain_text("[object Object]")
        assert not any(path == "routines" for path, _ in posts), "A routine was saved before approval"
        page.locator("#approve-action").click()
        expect(page.locator("#confirmation")).not_to_be_visible()
        expect(page.locator(".saved-routine")).to_have_count(1)
        save_posts = [body for path, body in posts if path == "routines"]
        assert len(save_posts) == 1 and save_posts[0]["name"] == "Work mode" and save_posts[0]["steps"] == steps
        assert save_posts[0]["confirmed"] is True and save_posts[0]["session_id"]
        # Cancelling a builder review leaves the existing routine unchanged.
        page.locator("#routine-name").fill("Another mode")
        page.locator("#routine-save").click()
        expect(page.locator("#confirmation")).to_be_visible()
        page.locator("#cancel-action").click()
        expect(page.locator("#confirmation")).not_to_be_visible()
        assert len([path for path, _ in posts if path == "routines"]) == 1

        page.locator('.saved-routine [data-role="run"]').click()
        result = page.locator(".message.assistant").filter(has_text=partial_text)
        expect(result).to_have_count(1)
        expect(result).to_contain_text("Notepad launch requested; window not verified.")
        expect(result).to_contain_text("Audio device unavailable.")
        expect(result).to_contain_text(re.compile(r"1.*(?:not requested|not run|unrun|remaining)", re.I))
        result.locator(".routine-outcomes summary").click()
        expect(result.locator(".routine-outcomes ol > li")).to_have_count(2)
        expect(result.locator(".routine-outcomes ol > li").first).to_be_visible()
        expect(result.locator(".routine-outcomes ol > li").nth(0)).to_contain_text("Open app")
        expect(result.locator(".routine-outcomes ol > li").nth(0)).to_contain_text("Completed")
        expect(result.locator(".routine-outcomes ol > li").nth(1)).to_contain_text("Media control")
        expect(result.locator(".routine-outcomes ol > li").nth(1)).to_contain_text("Failed")
        assert not any(path.endswith("/run") for path, _ in posts), "A trusted chat result triggered a duplicate browser execution"
        # Structured per-step evidence must remain after saved history reload.
        page.reload()
        expect(page.locator("#send-button")).to_be_enabled()
        result = page.locator(".message.assistant").filter(has_text=partial_text)
        expect(result).to_have_count(1)
        expect(result).to_contain_text("Notepad launch requested; window not verified.")
        expect(result).to_contain_text("Audio device unavailable.")

        state["mode"] = "review"
        settings()
        page.locator('.saved-routine [data-role="run"]').click()
        page.locator(".message.assistant button.message-action").last.click()
        expect(page.locator("#confirmation")).to_be_visible()
        expect(page.locator("#confirmation-details")).to_contain_text(revision)
        expect(page.locator("#confirmation-details")).to_contain_text("Instrumental focus music")
        page.locator("#approve-action").click()
        expect(page.locator("#confirmation")).not_to_be_visible()
        expect(page.locator(".message.assistant").filter(has_text=stale_text)).to_have_count(1)
        run_posts = [body for path, body in posts if path.endswith("/run")]
        assert len(run_posts) == 1 and run_posts[0]["revision"] == revision and run_posts[0]["steps"] == steps
        assert run_posts[0]["proposal_id"] == proposal_id and run_posts[0]["confirmed"] is True
        expect(page.locator(".message.assistant button.message-action").last).to_be_disabled()
        sessions = {body.get("session_id") for _, body in posts}
        assert len(sessions) == 1 and next(iter(sessions)), posts
        assert {path for path, _ in posts} <= {"chat", "routines", "routines/" + routine_id + "/run"}, posts
        settings()
        for width, height in ((1024, 600), (390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), f"Horizontal overflow at {width}"
        assert not errors, errors
        print("PASS: full-dashboard quick media command, exact routine review/cancel/save, session-bound run/stale rejection, visible and persisted partial step evidence, no duplicate execution, laptop/mobile layout")
        browser.close()


if __name__ == "__main__":
    main()
