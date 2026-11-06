// One explicit route per action. Unknown actions must never open a default URL.
export function actionRequest(action) {
  const a = action || {};
  const id = () => {
    if (!a.id || typeof a.id !== 'string') throw new Error('This action is missing its item ID. Please request it again.');
    return encodeURIComponent(a.id);
  };
  let path, body;
  switch (a.type) {
    case 'open_browser_url': path='/api/actions/open-browser-url'; body={url:a.url}; break;
    case 'open_app': path='/api/actions/open-app'; body={app:a.app,...(a.executable?{executable:a.executable}:{})}; break;
    case 'notepad_write': path='/api/actions/notepad-write'; body={text:a.text}; break;
    case 'browser_open': path='/api/actions/browser-open'; body={url:a.url}; break;
    case 'browser_click_text': path='/api/actions/browser-click-text'; body={url:a.url,text:a.text}; break;
    case 'browser_fill': path='/api/actions/browser-fill'; body={url:a.url,label:a.label,value:a.value}; break;
    case 'whatsapp_send': path='/api/actions/whatsapp-send'; body={phone:a.phone,text:a.text}; break;
    case 'whatsapp_draft': path='/api/actions/whatsapp-draft'; body={phone:a.phone,text:a.text}; break;
    case 'email_draft': path='/api/actions/email-draft'; body={to:a.to,subject:a.subject,body:a.body}; break;
    case 'type_text': path='/api/actions/type-text'; body={text:a.text}; break;
    case 'hotkey': path='/api/actions/hotkey'; body={keys:a.keys}; break;
    case 'click_point': path='/api/actions/click-point'; body={x:a.x,y:a.y}; break;
    case 'save_memory': path='/api/memories'; body={text:a.text}; break;
    case 'delete_memory': path='/api/memories/'+id()+'/delete'; body={}; break;
    case 'save_pronunciation': path='/api/pronunciations'; body={word:a.word,say_as:a.say_as}; break;
    case 'delete_pronunciation': path='/api/pronunciations/'+id()+'/delete'; body={}; break;
    case 'add_custom_app': path='/api/apps'; body={name:a.name,executable:a.executable}; break;
    case 'delete_custom_app': path='/api/apps/'+id()+'/delete'; body={}; break;
    case 'save_capability_request': path='/api/capability-requests'; body={title:a.title,description:a.description}; break;
    case 'delete_capability_request': path='/api/capability-requests/'+id()+'/delete'; body={}; break;
    case 'create_reminder': path='/api/reminders'; body={...a.reminder}; break;
    case 'delete_reminder': path='/api/reminders/'+id()+'/delete'; body={}; break;
    case 'create_task': path='/api/tasks'; body={text:a.text}; break;
    case 'complete_task': path='/api/tasks/'+id()+'/complete'; body={}; break;
    case 'delete_task': path='/api/tasks/'+id()+'/delete'; body={}; break;
    case 'create_event': path='/api/events'; body={...a.event}; break;
    case 'delete_event': path='/api/events/'+id()+'/delete'; body={}; break;
    case 'write_file': path='/api/files/write'; body={path:a.path,content:a.content}; break;
    case 'delete_file': path='/api/files/delete'; body={path:a.path}; break;
    default: throw new Error('This action is not supported by this dashboard. Nothing was executed.');
  }
  return {path,body:{...body,confirmed:true,...(a.proposal_id?{proposal_id:a.proposal_id}:{})}};
}

export function actionDetails(action) {
  const {body} = actionRequest(action);
  const names = {text:'Text',word:'Word or phrase',say_as:'Speak it as',phone:'Recipient phone',to:'Recipient',subject:'Subject',body:'Message',
    url:'Website',path:'File path',content:'Full file content',app:'Application',name:'Shortcut name',executable:'Executable path',title:'Request',description:'What SARA should learn to do',label:'Field',
    value:'Value to enter',keys:'Keyboard shortcut',x:'Screen X',y:'Screen Y',title:'Event',
    start_at:'Starts at',due_at:'Reminder time'};
  const details = Object.entries(body).filter(([key]) => !['confirmed','proposal_id','session_id','id','created','status'].includes(key))
    .map(([key,value]) => [names[key] || key, Array.isArray(value) ? value.join(' + ') : String(value ?? 'Not set')]);
  if (action.id) details.unshift(['Selected item',action.text || action.title || action.label || action.id]);
  return details;
}
