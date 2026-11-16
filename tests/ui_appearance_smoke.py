"""Exercise appearance changes without replacing functional chat controls."""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from browser_fixture import dashboard_fixture

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':900}, reduced_motion='reduce')
    page.add_init_script("localStorage.setItem('sara-auto-speak','false');localStorage.setItem('sara-wake','false');")
    page.clock.install()
    errors=[]
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(dashboard_fixture(page,'fixture'))
    expect(page.locator('#send-button')).to_be_enabled()
    page.locator('#message').fill('Draft stays here')
    page.evaluate('window.originalComposer=document.querySelector("#message")')
    page.locator('[data-view="settings"]').first.click()
    for theme in ('companion','playful','aurora','minimal','jarvis'):
        page.locator('#sara-look').select_option(theme)
        expect(page.locator('html')).to_have_attribute('data-look',theme)
        assert page.evaluate('originalComposer===document.querySelector("#message")')
        expect(page.locator('#message')).to_have_value('Draft stays here')
    page.locator('#sara-look').select_option('playful')
    page.reload()
    expect(page.locator('html')).to_have_attribute('data-look','playful')
    page.locator('[data-view="home"]').first.click()
    page.screenshot(path=str(Path(__file__).resolve().parents[1]/'sara_data/runtime/theme-playful.png'))
    page.locator('#message').fill('hello')
    page.route('**/api/chat',lambda route: route.fulfill(json={'reply':'Hello from the theme check','provider':'fixture'}))
    page.locator('#send-button').click()
    expect(page.locator('#messages')).to_contain_text('Hello from the theme check')
    for width,height in ((1024,600),(390,844)):
        page.set_viewport_size({'width':width,'height':height})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), page.evaluate('({width:innerWidth,overflow:[...document.querySelectorAll("body *")].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>[e.tagName,e.id,e.className,e.getBoundingClientRect().right]).slice(0,20)})')
        page.locator('#message').scroll_into_view_if_needed()
        expect(page.locator('#message')).to_be_visible()
    page.locator('[data-view="settings"]').first.click()
    page.locator('#sara-look-mode').select_option('daily')
    expect(page.locator('#sara-look-mode')).to_have_value('daily')
    expect(page.locator('#send-button')).to_be_enabled()
    page.reload()
    expect(page.locator('#sara-look-mode')).to_have_value('daily')
    page.locator('#sara-look-mode').select_option('session')
    before=page.locator('html').get_attribute('data-look')
    page.locator('[data-view="home"]').first.click()
    page.locator('#message').fill('Unsent work')
    page.clock.fast_forward(1800000)
    expect(page.locator('html')).to_have_attribute('data-look',before)
    page.locator('#message').fill('')
    page.clock.fast_forward(30000)
    assert page.locator('html').get_attribute('data-look')!=before
    assert not errors,errors
    browser.close()
print('Appearance: five looks, saved choice, preserved draft, working chat, responsive widths and daily preference passed.')
