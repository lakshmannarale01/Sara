"""Saved-routine builder and quick media commands without any Windows actions."""
from pathlib import Path
from playwright.sync_api import expect, sync_playwright
from browser_fixture import dashboard_fixture

ROOT = Path(__file__).resolve().parent.parent


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1024, "height": 600})
        page.emulate_media(reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda problem: errors.append(str(problem)))
        html = (ROOT / "index.html").read_text(encoding="utf-8").replace('<script type="module" src="/assets/dashboard.js"></script>', '')

        def assets(route):
            path = route.request.url.split("localhost")[-1]
            if path == "/":
                return route.fulfill(body=html, content_type="text/html; charset=utf-8")
            if path in ("/assets/abilities-client.js", "/assets/abilities-controls.css"):
                return route.fulfill(path=str(ROOT / path.lstrip("/")), content_type="text/javascript" if path.endswith(".js") else "text/css")
            return route.fallback()

        page.route("**/*", assets)
        page.goto(dashboard_fixture(page, "fixture"))
        page.evaluate("""async () => {
          document.body.dataset.view='settings';
          document.querySelector('#dashboard-grid').hidden=true;
          document.querySelector('#welcome-heading').hidden=true;
          document.querySelector('#view-settings').hidden=false;
          const c=window.__abilitiesTest={commands:[],reviews:[],requests:[],errors:[],routines:[],approve:false,audio:{available:true,volume:40,muted:false}};
          const {initializeAbilities}=await import('/assets/abilities-client.js');
          window.__abilities=initializeAbilities({
            request:async(path,body)=>{c.requests.push({path,body});if(path==='/api/audio/status')return {...c.audio};if(path==='/api/routines')return {routines:structuredClone(c.routines)};throw new Error('Unexpected request: '+path);},
            onCommand:async command=>{c.commands.push(command);if(c.failCommand)throw new Error('Command connection failed');},
            onReview:async action=>{
              c.reviews.push(structuredClone(action));if(!c.approve)return false;
              if(action.type==='save_routine')c.routines.push({id:'routine-1',revision:'revision-1',name:action.name,steps:structuredClone(action.steps)});
              if(action.type==='delete_routine')c.routines=c.routines.filter(item=>item.id!==action.id);
              return true;
            },onError:problem=>c.errors.push(problem)
          });
          await __abilities.refresh();
        }""")
        expect(page.locator("#abilities-audio-status")).to_contain_text("40%")
        expect(page.locator("#abilities-audio-status")).to_contain_text("not muted")
        page.locator("#abilities-volume").fill("30")
        assert page.evaluate("__abilitiesTest.commands.length") == 0
        page.locator("#abilities-volume-apply").click()
        page.wait_for_function("__abilitiesTest.commands.length===1")
        assert page.evaluate("__abilitiesTest.commands[0]") == "volume 30 percent karo"
        for command in ("mute karo", "unmute karo", "play pause", "previous song", "next song"):
            page.locator('[data-command="' + command + '"]').click()
        assert page.evaluate("__abilitiesTest.commands") == ["volume 30 percent karo", "mute karo", "unmute karo", "play pause", "previous song", "next song"]
        # Refresh can read live status without silently replacing a user draft.
        page.locator("#abilities-volume").fill("25")
        page.evaluate("__abilitiesTest.audio={available:true,volume:70,muted:true}")
        page.evaluate("__abilities.refresh()")
        expect(page.locator("#abilities-audio-status")).to_contain_text("70%")
        expect(page.locator("#abilities-volume")).to_have_value("25")
        page.locator("#abilities-audio-refresh").click()
        expect(page.locator("#abilities-volume")).to_have_value("70")

        page.locator("#routine-name").fill("Work mode")
        page.locator("#routine-add-step").click()
        row = page.locator(".routine-step").nth(1)
        row.locator('[data-role="kind"]').select_option("media_control")
        row.locator('[data-role="level"]').fill("30")
        page.locator("#routine-save").click()
        page.wait_for_function("__abilitiesTest.reviews.length===1")
        assert page.evaluate("__abilitiesTest.routines.length") == 0, "Rejected review saved a routine"
        review = page.evaluate("__abilitiesTest.reviews[0]")
        assert review["type"] == "save_routine" and review["name"] == "Work mode"
        assert review["steps"] == [{"type": "open_app", "app": "notepad"}, {"type": "media_control", "command": "set_volume", "level": 30}], review
        page.evaluate("__abilitiesTest.approve=true")
        page.locator("#routine-save").click()
        expect(page.locator(".saved-routine")).to_have_count(1)
        expect(page.locator(".saved-routine")).to_contain_text("Work mode")
        expect(page.locator(".saved-routine")).to_contain_text("30%")
        page.locator('.saved-routine [data-role="run"]').click()
        assert page.evaluate("__abilitiesTest.commands.at(-1)") == 'run routine "Work mode"'
        page.evaluate("__abilitiesTest.approve=false")
        page.locator('.saved-routine [data-role="delete"]').click()
        expect(page.locator(".saved-routine")).to_have_count(1)
        removal = page.evaluate("__abilitiesTest.reviews.at(-1)")
        assert {key: removal[key] for key in ("type", "id", "revision", "name")} == {"type": "delete_routine", "id": "routine-1", "revision": "revision-1", "name": "Work mode"}
        page.evaluate("__abilitiesTest.approve=true")
        page.locator('.saved-routine [data-role="delete"]').click()
        expect(page.locator(".saved-routine")).to_have_count(0)

        # Invalid names/levels/URLs never reach action review.
        before = page.evaluate("__abilitiesTest.reviews.length")
        page.locator("#routine-name").fill('Bad "name"')
        page.locator("#routine-save").click()
        expect(page.locator("#abilities-error")).to_contain_text("without quotes")
        page.locator("#routine-name").fill("Another mode")
        row.locator('[data-role="level"]').fill("101")
        page.locator("#routine-save").click()
        expect(page.locator("#abilities-error")).to_contain_text("0 to 100")
        row.locator('[data-role="kind"]').select_option("website")
        row.locator('[data-role="url"]').fill("javascript:alert(1)")
        page.locator("#routine-save").click()
        expect(page.locator("#abilities-error")).to_contain_text("HTTPS URL")
        assert page.evaluate("__abilitiesTest.reviews.length") == before

        # Search queries remain literal and only active fields form the payload.
        page.evaluate("__abilitiesTest.approve=false")
        row.locator('[data-role="kind"]').select_option("search")
        row.locator('[data-role="query"]').fill("C++ & Python")
        page.locator("#routine-save").click()
        assert page.evaluate("__abilitiesTest.reviews.at(-1).steps[1]") == {"type": "open_browser_url", "url": "https://www.google.com/search?q=C%2B%2B%20%26%20Python"}
        for _ in range(6):
            page.locator("#routine-add-step").click()
        expect(page.locator(".routine-step")).to_have_count(8)
        expect(page.locator("#routine-add-step")).to_be_disabled()
        page.locator('.routine-step [data-role="remove"]').first.click()
        expect(page.locator(".routine-step")).to_have_count(7)
        expect(page.locator("#routine-add-step")).to_be_enabled()
        expect(page.locator(".routine-step legend").first).to_have_text("Step 1")

        page.evaluate("__abilitiesTest.failCommand=true")
        page.locator('[data-command="mute karo"]').click()
        expect(page.locator("#abilities-error")).to_contain_text("Command connection failed")
        page.evaluate("__abilitiesTest.audio={available:false,reason:'No default audio device'}")
        page.locator("#abilities-audio-refresh").click()
        expect(page.locator("#abilities-audio-status")).to_contain_text("No default audio device")
        expect(page.locator("#abilities-volume-apply")).to_be_disabled()
        expect(page.locator('[data-command="mute karo"]')).to_be_disabled()
        assert page.evaluate("__abilitiesTest.requests.every(request=>!request.body)")
        for width, height in ((1024, 600), (390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), f"Horizontal clipping at {width}"
        page.evaluate("__abilities.destroy()")
        expect(page.locator("#assistant-abilities")).to_have_count(0)
        assert not errors, errors
        print("PASS: readonly live audio status, explicit quick commands, reviewed canonical routine steps, run/delete revision, validation, eight-step bound, error recovery, laptop/mobile layout; no OS actions")
        browser.close()


if __name__ == "__main__":
    main()
