"""Isolated attachment/permission UI regressions; no camera, screen or server.

Media comes from a test canvas stream. Model/access APIs are controlled mocks.
"""
from pathlib import Path
from playwright.sync_api import expect, sync_playwright
from browser_fixture import dashboard_fixture

ROOT = Path(__file__).resolve().parent.parent


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        # Exercise this module without the surrounding speech/chat controller.
        html = (ROOT / "index.html").read_text(encoding="utf-8").replace('<script type="module" src="/assets/dashboard.js"></script>', '')

        def assets(route):
            path = route.request.url.split("localhost")[-1]
            if path == "/":
                return route.fulfill(body=html, content_type="text/html; charset=utf-8")
            if path in ("/assets/vision-client.js", "/assets/vision-controls.css"):
                return route.fulfill(path=str(ROOT / path.lstrip("/")), content_type="text/javascript" if path.endswith(".js") else "text/css")
            return route.fallback()

        page.route("**/*", assets)
        page.goto(dashboard_fixture(page, "fixture"))
        page.evaluate("""async () => {
          document.body.dataset.view='home';
          const c=window.__visualTest={requests:[],calls:[],stopped:0,mode:'review',errors:[]};
          c.makeStream=()=>{
            const canvas=document.createElement('canvas');canvas.width=320;canvas.height=200;
            const ctx=canvas.getContext('2d');ctx.fillStyle='#07c';ctx.fillRect(0,0,320,200);
            const stream=canvas.captureStream(5);
            stream.getTracks().forEach(track=>{const stop=track.stop.bind(track);track.stop=()=>{c.stopped++;stop();};});
            return stream;
          };
          Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{
            getDisplayMedia:async()=>{c.requests.push('screen');return c.makeStream();},
            getUserMedia:async()=>{c.requests.push('camera');return c.makeStream();}
          }});
          const {initializeVisionControls}=await import('/assets/vision-client.js');
          window.__vision=initializeVisionControls({onError:e=>c.errors.push(e),request:async(path,body)=>{
            c.calls.push({path,body});
            if(path==='/api/access-mode'){if(body)c.mode=body.mode;return {mode:c.mode};}
            if(path==='/api/vision/status')return {available:false,reason:'Install a local vision model.',model:null};
            throw new Error('Unexpected test API');
          }});
          c.imageFile=async(name='test.png',type='image/png')=>{
            const canvas=document.createElement('canvas');canvas.width=10;canvas.height=10;
            canvas.getContext('2d').fillRect(0,0,10,10);
            return new File([await new Promise(resolve=>canvas.toBlob(resolve,'image/png'))],name,{type});
          };
          c.paste=async(name)=>{const data=new DataTransfer();data.items.add(await c.imageFile(name));
            document.querySelector('#message').dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));};
        }""")
        assert page.evaluate("__visualTest.requests.length") == 0, "Media started without a click"
        assert page.evaluate("async()=>await __vision.captureSharedView()") is None
        assert page.evaluate("__visualTest.requests.length") == 0, "A check-in requested media permission on its own"
        expect(page.locator("#proactive-vision")).not_to_be_checked()
        expect(page.locator("#vision-model-status")).to_have_text("Install a local vision model.")
        page.evaluate("__visualTest.paste('first.png')")
        expect(page.locator(".attachment-card")).to_have_count(1)
        assert not page.locator("#message").evaluate("node=>node.required")
        page.evaluate("async()=>{window.__sent=await __vision.attachmentsForMessage();}")
        assert page.evaluate("__sent[0].source") == "upload"
        assert page.evaluate("__sent[0].data_url.startsWith('data:image/jpeg;base64,')")
        page.evaluate("__visualTest.paste('added-during-reply.png')")
        expect(page.locator(".attachment-card")).to_have_count(2)
        page.evaluate("__vision.clearSentAttachments(__sent)")
        expect(page.locator(".attachment-card")).to_have_count(1)
        expect(page.locator(".attachment-card>span")).to_have_text("added-during-reply.png")
        page.locator("#attachment-input").set_input_files({"name": "bad.svg", "mimeType": "image/svg+xml", "buffer": b"<svg/>"})
        expect(page.locator("#attachment-error")).to_contain_text("PNG, JPEG or WebP")
        expect(page.locator(".attachment-card")).to_have_count(1)
        page.locator(".attachment-remove").click()
        assert page.locator("#message").evaluate("node=>node.required")
        page.evaluate("async()=>{for(let i=0;i<5;i++)await __visualTest.paste('bounded-'+i+'.png');}")
        expect(page.locator(".attachment-card")).to_have_count(4)
        expect(page.locator("#attachment-error")).to_contain_text("Up to four images")
        for _ in range(4):
            page.locator(".attachment-remove").first.click()

        page.locator("#share-screen").click()
        page.wait_for_function("document.querySelector('#visual-video').videoWidth===320")
        expect(page.locator("#visual-status")).to_contain_text("Screen preview active")
        assert page.evaluate("__visualTest.requests") == ["screen"]
        assert not page.locator("#message").evaluate("node=>node.required")
        assert page.evaluate("async()=>(await __vision.captureSharedView()).source") == "screen"
        expect(page.locator(".attachment-card")).to_have_count(0)
        page.evaluate("async()=>{window.__frame=await __vision.attachmentsForMessage();}")
        assert page.evaluate("__frame.length===1 && __frame[0].source==='screen'")
        page.locator("#capture-frame").click()
        expect(page.locator(".attachment-card")).to_have_count(1)
        expect(page.locator("#include-live-view")).not_to_be_checked()
        assert page.evaluate("async()=>(await __vision.attachmentsForMessage()).length") == 1, "A frozen frame was duplicated"
        page.locator("#stop-visual").click()
        expect(page.locator("#visual-status")).to_have_text("Screen and camera are off")
        assert page.evaluate("__visualTest.stopped") == 1
        assert page.evaluate("async()=>await __vision.captureSharedView()") is None
        page.locator(".attachment-remove").click()

        # Standalone module has no nav controller; switch the visible view here.
        page.evaluate("document.body.dataset.view='settings';document.querySelector('#dashboard-grid').hidden=true;document.querySelector('#view-settings').hidden=false")
        page.locator("#access-mode").select_option("trusted")
        expect(page.locator("#access-mode-status")).to_contain_text("Trusted routine mode")
        assert page.evaluate("__visualTest.mode") == "trusted"
        page.evaluate("document.body.dataset.view='home';document.querySelector('#dashboard-grid').hidden=false;document.querySelector('#view-settings').hidden=true")
        page.locator("#share-camera").click()
        page.wait_for_function("document.querySelector('#visual-video').videoWidth===320")
        expect(page.locator("#visual-status")).to_contain_text("Camera preview active")
        page.evaluate("window.dispatchEvent(new Event('pagehide'))")
        assert page.evaluate("__visualTest.stopped") == 2
        expect(page.locator("#visual-preview")).to_be_hidden()
        # A late permission result after Stop must release its stream immediately.
        page.evaluate("()=>{navigator.mediaDevices.getDisplayMedia=()=>new Promise(resolve=>__visualTest.grant=resolve);}")
        page.locator("#share-screen").click()
        expect(page.locator("#visual-status")).to_contain_text("Waiting for your permission")
        page.locator("#stop-visual").click()
        page.evaluate("__visualTest.grant(__visualTest.makeStream())")
        page.wait_for_function("__visualTest.stopped===3")
        expect(page.locator("#visual-preview")).to_be_hidden()
        page.evaluate("()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('denied','NotAllowedError');};}")
        page.locator("#share-camera").click()
        expect(page.locator("#attachment-error")).to_contain_text("Access was not granted")
        expect(page.locator("#visual-status")).to_have_text("Screen and camera are off")
        assert not page.evaluate("Object.values(localStorage).some(value=>value.includes('data:image'))")
        # The new control rows must keep the composer in a short laptop window.
        page.set_viewport_size({"width": 1024, "height": 600})
        assert page.locator("#chat-form").bounding_box()["y"] + page.locator("#chat-form").bounding_box()["height"] <= 600
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), "Visual controls overflow mobile width"
        assert not errors, errors
        print("PASS: image paste/preview/removal, four-image bound, image-only validity, sent-queue isolation, SVG rejection, local-model reason, explicit screen/camera snapshots, no duplicate frame, stop/pagehide/late-grant cleanup, denied permission, trusted-mode request, laptop/mobile layout")
        browser.close()


if __name__ == "__main__":
    main()
