"""Named-chat navigation and offline productivity workflows in a routed browser."""
from playwright.sync_api import sync_playwright,expect
from browser_fixture import dashboard_fixture
from urllib.parse import urlsplit,parse_qs

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':900},reduced_motion='reduce')
    page.add_init_script("localStorage.setItem('sara-auto-speak','false');localStorage.setItem('sara-wake','false');")
    page.clock.install()
    records={};counter=[0];errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def route_api(route):
        parsed=urlsplit(route.request.url);path=parsed.path
        body=route.request.post_data_json if route.request.method=='POST' else {}
        if path=='/api/chats':return route.fulfill(json=[{'id':key,'title':row['title']} for key,row in records.items()])
        if path=='/api/chats/create':
            counter[0]+=1;key=f'{counter[0]:032x}';records[key]={'title':'New chat','messages':[]}
            return route.fulfill(json={'id':key,'title':'New chat'})
        if path=='/api/conversations':return route.fulfill(json=records[parse_qs(parsed.query)['chat_id'][0]]['messages'])
        if path=='/api/chats/rename':records[body['chat_id']]['title']=body['title'];return route.fulfill(json={'ok':True})
        if path=='/api/chats/delete':del records[body['chat_id']];return route.fulfill(json={'ok':True})
        if path=='/api/chat':
            row=records[body['chat_id']];row['messages'].append({'question':body['message'],'answer':'Reply '+body['message']});row['title']=body['message']
            return route.fulfill(json={'reply':'Reply '+body['message'],'provider':'fixture'})
        return route.fallback()
    page.route('**/api/**',route_api)
    page.goto(dashboard_fixture(page,'fixture'));expect(page.locator('#send-button')).to_be_enabled()
    page.locator('#message').fill('Physics');page.locator('#send-button').click();expect(page.locator('#messages')).to_contain_text('Reply Physics')
    first=page.locator('#chat-picker').input_value()
    page.locator('#new-chat').click();expect(page.locator('#messages')).to_be_empty()
    second=page.locator('#chat-picker').input_value();assert second!=first
    page.locator('#message').fill('Shopping');page.locator('#send-button').click();expect(page.locator('#messages')).to_contain_text('Reply Shopping')
    page.locator('#chat-picker').select_option(first);expect(page.locator('#messages')).to_contain_text('Reply Physics');expect(page.locator('#messages')).not_to_contain_text('Shopping')
    page.reload();expect(page.locator('#messages')).to_contain_text('Reply Physics')
    page.once('dialog',lambda dialog:dialog.accept('Physics revision'));page.locator('#rename-chat').click();expect(page.locator('#chat-picker option:checked')).to_have_text('Physics revision')
    with page.expect_download() as downloaded:page.locator('#export-chat').click()
    assert downloaded.value.suggested_filename=='sara-chat.txt'
    page.once('dialog',lambda dialog:dialog.accept());page.locator('#delete-chat').click();expect(page.locator('#messages')).to_contain_text('Shopping')
    page.locator('[data-view="day"]').first.click()
    page.locator('#focus-minutes').fill('1');page.locator('#focus-minutes').dispatch_event('change');page.locator('#focus-start').click()
    page.clock.fast_forward(30000);expect(page.locator('#focus-clock')).to_have_text('00:30')
    page.reload();expect(page.locator('#focus-clock')).to_have_text('00:30')
    page.clock.fast_forward(30000);expect(page.locator('#focus-count')).to_contain_text('1 sessions');expect(page.locator('#focus-status')).to_contain_text('Focus complete')
    page.locator('#focus-next').click();expect(page.locator('#focus-phase')).to_have_text('Break')
    page.locator('#study-source').fill('Velocity? :: Speed with direction\nForce? :: Mass times acceleration');page.locator('#study-save').click();expect(page.locator('#study-card')).to_have_text('Velocity?')
    page.locator('#study-flip').click();expect(page.locator('#study-card')).to_have_text('Speed with direction');page.locator('#study-known').click();expect(page.locator('#study-card')).to_have_text('Force?')
    page.reload();expect(page.locator('#study-card')).to_have_text('Velocity?')
    page.locator('#task-text').fill('Review physics');page.locator('#task-priority').select_option('high');page.locator('#task-category').select_option('study');page.locator('#task-form button').click();expect(page.locator('#confirmation-details')).to_contain_text('high');expect(page.locator('#confirmation-details')).to_contain_text('study');page.locator('#cancel-action').click()
    for width,height in ((1024,600),(390,844)):
        page.set_viewport_size({'width':width,'height':height});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert not errors,errors
    browser.close()
print('PASS: create/switch/rename/export/delete chats, isolated UI, timer deadline/reload, flashcards and task review.')
