import {actionRequest, actionDetails} from './action-router.js';
import {createHudCore} from './hud-core.js';
import {initializeVisionControls} from './vision-client.js';
import {initializeAbilities} from './abilities-client.js';
import {initializeAppearance} from './appearance.js';
import {initializeChats} from './chat-library.js';
import {initializeProductivity} from './productivity.js';

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const hudCore=createHudCore($('#hud-canvas'),$('#character-stage'));
let SESSION_ID=(()=>{try {let id=sessionStorage.getItem('sara-session-id');if(!/^[A-Za-z0-9_-]{8,80}$/.test(id || '')){id=crypto.randomUUID();sessionStorage.setItem('sara-session-id',id);}return id;}catch{return 'session-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);}})();
let ACTIVE_CHAT='';
const prefs = {
  get(key, fallback='') { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, String(value)); } catch { /* Settings still work for this session. */ } }
};
const state = {view:'home',busy:false,stopped:false,memories:[],pronunciations:[],apps:{built_in:[],custom:[]},capabilityRequests:[],agenda:{tasks:[],events:[],reminders:[]},
  speak:prefs.get('sara-auto-speak','true')==='true',proactive:prefs.get('sara-proactive','false')==='true',
  voiceMode:prefs.get('sara-voice-mode','system'),naturalVoiceAvailable:false,windowsVoices:[],audio:null,audioUrl:null,audioController:null,
  healthChecked:0,capabilitiesChecked:0,ready:false,historyLoaded:false,utterances:[],speechStarted:false,
  wake:prefs.get('sara-wake','true')==='true',wakeGestureReady:false,
  recognizing:false,recognitionStarting:false,recognitionBlocked:'',recognitionFailures:0,recognitionRetryAt:0,
  voiceConversation:false,wakeUntil:0,speaking:false,speechSequence:0,lastVoicePlayback:'',dialog:null,refreshing:false};
state.pendingAction=null;
initializeAppearance({canRotate:()=>!state.busy&&!state.speaking&&!state.recognizing&&!state.dialog&&!state.pendingAction&&!document.querySelector('#message')?.value});
let recognition=null, recognitionTimer=null, recognitionStartTimer=null, followUpTimer=null, toastTimer=null, speechWatchdog=null;
const FOLLOW_UP_MS=60000;
const speechCache=new Map();
let voiceListWaitCompleted=false;
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const wakeHelp=[...document.querySelectorAll('.settings-card .card-note')].find(node=>node.textContent.startsWith('Microphone starts'));
if(wakeHelp) wakeHelp.textContent="Hands-free listening resumes after each reply. Click the microphone once to start a conversation; direct follow-ups stay open for 60 seconds after Sara finishes. After that, say Sara again. Click the active microphone to stop. Browser microphone permission is required; recognition may use an online speech service.";

function el(tag, className='', text='') {
  const node=document.createElement(tag);
  if(className) node.className=className;
  if(text !== '') node.textContent=String(text);
  return node;
}
function icon(name) {
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  const use=document.createElementNS('http://www.w3.org/2000/svg','use');
  use.setAttribute('href','#i-'+name);svg.setAttribute('aria-hidden','true');svg.append(use);return svg;
}
function toast(message) {
  clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').hidden=false;
  toastTimer=setTimeout(()=>{$('#toast').hidden=true;},5500);
}
async function api(path, body, timeout=12000, signal) {
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
  const cancel=()=>controller.abort();
  signal?.addEventListener('abort',cancel,{once:true});if(signal?.aborted)cancel();
  try {
    const response=await fetch(path,{method:body===undefined?'GET':'POST',
      headers:body===undefined?{}:{'Content-Type':'application/json'},
      body:body===undefined?undefined:JSON.stringify({...body,session_id:SESSION_ID,...(ACTIVE_CHAT&&body.chat_id===undefined?{chat_id:ACTIVE_CHAT}:{})}),signal:controller.signal});
    const data=await response.json();
    if(!response.ok){const error=new Error((typeof data.result==='string'?data.result:data.error) || (data.requires_confirmation?'Please review and approve this action first.':'Request failed ('+response.status+').'));error.details=data;throw error;}
    return data;
  } catch(error) {
    if(error.name==='AbortError') throw new Error('The request timed out. Its outcome is unknown; check activity before retrying an action.');
    if(error instanceof TypeError) throw new Error('Could not reach SARA. Start the local server and try again.');
    throw error;
  } finally {clearTimeout(timer);signal?.removeEventListener('abort',cancel);}
}
async function chatApi(message,onDelta,attachments=[]) {
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),attachments.length?120000:75000);
  let reader;
  try {
    const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/x-ndjson'},body:JSON.stringify({message,session_id:SESSION_ID,...(ACTIVE_CHAT?{chat_id:ACTIVE_CHAT}:{}),...(attachments.length?{attachments}:{})}),signal:controller.signal});
    if(!response.ok){const data=await response.json();throw new Error(data.error || 'Chat request failed.');}
    if(!response.headers.get('Content-Type')?.includes('application/x-ndjson'))return await response.json();
    reader=response.body.getReader();const decoder=new TextDecoder();let buffer='',result=null;
    const consume=line=>{if(!line.trim())return;const event=JSON.parse(line);if(event.type==='delta')onDelta(event.text);else if(event.type==='done')result=event;else if(event.type==='error')throw new Error(event.error || 'The reply could not complete.');};
    while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value || new Uint8Array(),{stream:!done});let newline;while((newline=buffer.indexOf('\n'))!==-1){consume(buffer.slice(0,newline));buffer=buffer.slice(newline+1);}if(done)break;}
    if(buffer.trim())consume(buffer);
    if(!result)throw new Error('Connection ended before the reply completed.');
    return result;
  } catch(error) {
    if(error.name==='AbortError')throw new Error('AI response took too long. Please try a shorter question or check Ollama.');
    throw error;
  } finally {clearTimeout(timer);reader?.releaseLock();}
}
const visualInputs=initializeVisionControls({request:api,onError:toast,onImagesChange:info=>{
  if(!info.activeSource && state.checkInVisual)cancelCheckIn();
}});
const abilityControls=initializeAbilities({request:api,onCommand:submitMessage,onReview:reviewAction,onError:toast});
const chatLibrary=initializeChats({request:api,onError:toast,isBusy:()=>state.busy||state.preparingMessage||state.dialog||state.pendingAction||Boolean($('#message').value)||visualInputs.getChatAttachments().length>0,onSelect:async(id,messages)=>{
  cancelCheckIn();stopSpeech();pauseRecognition();
  let previous=ACTIVE_CHAT;try{previous=previous||sessionStorage.getItem('sara-session-chat');}catch{}
  if(previous&&previous!==id){SESSION_ID=crypto.randomUUID();try{sessionStorage.setItem('sara-session-id',SESSION_ID);}catch{}}
  try{sessionStorage.setItem('sara-session-chat',id);}catch{}
  ACTIVE_CHAT=id;state.lastInteraction=Date.now();$('#messages').replaceChildren();
  for(const item of messages){if(item.initiated_by!=='sara')addMessage(item.question||'','you','',item.time);const content=addMessage(item.answer||'','sara',item.provider,item.time);appendStepResults(content,item);}
}});
state.lastInteraction=Date.now();
initializeProductivity({onError:toast,onCommand:submitMessage});

function dateText(value, empty='Time not set') {
  const date=new Date(value);
  return value && !Number.isNaN(date.getTime()) ? date.toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}) : empty;
}
function humanize(value) {return String(value).replaceAll('_',' ').replace(/^./,s=>s.toUpperCase());}
function empty(target,title,description) {
  const box=el('div','empty-state');box.append(el('strong','',title),el('p','',description));target.append(box);
}
function setView(view, updateHash=true) {
  if(!['home','chat','day','memories','activity','settings'].includes(view)) view='home';
  state.view=view;
  document.body.dataset.view=view;
  const chatView=['home','chat'].includes(view);
  $('#dashboard-grid').hidden=!chatView;$('#welcome-heading').hidden=view!=='home';
  $('#hero').hidden=!chatView;$('#starter-grid').hidden=view!=='home';
  $('#dashboard-grid').classList.toggle('chat-only',view==='chat');
  $$('.detail-view').forEach(node=>{node.hidden=node.id!=='view-'+view;});
  $$('.nav-item').forEach(node=>{const active=node.dataset.view===view;node.classList.toggle('active',active);if(active)node.setAttribute('aria-current','page');else node.removeAttribute('aria-current');});
  $('#view-name').textContent={home:'Command center',chat:'Talk to SARA',day:'My day',memories:'Memories',activity:'Activity',settings:'Settings & controls'}[view];
  if(updateHash) history.replaceState(null,'','#'+view);
  if(state.ready && ['day','memories','activity','settings'].includes(view))void refreshData();
  if(state.ready && view==='settings')void abilityControls.refresh();
}
function setCharacter(status) {
  const stage=$('#character-stage');stage.dataset.state=status;
  const label={ready:'Ready for your command',thinking:'Thinking it through',listening:'Listening to you',speaking:'Speaking',review:'Waiting for your approval'}[status] || 'Ready for your command';
  $('#character-status').textContent=label;stage.setAttribute('aria-label','SARA: '+label);
  hudCore.setState(status);
}
function addMessage(text,who='sara',provider='',savedTime) {
  $('#chat-welcome')?.remove();
  const row=el('div','message '+(who==='you'?'user':'assistant'));
  row.append(el('span',who==='you'?'user-avatar':'sara-monogram',who==='you'?'Y':'✦'));
  const content=el('div','message-content'),author=el('div','message-author',who==='you'?'You':'SARA');
  if(provider) author.append(el('small','',provider==='ollama'?'Local AI':provider==='openai'?'Cloud AI':provider==='safe-local'?'Local fallback':humanize(provider)));
  if(savedTime) row.title=dateText(savedTime);
  content.append(author,el('div','message-text',text));row.append(content);$('#messages').append(row);
  $('#messages').scrollTop=$('#messages').scrollHeight;return content;
}
function setBusy(busy) {
  state.busy=busy;$('#send-button').disabled=busy;$('#thinking').hidden=!busy;
  $$('[data-prompt]').forEach(button=>{button.disabled=busy;});
  if(busy) {stopSpeech();pauseRecognition();setCharacter('thinking');}
  else {if(!state.speaking)openFollowUpWindow();setCharacter(state.dialog?'review':state.speaking&&state.speechStarted?'speaking':state.recognizing?'listening':'ready');scheduleWake();}
}
async function submitMessage(message) {
  message=String(message || '').trim();
  if(!state.historyLoaded){toast('Loading your saved conversation…');return;}
  if(state.busy || state.preparingMessage) return;
  let attachments;
  state.preparingMessage=true;
  try {attachments=await visualInputs.attachmentsForMessage();}
  catch(error){toast(error.message);return;}
  finally {state.preparingMessage=false;}
  if(!message && !attachments.length) return;
  cancelCheckIn();
  state.lastInteraction=Date.now();
  setView('chat');$('#message').value='';resizeComposer();
  const userContent=addMessage(message || 'Please explain this image.','you');
  if(attachments.length){
    const previews=el('div','sent-image-previews');
    for(const item of attachments){const img=el('img');img.src=item.data_url;img.alt=item.source+' image shared with this message';img.style.cssText='max-width:120px;max-height:80px;object-fit:contain;margin:6px 6px 0 0';previews.append(img);}
    userContent.append(previews);
  }
  setBusy(true);
  let liveContent=null,streamed='';
  try {
    const data=await chatApi(message,chunk=>{
      streamed+=chunk;
      if(!liveContent)liveContent=addMessage('','sara');
      liveContent.querySelector('.message-text').textContent=streamed;
      $('#thinking').hidden=true;$('#messages').scrollTop=$('#messages').scrollHeight;
    },attachments);
    if(data.provider!=='vision-unavailable')visualInputs.clearSentAttachments(attachments);
    const text=data.reply || 'No reply was returned. Please try again.';
    const content=liveContent || addMessage(text,'sara',data.provider);
    if(liveContent){content.querySelector('.message-text').textContent=text;content.querySelector('.message-author').append(el('small','',humanize(data.provider || 'AI')));}
    appendStepResults(content,data.tool_result);
    if(data.timing){content.title='Reply: '+(data.timing.total_ms/1000).toFixed(1)+'s'+(data.timing.first_token_ms!==null&&data.timing.first_token_ms!==undefined?' · first text '+(data.timing.first_token_ms/1000).toFixed(1)+'s':'');}
    if(data.timing?.incomplete)toast('Reply stopped at the response limit. Ask SARA to continue for more detail.');
    if(data.download==='/api/calendar.ics') {
      const link=el('a','quiet-button message-action','Download calendar ↗');link.href=data.download;link.download='sara-calendar.ics';content.append(link);
    }
    if(data.pending_cancelled && state.pendingAction){settleProposal(state.pendingAction.proposal_id,'Cancelled');state.pendingAction=null;}
    if(data.requires_confirmation && data.action)attachProposal(content,data.action);
    if(data.visual_request==='camera') {
      const action = el('button','visual-command-action','Open camera');
      action.type='button'; action.addEventListener('click',()=>{ action.disabled=true; void visualInputs.startCamera(); });
      content.append(action);
    } else if(data.visual_request==='screen') {
      const action = el('button','visual-command-action','Share screen');
      action.type='button'; action.addEventListener('click',()=>{ action.disabled=true; void visualInputs.startScreen(); });
      content.append(action);
    }
    setBusy(false);
    if(data.review_pending && data.action)void reviewAction(data.action);
    else if(state.speak) void speak(text);
  } catch(error) {addMessage(error.message,'sara','connection');if(!$('#message').value)$('#message').value=message;}
  finally {setBusy(false);void refreshData();void chatLibrary.refresh().catch(()=>{});}
}
function resizeComposer() {const node=$('#message');node.style.height='auto';node.style.height=Math.min(node.scrollHeight,144)+'px';}

function settleProposal(id,label) {
  if(!id)return;
  $$('[data-proposal-id]').filter(button=>button.dataset.proposalId===id).forEach(button=>{button.disabled=true;button.textContent=label;});
}
function attachProposal(content,action) {
  if(state.pendingAction?.proposal_id && state.pendingAction.proposal_id!==action.proposal_id)settleProposal(state.pendingAction.proposal_id,'Replaced');
  state.pendingAction=structuredClone(action);
  const button=el('button','primary-button message-action','Review action');
  if(action.proposal_id)button.dataset.proposalId=action.proposal_id;
  button.addEventListener('click',async()=>{if(await reviewAction(action)){button.disabled=true;button.textContent='Completed';}});
  content.append(button);
}
function noteLink(result) {
  if(!/^[a-f0-9]{32}$/.test(result.note_id || ''))return null;
  const link=el('a','quiet-button message-action','Read saved note');link.href='/api/notes/'+result.note_id;link.target='_blank';link.rel='noopener';return link;
}
function showToolResult(result,failed=false) {
  const text=typeof result.result==='string'?result.result:result.result?.result || result.error || (failed?'Action did not complete.':'Action completed.');
  const content=addMessage(text,'sara',failed?'tool-error':'tool-result');
  appendStepResults(content,result);
  const link=noteLink(result);if(link)content.append(link);
  return text;
}
function appendStepResults(content,result) {
  if(!Array.isArray(result?.step_results) || !result.step_results.length)return;
  const details=el('details','routine-outcomes'),summary=el('summary','','Routine step results'),list=el('ol');
  for(const row of result.step_results.slice(0,8)){
    const text=typeof row.result?.result==='string'?row.result.result:row.result?.error || 'No verified result was returned.';
    list.append(el('li','',humanize(row.action?.type || 'step')+' · '+humanize(row.status)+' — '+text));
  }
  details.append(summary,list);
  const unrun=Number(result.total_steps)-result.step_results.length;
  if(unrun>0)details.append(el('p','',unrun+' later '+(unrun===1?'step was':'steps were')+' not requested.'));
  content.append(details);
}

function reviewAction(action) {
  if(state.dialog) {toast('Finish reviewing the current action first.');return Promise.resolve(false);}
  if(state.stopped) {toast('Actions are paused. Resume them from the top bar first.');return Promise.resolve(false);}
  let details;
  try {details=actionDetails(action);} catch(error) {toast(error.message);return Promise.resolve(false);}
  stopSpeech();pauseRecognition();setCharacter('review');
  $('#confirmation-title').textContent=humanize(action.type);
  $('#confirmation-description').textContent=action.label_text || action.label || 'Review the details below before SARA makes this change.';
  $('#confirmation-details').replaceChildren();
  for(const [key,value] of details) $('#confirmation-details').append(el('dt','',key),el('dd','',value));
  if(action.type==='create_reminder' && !action.reminder?.due_at) {
    $('#confirmation-details').append(el('dt','','Notification'),el('dd','','No time was understood. This reminder will be saved without an automatic notification. Cancel and include a time if you want an alert.'));
  }
  $('#confirmation-error').hidden=true;$('#approve-action').disabled=false;$('#approve-action').textContent='Approve action';
  return new Promise(resolve=>{state.dialog={action:structuredClone(action),resolve,executing:false};$('#confirmation').showModal();});
}
function closeReview(success=false) {
  if(!state.dialog || state.dialog.executing) return;
  const {resolve}=state.dialog;state.dialog=null;$('#confirmation').close();setCharacter('ready');scheduleWake();resolve(success);
}
$('#approve-action').addEventListener('click',async()=>{
  const pending=state.dialog;
  if(!pending || pending.executing) return;
  pending.executing=true;$('#approve-action').disabled=true;$('#approve-action').textContent='Working…';
  $('#cancel-action').disabled=true;$('#close-confirmation').disabled=true;
  try {
    const {path,body}=actionRequest(pending.action);
    const result=await api(path,body,65000);
    if(result.ok===false || result.requires_confirmation){const error=new Error(result.result || result.error || 'Action did not complete.');error.details=result;throw error;}
    if(['save_pronunciation','delete_pronunciation'].includes(pending.action.type))speechCache.clear();
    const resultText=showToolResult(result);
    settleProposal(pending.action.proposal_id,'Completed');state.pendingAction=null;
    toast(resultText);pending.executing=false;closeReview(true);await refreshData();
  } catch(error) {
    showToolResult(error.details || {result:error.message},true);
    settleProposal(pending.action.proposal_id,'Request ended');state.pendingAction=null;
    pending.executing=false;closeReview(false);toast(error.message);
    // The real failure/partial result remains in chat. Do not silently retry.
  } finally {$('#cancel-action').disabled=false;$('#close-confirmation').disabled=false;}
});
function cancelReview() {
  if(!state.dialog || state.dialog.executing)return;
  const action=state.dialog.action;closeReview();
  if(action.proposal_id){settleProposal(action.proposal_id,'Cancelled');state.pendingAction=null;void api('/api/actions/cancel',{proposal_id:action.proposal_id}).catch(error=>toast(error.message));}
}
$('#cancel-action').addEventListener('click',cancelReview);
$('#close-confirmation').addEventListener('click',cancelReview);
$('#confirmation').addEventListener('cancel',event=>{event.preventDefault();cancelReview();});

function renderAgenda() {
  const {tasks,events,reminders}=state.agenda;
  $('#task-count').textContent=tasks.length;$('#event-count').textContent=events.length;$('#reminder-count').textContent=reminders.length;
  $('#nav-count').textContent=tasks.length;
  const preview=$('#agenda-preview');preview.replaceChildren();
  const timed=[...events.map(item=>({type:'event',text:item.title,time:item.start_at})),...reminders.map(item=>({type:'reminder',text:item.text,time:item.due_at}))].sort((a,b)=>(Date.parse(a.time)||Infinity)-(Date.parse(b.time)||Infinity));
  const rows=[...timed,...tasks.map(item=>({type:'task',text:item.text}))];
  if(!rows.length) empty(preview,'A little breathing room.','Nothing planned yet. Add one small task to get started.');
  rows.slice(0,3).forEach(item=>{
    const row=el('div','agenda-row'),copy=el('div');copy.append(el('strong','',item.text),el('small','',item.time?dateText(item.time):'Pending task'));
    row.append(el('span','agenda-dot '+item.type),copy);preview.append(row);
  });
  const renderList=(target,items,kind)=>{
    target.replaceChildren();
    if(!items.length) {empty(target,'No '+kind+' yet.',kind==='tasks'?'Small steps count. Add your first task above.':'Add one when you have something planned.');return;}
    for(const item of items) {
      const row=el('div','item-row'),copy=el('div','item-copy'),text=item.text||item.title;
      copy.append(el('strong','',text),el('small','',kind==='tasks'?`${item.priority||'medium'} priority · ${item.category||'general'}${item.due_at?' · Due '+dateText(item.due_at):''}`:dateText(item.start_at||item.due_at,'No notification time')));
      if(kind==='tasks') row.append(actionButton('check','Complete task',{type:'complete_task',id:item.id,text,label:'Mark this task complete: '+text},'complete-button'));
      row.append(copy);
      row.append(actionButton('trash','Delete '+(kind==='tasks'?'task':kind==='events'?'event':'reminder'),
        {type:kind==='tasks'?'delete_task':kind==='events'?'delete_event':'delete_reminder',id:item.id,text,label:'Remove: '+text}));
      target.append(row);
    }
  };
  renderList($('#task-list'),tasks,'tasks');renderList($('#event-list'),events,'events');renderList($('#reminder-list'),reminders,'reminders');
}
function actionButton(symbol,label,action,extra='') {
  const button=el('button','icon-button '+extra);button.type='button';button.title=label;button.setAttribute('aria-label',label);
  button.append(icon(symbol));button.addEventListener('click',()=>reviewAction(action));return button;
}
function renderMemories() {
  const preview=$('#memory-preview');preview.replaceChildren();
  const approved=state.memories.filter(item=>item?.approved===true && typeof item.text==='string' && item.text.trim());
  $('#hud-memory-count').textContent=approved.length+' approved '+(approved.length===1?'memory':'memories');
  if(!approved.length) empty(preview,'Getting to know your preferences.','Tell SARA what helps you. Only the memories you approve are used in replies.');
  approved.slice(-2).forEach(item=>preview.append(el('p','memory-preview-row',item.text)));
  const query=$('#memory-search').value.toLowerCase(),list=$('#memory-list');list.replaceChildren();
  const filtered=state.memories.filter(item=>String(item.text).toLowerCase().includes(query));
  if(!filtered.length) empty(list,query?'No matching memories.':'A fresh start.','Add a preference above, or ask SARA to remember something in chat.');
  filtered.forEach(item=>{
    const card=el('article','panel memory-card'),copy=el('div'),symbol=icon('memory');symbol.classList.add('accent-icon');
    const approvalLabel=item.approved===true?'Approved by you · ':'Not approved · SARA does not use this · ';
    copy.append(el('p','',item.text),el('small','',approvalLabel+dateText(item.updated||item.created,'Saved locally')));
    const controls=el('div','memory-actions'),edit=el('button','quiet-button','Edit');edit.type='button';
    edit.addEventListener('click',()=>{
      if(copy.querySelector('.memory-edit-form'))return;
      const form=el('div','memory-edit-form'),editor=document.createElement('textarea');
      editor.value=item.text;editor.maxLength=500;editor.setAttribute('aria-label','Edit approved memory');
      editor.style.cssText='width:100%;min-height:76px;padding:10px;border:1px solid #ffffff20;border-radius:8px;background:#11151f;color:inherit;resize:vertical';
      const save=el('button','primary-button','Review update');save.type='button';
      const cancel=el('button','quiet-button','Cancel');cancel.type='button';
      const buttons=el('div','memory-edit-actions');buttons.append(save,cancel);form.append(editor,buttons);copy.append(form);editor.focus();
      cancel.addEventListener('click',()=>form.remove());
      save.addEventListener('click',async()=>{
        const text=editor.value.trim();
        if(!text){toast('Memory cannot be empty.');return;}
        if(text===item.text){form.remove();return;}
        const approved=await reviewAction({type:'update_memory',id:item.id,old_text:item.text,text,label_text:'Review the current and replacement memory before saving.'});
        if(approved)form.remove();
      });
    });
    if(item.approved!==true)controls.append(actionButton('check','Approve memory',{type:'approve_memory',id:item.id,text:item.text,label_text:'Approve this exact saved memory for future replies.'}));
    controls.append(edit,actionButton('trash','Delete memory',{type:'delete_memory',id:item.id,text:item.text,label:'Forget this approved memory'}));
    card.append(symbol,copy,controls);list.append(card);
  });
}
function ensurePronunciationSettings() {
  const grid=$('#view-settings .settings-grid');if(!grid || $('#pronunciation-settings'))return;
  const section=el('section','panel settings-card');section.id='pronunciation-settings';
  section.append(el('h2','','Pronunciation guide'),el('p','card-note','Teach SARA how to say names or Hindi words. This changes spoken audio only; your chat text stays the same. Devanagari is usually best for Hindi, e.g. Kalpana → कल्पना.'));
  const form=document.createElement('form');form.id='pronunciation-form';form.className='pronunciation-form';
  const wordLabel=el('label','','Word or phrase');wordLabel.htmlFor='pronunciation-word';
  const word=el('input');word.id='pronunciation-word';word.maxLength=80;word.required=true;word.placeholder='e.g. Kalpana';
  const sayLabel=el('label','','Speak it as');sayLabel.htmlFor='pronunciation-say-as';
  const sayAs=el('input');sayAs.id='pronunciation-say-as';sayAs.maxLength=160;sayAs.required=true;sayAs.placeholder='e.g. कल्पना';
  const button=el('button','primary-button','Save pronunciation');button.type='submit';
  form.append(wordLabel,word,sayLabel,sayAs,button);form.addEventListener('submit',async event=>{
    event.preventDefault();const source=word.value.trim(),spoken=sayAs.value.trim();if(!source||!spoken)return;
    if(await reviewAction({type:'save_pronunciation',word:source,say_as:spoken,label:'Save this local pronunciation for spoken replies'})){form.reset();await refreshData();}
  });
  const pronunciationList=el('div','item-list pronunciation-list');pronunciationList.id='pronunciation-list';section.append(form,pronunciationList);
  grid.prepend(section);
}
function renderPronunciations() {
  const list=$('#pronunciation-list');if(!list)return;list.replaceChildren();
  if(!state.pronunciations.length){empty(list,'No custom pronunciations yet.','Add a word above when SARA says it incorrectly.');return;}
  state.pronunciations.forEach(item=>{
    const row=el('div','item-row'),copy=el('div','item-copy');
    copy.append(el('strong','',item.word),el('small','','Say as: '+item.say_as));
    row.append(copy,actionButton('trash','Remove pronunciation',{type:'delete_pronunciation',id:item.id,text:item.word,label:'Remove this local pronunciation preference'}));list.append(row);
  });
}
function ensureAppSettings() {
  const grid=$('#view-settings .settings-grid');if(!grid || $('#app-settings'))return;
  const section=el('section','panel settings-card');section.id='app-settings';
  section.append(el('h2','','App shortcuts'),el('p','card-note','Register a Windows .exe by its full path. SARA will ask before every launch. Command arguments are not supported.'));
  const form=document.createElement('form');form.id='custom-app-form';form.className='pronunciation-form';
  const nameLabel=el('label','','Shortcut name');nameLabel.htmlFor='custom-app-name';
  const name=el('input');name.id='custom-app-name';name.maxLength=60;name.required=true;name.placeholder='e.g. VS Code';
  const pathLabel=el('label','','Full .exe path');pathLabel.htmlFor='custom-app-executable';
  const executable=el('input');executable.id='custom-app-executable';executable.maxLength=500;executable.required=true;executable.placeholder='C:\\Program Files\\App\\app.exe';
  const button=el('button','primary-button','Add shortcut');button.type='submit';
  form.append(nameLabel,name,pathLabel,executable,button);form.addEventListener('submit',async event=>{
    event.preventDefault();const appName=name.value.trim(),appPath=executable.value.trim();if(!appName||!appPath)return;
    if(await reviewAction({type:'add_custom_app',name:appName,executable:appPath,label:`Register ${appName} at this executable path`})){form.reset();await refreshData();}
  });
  const builtins=el('p','card-note');builtins.id='built-in-apps';
  const list=el('div','item-list pronunciation-list');list.id='custom-app-list';section.append(form,builtins,list);grid.prepend(section);
}
function renderApps() {
  const list=$('#custom-app-list');if(!list)return;
  $('#built-in-apps').textContent='Built-in: '+(state.apps.built_in||[]).join(', ');
  list.replaceChildren();const items=state.apps.custom||[];
  if(!items.length){empty(list,'No custom shortcuts yet.','Add an .exe path above to make one available by name in chat.');return;}
  items.forEach(item=>{
    const row=el('div','item-row'),copy=el('div','item-copy');
    copy.append(el('strong','',item.name),el('small','',item.executable));
    row.append(copy,actionButton('trash','Remove app shortcut',{type:'delete_custom_app',id:item.id,text:item.name,label:'Remove this local app shortcut'}));list.append(row);
  });
}
function ensureCapabilityRequestSettings() {
  const grid=$('#view-settings .settings-grid');if(!grid || $('#capability-request-settings'))return;
  const section=el('section','panel settings-card');section.id='capability-request-settings';
  section.append(el('h2','','Feature requests'),el('p','card-note','When SARA cannot do something yet, approve saving it here. Requests are local notes for future development; saving one does not install or enable a feature.'));
  const list=el('div','item-list pronunciation-list');list.id='capability-request-list';section.append(list);grid.prepend(section);
}
function renderCapabilityRequests() {
  const list=$('#capability-request-list');if(!list)return;list.replaceChildren();
  if(!state.capabilityRequests.length){empty(list,'No saved feature requests.','SARA can offer to keep track of a missing capability when you ask.');return;}
  state.capabilityRequests.slice().reverse().forEach(item=>{
    const row=el('div','item-row'),copy=el('div','item-copy');
    copy.append(el('strong','',item.title),el('small','',item.description+' · '+(item.status||'requested')+(item.current_status?' · capability '+item.current_status:'')));
    if(item.required_access)copy.append(el('small','','Required access: '+item.required_access));
    if(Array.isArray(item.implementation_plan)&&item.implementation_plan.length){
      const details=el('details','capability-plan'),summary=el('summary','','Implementation plan'),steps=document.createElement('ol');
      item.implementation_plan.forEach(step=>steps.append(el('li','',step)));details.append(summary,steps);copy.append(details);
    }
    row.append(copy,actionButton('trash','Remove feature request',{type:'delete_capability_request',id:item.id,text:item.title,label:'Remove this saved feature request'}));list.append(row);
  });
}
function renderPolicy(policy) {
  state.stopped=!!policy.stopped;
  $('#pause-actions span').textContent=state.stopped?'Resume actions':'Pause actions';
  $('#pause-actions').setAttribute('aria-pressed',String(state.stopped));
  $('#pause-actions').style.color=state.stopped?'var(--peach)':'';
  $('#policy-status').textContent=state.stopped?'New actions are paused. Conversation is still available.':policy.access_mode==='trusted'?'Trusted routines are enabled. Supported media, browsing, built-in apps and saved routines can run directly; other changes need review.':'Review mode is enabled. Actions need your approval.';
  const list=$('#policy-list');list.replaceChildren();
  Object.entries(policy.actions||{}).forEach(([name,info])=>{const row=el('div','policy-row'),scoped=['media_control','run_routine','open_app','open_browser_url','browser_open','youtube_play'].includes(name)&&policy.access_mode==='trusted';row.append(el('span','',humanize(name)),el('span','badge '+info.risk,info.risk+(scoped?' · trusted scope':' · review')));list.append(row);});
}
function renderCapabilities(capabilities) {
  const list=$('#capabilities');list.replaceChildren();
  Object.entries(capabilities).forEach(([name,info])=>{
    const row=el('div','capability-row'),copy=el('div','',humanize(name));
    if(info.scope)copy.append(el('small','',info.scope));
    row.append(copy,el('span','badge '+info.status,info.status));list.append(row);
  });
}
function renderActivity(items) {
  const list=$('#activity-list');list.replaceChildren();
  if(!items.length) {const row=el('div','activity-row');empty(row,'Your story starts here.','Conversations and actions will appear as you use SARA.');list.append(row);}
  items.forEach(item=>{
    const row=el('article','activity-row'),copy=el('div');
    row.append(icon(item.event==='conversation'?'chat':'activity'));
    copy.append(el('strong','',item.event==='conversation'?'You & SARA':humanize(item.event||'Activity')));
    if(item.event==='conversation') copy.append(el('p','','You: '+(item.question||'')),el('p','','SARA: '+(item.answer||'')));
    else if(item.error || item.path || item.title) copy.append(el('p','',item.error||item.path||item.title));
    copy.append(el('small','',dateText(item.time)));row.append(copy);list.append(row);
  });
}
async function refreshSuggestions() {
  const list=$('#suggestions');list.replaceChildren();
  if(!state.proactive) return;
  try {(await api('/api/suggestions')).suggestions.forEach(item=>list.append(el('p','suggestion',item.text)));}
  catch {list.append(el('p','card-note','Suggestions could not be loaded.'));}
}
async function refreshData(initial=false) {
  if(state.refreshing) return;
  state.refreshing=true;
  const requests=[
    ['/api/agenda',data=>{state.agenda=data;renderAgenda();}],
    ['/api/memories',data=>{state.memories=data;renderMemories();}],
    ['/api/policy',renderPolicy]
  ];
  if(initial || state.view==='settings'){
    requests.push(['/api/pronunciations',data=>{state.pronunciations=data;renderPronunciations();}]);
    requests.push(['/api/apps',data=>{state.apps=data;renderApps();}]);
    requests.push(['/api/capability-requests',data=>{state.capabilityRequests=data;renderCapabilityRequests();}]);
  }
  if(initial || state.view==='activity')requests.push(['/api/activity',renderActivity]);
  if(initial || (state.view==='settings' && Date.now()-state.capabilitiesChecked>60000))requests.push(['/api/capabilities',data=>{renderCapabilities(data);state.capabilitiesChecked=Date.now();}]);
  if(initial || Date.now()-state.healthChecked>30000)requests.push(['/api/health',data=>{
      state.healthChecked=Date.now();
      state.naturalVoiceAvailable=Boolean(data.natural_voice);updateVoiceModeAvailability();
      const node=$('#connection'),modelReady=Boolean(data.model_available);
      const label=data.ollama?(modelReady?'Local AI connected':'Ollama model missing'):'Local tools ready';
      $('#hud-model').textContent=data.ollama?(modelReady?data.model+' · local':'Model not installed'):'Local tools · AI offline';
      node.replaceChildren(el('i'),document.createTextNode(label));
      node.classList.toggle('offline',!data.ollama || !modelReady);
      node.title=data.ollama?(modelReady?'Ollama and model are ready: '+data.model:'Ollama is running, but '+data.model+' is not installed. Run `ollama run '+data.model+'` once.'):'Ollama is not reachable. Chat may use configured cloud AI or the local fallback.';
    }]);
  const outcomes=await Promise.allSettled(requests.map(async([path,render])=>render(await api(path))));
  const failures=outcomes.filter(item=>item.status==='rejected');
  $('#error-banner').hidden=!failures.length;
  if(failures.length) {
    $('#error-banner span').textContent='Some workspace data could not load. '+failures[0].reason.message;
    if(failures.length===requests.length) {$('#connection').replaceChildren(el('i'),document.createTextNode('Server unavailable'));$('#connection').classList.add('offline');$('#hud-model').textContent='Server unavailable';}
  }
  state.refreshing=false;
  await refreshSuggestions();
}

function stopSpeech() {
  clearInterval(speechWatchdog);speechWatchdog=null;
  state.speechSequence++;state.speaking=false;
  state.speechStarted=false;
  state.utterances=[];
  state.audioController?.abort();state.audioController=null;
  if(state.audio){state.audio.pause();state.audio.removeAttribute('src');state.audio.load();state.audio=null;}
  if(state.audioUrl){URL.revokeObjectURL(state.audioUrl);state.audioUrl=null;}
  window.speechSynthesis?.cancel();$('#stop-speech').hidden=true;
  if(!state.busy)setCharacter(state.recognizing?'listening':'ready');
}
function finishSpeech(sequence, failed=false) {
  if(sequence!==state.speechSequence)return;
  state.speechSequence++;
  clearInterval(speechWatchdog);speechWatchdog=null;
  state.speaking=false;state.audio=null;state.audioController=null;
  state.speechStarted=false;
  state.utterances=[];
  if(state.audioUrl){URL.revokeObjectURL(state.audioUrl);state.audioUrl=null;}
  $('#stop-speech').hidden=true;
  openFollowUpWindow();
  $('#voice-status').textContent=failed?'Voice failed · try another voice':listeningStatus();
  setCharacter(state.busy?'thinking':'ready');scheduleWake();
  if(failed)showVoiceRetry(state.lastVoicePlayback || 'Voice did not start. Click Retry voice; check your speaker output if it stays silent.');
}
function watchSystemSpeech(sequence) {
  clearInterval(speechWatchdog);const started=Date.now();let idleSince=0;
  speechWatchdog=setInterval(()=>{
    if(sequence!==state.speechSequence || !state.speaking){clearInterval(speechWatchdog);speechWatchdog=null;return;}
    const synth=window.speechSynthesis;
    if(!state.speechStarted && Date.now()-started>=15000){
      state.lastVoicePlayback='System voice did not start within 15 seconds.';
      $('#voice-diagnostics').textContent=state.lastVoicePlayback;
      stopSpeech();finishSpeech(state.speechSequence,true);return;
    }
    if(synth.paused && !document.hidden){synth.resume();return;}
    if(synth.speaking || synth.pending){idleSince=0;return;}
    if(!idleSince)idleSince=Date.now();
    // Some system engines finish without an end event. Trust the engine's idle
    // flags rather than a text-length timer that could cut off valid speech.
    if(Date.now()-idleSince>=1200 && (state.speechStarted || Date.now()-started>=5000)){
      const failed=!state.speechStarted;
      if(failed){stopSpeech();finishSpeech(state.speechSequence,true);}
      else finishSpeech(sequence);
    }
  },500);
}
function voiceScore(voice, hindi=false) {
  const name=voice.name.toLowerCase(),lang=voice.lang.toLowerCase();let score=0;
  if(/kalpana|heera|swara|neerja|zira|aria|jenny|sonia|susan|hazel|samantha|natasha|kavya|meera|priya|shreya|\bfemale\b/.test(name))score+=45;
  if(/david|mark|ravi|hemant|george|richard|\bmale\b/.test(name))score-=60;
  if(/natural|neural|online|enhanced/.test(name))score+=22;
  if(hindi)score+=lang.startsWith('hi')?32:lang==='en-in'?8:0;
  else score+=lang==='en-in'?28:lang.startsWith('en')?14:0;
  return score;
}
function preferredVoice(voices,hindi=false) {
  const chosen=voices.find(voice=>voice.voiceURI===$('#voice-select').value);
  if(chosen && chosen.lang.toLowerCase().startsWith(hindi?'hi':'en'))return chosen;
  const candidates=hindi?voices.filter(voice=>voice.lang.toLowerCase().startsWith('hi')):voices.filter(voice=>voice.lang.toLowerCase().startsWith('en'));
  return [...candidates].sort((a,b)=>voiceScore(b,hindi)-voiceScore(a,hindi))[0] || null;
}
function systemVoices() {
  const browser=window.speechSynthesis?.getVoices() || [];
  return [...browser,...state.windowsVoices.map(voice=>({...voice,voiceURI:'windows:'+voice.id,localWindows:true}))];
}
function reportSystemPlayback(utterances,rate,label='system reply') {
  const routes=[...new Set(utterances.map(item=>`${item.lang || 'default'}: ${item.voice?.name || 'browser default'}`))];
  const noHindiVoice=utterances.some(item=>item.lang?.toLowerCase().startsWith('hi')&&!item.voice);
  state.lastVoicePlayback=`Queued ${label} · ${Number(rate).toFixed(2)}× · ${routes.join(' · ') || 'no speech passages'}${noHindiVoice?' · no explicit Hindi voice was available; browser fallback is in use.':''}`;
  $('#voice-diagnostics').textContent=state.lastVoicePlayback;
}
function saveVoiceSelection(voice) {
  prefs.set('sara-voice-uri',voice?.voiceURI || '');
  prefs.set('sara-voice-name',voice?.name || '');
  prefs.set('sara-voice-lang',voice?.lang || '');
}
function waitForSystemVoices(timeout=1400) {
  const synth=window.speechSynthesis;
  if(!synth?.getVoices)return Promise.resolve([]);
  const read=()=>{try{return synth.getVoices() || [];}catch{return [];}};
  const ready=read();if(ready.length){voiceListWaitCompleted=false;return Promise.resolve(ready);}
  if(voiceListWaitCompleted)return Promise.resolve(ready);
  return new Promise(resolve=>{
    let timer=null,poll=null,settled=false;
    const finish=()=>{
      if(settled)return;settled=true;clearTimeout(timer);clearInterval(poll);
      synth.removeEventListener?.('voiceschanged',finish);
      const voices=read();voiceListWaitCompleted=!voices.length;resolve(voices);
    };
    synth.addEventListener?.('voiceschanged',finish);
    poll=setInterval(()=>{if(read().length)finish();},100);
    timer=setTimeout(finish,timeout);
  });
}
async function speakNatural(text,sequence) {
  const controller=new AbortController();state.audioController=controller;
  const timer=setTimeout(()=>controller.abort(),45000);
  try {
    const response=await fetch('/api/tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,speed:Number($('#voice-rate').value)}),signal:controller.signal});
    if(!response.ok){const error=await response.json().catch(()=>({}));throw new Error(error.error || 'Natural voice is temporarily unavailable.');}
    const blob=await response.blob();
    if(sequence!==state.speechSequence)return true;
    state.audioUrl=URL.createObjectURL(blob);
    const audio=new Audio(state.audioUrl);state.audio=audio;
    audio.onplaying=()=>{if(sequence===state.speechSequence){state.speechStarted=true;$('#voice-status').textContent='SARA speaking · natural AI voice';state.lastVoicePlayback=`Last natural reply · ${Number($('#voice-rate').value).toFixed(2)}× · ${text.length} characters · OpenAI TTS`;$('#voice-diagnostics').textContent=state.lastVoicePlayback;setCharacter('speaking');}};
    audio.onended=()=>finishSpeech(sequence);
    audio.onerror=()=>{if(sequence===state.speechSequence && state.speechStarted){toast('Natural voice playback failed. Try a system voice.');finishSpeech(sequence,true);}};
    await audio.play();
    return true;
  } catch(error) {
    if(sequence!==state.speechSequence)return true;
    if(state.audio){state.audio.onended=null;state.audio.onerror=null;state.audio.onplaying=null;state.audio.pause();state.audio.removeAttribute('src');state.audio=null;}
    if(state.audioUrl){URL.revokeObjectURL(state.audioUrl);state.audioUrl=null;}
    toast('Natural voice unavailable; using the system voice.');
    return false;
  } finally {
    clearTimeout(timer);
    if(state.audioController===controller)state.audioController=null;
  }
}
async function speakWindows(text,sequence) {
  const hindi=/[\u0900-\u097f]/.test(text), selected=preferredVoice(systemVoices(),hindi);
  const local=state.windowsVoices.find(voice=>selected?.name?.startsWith(voice.name));
  if(!local)return false;
  const controller=new AbortController();state.audioController=controller;
  const timer=setTimeout(()=>controller.abort(),40000);
  try {
    const response=await fetch('/api/tts/windows',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text,voice:local.id,lang:hindi?'hi-IN':local.lang,speed:Number($('#voice-rate').value)}),signal:controller.signal});
    if(!response.ok){const error=await response.json().catch(()=>({}));throw new Error(error.error || 'Windows voice could not generate audio.');}
    const blob=await response.blob();if(sequence!==state.speechSequence)return true;
    state.audioUrl=URL.createObjectURL(blob);const audio=new Audio(state.audioUrl);state.audio=audio;
    audio.onplaying=()=>{if(sequence!==state.speechSequence)return;state.speechStarted=true;state.lastVoicePlayback='Windows local · '+local.name+' · '+Number($('#voice-rate').value).toFixed(2)+'×';$('#voice-diagnostics').textContent=state.lastVoicePlayback;$('#voice-status').textContent='Speaking · '+local.name;setCharacter('speaking');};
    audio.onended=()=>finishSpeech(sequence);
    audio.onerror=()=>{if(sequence===state.speechSequence){state.lastVoicePlayback='Windows audio playback failed. Check speaker output, then retry.';finishSpeech(sequence,true);}};
    await audio.play();return true;
  } catch(error) {
    if(sequence!==state.speechSequence)return true;
    if(state.audio){state.audio.onended=null;state.audio.onerror=null;state.audio.onplaying=null;state.audio.pause();state.audio.removeAttribute('src');state.audio=null;}
    if(state.audioUrl){URL.revokeObjectURL(state.audioUrl);state.audioUrl=null;}
    state.lastVoicePlayback=error.name==='NotAllowedError'?'Voice playback needs a click. Use Enable voice / Retry.':error.message;
    $('#voice-diagnostics').textContent=state.lastVoicePlayback;
    return false;
  } finally {clearTimeout(timer);if(state.audioController===controller)state.audioController=null;}
}
function showVoiceRetry(reason) {
  $('#voice-diagnostics').textContent=reason;$('#voice-status').textContent='Voice failed · '+reason;
  $('#retry-voice').hidden=false;toast(reason);
}
async function speak(text, force=false, systemOnly=false) {
  if(!state.speak && !force) return;
  stopSpeech();const sequence=state.speechSequence;
  const short=String(text).slice(0,1200);
  state.lastSpeechText=short;$('#retry-voice').hidden=true;
  state.speaking=true;pauseRecognition();
  $('#stop-speech').hidden=false;
  let prepared=speechCache.get(short);
  if(!prepared){
    try {prepared=await api('/api/speech-text',{text:short,fast:true},2500);speechCache.set(short,prepared);if(speechCache.size>12)speechCache.delete(speechCache.keys().next().value);}
    catch {prepared={text:short,segments:[{text:short,lang:/[\u0900-\u097f]/.test(short)?'hi-IN':'en-IN'}]};}
  }
  if(sequence!==state.speechSequence)return;
  if(!prepared.text?.trim()){finishSpeech(sequence);return;}
  if(!systemOnly && state.voiceMode==='natural' && state.naturalVoiceAvailable && await speakNatural(prepared.text,sequence))return;
  if(sequence!==state.speechSequence)return;
  if(await speakWindows(prepared.text,sequence))return;
  if(sequence!==state.speechSequence)return;
  if(!('speechSynthesis' in window)) {toast('Speech output is not supported in this browser.');finishSpeech(sequence,true);return;}
  const voices=(await waitForSystemVoices()).filter(voice=>!voice.localWindows);
  if(sequence!==state.speechSequence)return;
  populateVoices();
  const segments=(prepared.playback || [{text:prepared.text,lang:/[\u0900-\u097f]/.test(prepared.text)?'hi-IN':'en-IN'}]).filter(item=>item.text.trim());
  state.utterances=segments.map((segment,index)=>{
    const utterance=new SpeechSynthesisUtterance(segment.text),hindi=segment.lang==='hi-IN';
    utterance.voice=preferredVoice(voices,hindi);utterance.lang=utterance.voice?.lang || segment.lang;
    utterance.rate=Number($('#voice-rate').value);utterance.pitch=1.04;
    utterance.onstart=()=>{if(sequence===state.speechSequence){state.speechStarted=true;$('#voice-status').textContent='Speaking'+(utterance.voice?.name?' · '+utterance.voice.name:'');setCharacter('speaking');}};
    utterance.onend=()=>{if(index===segments.length-1)finishSpeech(sequence);};
    utterance.onerror=event=>{if(sequence===state.speechSequence){state.lastVoicePlayback=`System voice error (${event.error || 'unknown'}) · ${utterance.voice?.name || utterance.lang}`;stopSpeech();finishSpeech(state.speechSequence,true);showVoiceRetry(state.lastVoicePlayback+' · click Retry voice or select another installed voice.');}};
    return utterance;
  });
  reportSystemPlayback(state.utterances,$('#voice-rate').value,systemOnly?'system voice test':'system reply');
  try {window.speechSynthesis.resume();for(const utterance of state.utterances)window.speechSynthesis.speak(utterance);watchSystemSpeech(sequence);} catch {state.lastVoicePlayback='System speech failed to start.';$('#voice-diagnostics').textContent=state.lastVoicePlayback;toast('Could not start browser voice output.');stopSpeech();finishSpeech(state.speechSequence,true);}
}
function populateVoices() {
  const voices=systemVoices(),select=$('#voice-select');
  const savedUri=select.value || prefs.get('sara-voice-uri'),savedName=prefs.get('sara-voice-name'),savedLang=prefs.get('sara-voice-lang');
  select.replaceChildren(new Option('SARA picks the best available voice',''));
  [...voices].sort((a,b)=>voiceScore(b)-voiceScore(a)).forEach(voice=>select.add(new Option(voice.name+' ('+voice.lang+')'+(voice.localWindows?' · Windows local':''),voice.voiceURI)));
  const savedVoice=voices.find(voice=>voice.voiceURI===savedUri)
    || (savedName?voices.find(voice=>voice.name.toLowerCase()===savedName.toLowerCase() && (!savedLang || voice.lang.toLowerCase()===savedLang.toLowerCase())):null)
    || (savedName?voices.find(voice=>voice.name.toLowerCase()===savedName.toLowerCase()):null)
    || (!savedName && savedUri?voices.find(voice=>voice.name && savedUri.toLowerCase().includes(voice.name.toLowerCase())):null);
  select.value=savedVoice?.voiceURI || '';
  if(savedVoice)saveVoiceSelection(savedVoice);
  const recommended=preferredVoice(voices);
  const missingSavedVoice=voices.length && !savedVoice && (savedName || savedUri) ? ' · Saved voice unavailable: '+(savedName || savedUri)+'; using a fallback' : '';
  $('#voice-diagnostics').textContent=voices.length+' system voices · '+(savedVoice?'Selected '+savedVoice.name:recommended?'SARA picks '+recommended.name:'No voice detected')+' · '+(voices.some(v=>v.lang.toLowerCase().startsWith('hi'))?'Hindi voice available':'Hindi voice unavailable')+missingSavedVoice+(state.lastVoicePlayback?' · '+state.lastVoicePlayback:'');
}
function updateVoiceModeAvailability() {
  const mode=$('#voice-mode');if(!mode)return;
  mode.querySelector('[value="natural"]').disabled=!state.naturalVoiceAvailable;
  if(state.voiceMode==='natural'&&!state.naturalVoiceAvailable){state.voiceMode='system';prefs.set('sara-voice-mode','system');}
  mode.value=state.voiceMode;
  $('#voice-mode-note').textContent=state.naturalVoiceAvailable?'Natural voice sends SARA’s reply text to the OpenAI API and uses credits; the voice is AI-generated. System voice works offline.':'Natural AI voice needs OPENAI_API_KEY; SARA will use the best available system voice.';
}
function initializeVoiceModeControl() {
  const label=el('label','','SARA voice');label.htmlFor='voice-mode';
  const select=el('select');select.id='voice-mode';
  select.add(new Option('Female system voice · offline','system'));
  select.add(new Option('Natural AI voice · uses API credits','natural'));
  const note=el('p','card-note');note.id='voice-mode-note';
  $('#auto-speak').closest('label').after(label,select,note);
  if(!['system','natural'].includes(state.voiceMode))state.voiceMode='system';
  select.value=state.voiceMode;
  select.addEventListener('change',()=>{stopSpeech();state.voiceMode=select.value;prefs.set('sara-voice-mode',state.voiceMode);updateVoiceModeAvailability();openFollowUpWindow();scheduleWake();});
  updateVoiceModeAvailability();
}
function setSpeakPreference(value) {
  state.speak=value;prefs.set('sara-auto-speak',value);$('#auto-speak').checked=value;
  $('#speaker-toggle').setAttribute('aria-pressed',String(value));
  $('#speaker-toggle').title=value?'Mute spoken replies':'Enable spoken replies';
  $('#speaker-toggle').setAttribute('aria-label',$('#speaker-toggle').title);
  if(value && !state.speaking) $('#voice-status').textContent='Voice ready · replies will be spoken';
  if(!value){stopSpeech();openFollowUpWindow();scheduleWake();}
}
function openFollowUpWindow() {
  if(state.wake && state.voiceConversation){
    state.wakeUntil=Date.now()+FOLLOW_UP_MS;clearTimeout(followUpTimer);
    followUpTimer=setTimeout(()=>{if(state.wake && !state.speaking && !state.busy && !state.recognitionBlocked)$('#voice-status').textContent=state.recognizing?'Microphone on · say “Sara”':listeningStatus();},FOLLOW_UP_MS+50);
  }
}
function listeningStatus() {
  if(!state.wake)return 'Microphone off';
  return Date.now()<state.wakeUntil?'Hands-free ready · you can reply directly':'Wake mode ready · say “Sara”';
}
function canListen() {
  return Boolean(SpeechRecognition && state.historyLoaded && state.wake && state.wakeGestureReady && !state.recognitionBlocked && !state.busy && !state.speaking && !state.dialog && !document.hidden);
}
function scheduleWake(delay=250) {
  clearTimeout(recognitionTimer);recognitionTimer=null;
  if(canListen() && !state.recognizing && !state.recognitionStarting && !recognition){
    const wait=Math.max(delay,state.recognitionRetryAt-Date.now());
    recognitionTimer=setTimeout(()=>{recognitionTimer=null;if(canListen())startRecognition();},wait);
  }
}
function pauseRecognition() {
  clearTimeout(recognitionTimer);recognitionTimer=null;
  clearTimeout(recognitionStartTimer);recognitionStartTimer=null;
  const previous=recognition;recognition=null;
  state.recognizing=false;state.recognitionStarting=false;
  $('#mic-button').setAttribute('aria-pressed','false');$('#mic-button').setAttribute('aria-label','Start hands-free conversation');$('#mic-button').title='Start or retry hands-free conversation';
  // Clear ownership first: delayed events from the aborted instance cannot
  // overwrite a newer session or restart after an explicit user Stop.
  try {previous?.abort();} catch { /* Already disconnected. */ }
}
function stopMicrophone(disableWake=true) {
  if(disableWake){state.wake=false;state.voiceConversation=false;state.wakeUntil=0;clearTimeout(followUpTimer);followUpTimer=null;prefs.set('sara-wake','false');$('#wake-toggle').checked=false;}
  pauseRecognition();
  $('#voice-status').textContent=listeningStatus();if(!state.speaking && !state.busy)setCharacter('ready');
}
function setWakePreference(enabled, start=true) {
  state.wake=Boolean(enabled);prefs.set('sara-wake',state.wake);$('#wake-toggle').checked=state.wake;
  if(!state.wake){stopMicrophone(true);return;}
  if(start){state.wakeGestureReady=true;state.recognitionBlocked='';state.recognitionRetryAt=0;state.recognitionFailures=0;pauseRecognition();stopSpeech();scheduleWake(0);}
  $('#voice-status').textContent=listeningStatus();
}
function recognitionFailed(rec,error) {
  if(recognition!==rec)return;
  pauseRecognition();
  if(['not-allowed','service-not-allowed','audio-capture','language-not-supported'].includes(error)){
    state.recognitionBlocked=error;
    const message=error==='language-not-supported'?'Voice input language unsupported · choose another language in Settings':error==='audio-capture'?'Microphone unavailable · check audio device, then tap mic to retry':'Microphone permission needed · allow access, then tap mic once';
    $('#voice-status').textContent=message;toast(message);return;
  }
  // A temporary online recognizer failure must not erase hands-free intent.
  state.recognitionFailures=error==='no-speech'||error==='aborted'?0:Math.min(state.recognitionFailures+1,5);
  const delay=state.recognitionFailures?Math.min(8000,500*2**state.recognitionFailures):300;
  state.recognitionRetryAt=Date.now()+delay;
  $('#voice-status').textContent=state.recognitionFailures?'Voice connection interrupted · reconnecting automatically':listeningStatus();
  scheduleWake(delay);
}
function startRecognition() {
  if(!canListen() || state.recognizing || state.recognitionStarting || recognition)return;
  const rec=new SpeechRecognition();recognition=rec;state.recognitionStarting=true;let startedAt=Date.now();
  rec.lang=$('#recognition-language').value;rec.interimResults=false;rec.continuous=true;
  rec.onstart=()=>{
    if(recognition!==rec){try {rec.abort();} catch { /* Stale start already ended. */ }return;}
    if(!canListen()){pauseRecognition();return;}
    clearTimeout(recognitionStartTimer);recognitionStartTimer=null;startedAt=Date.now();
    state.recognitionStarting=false;state.recognizing=true;
    $('#mic-button').setAttribute('aria-pressed','true');$('#mic-button').setAttribute('aria-label','Stop hands-free listening');$('#mic-button').title='Stop hands-free listening';
    $('#voice-status').textContent=Date.now()<state.wakeUntil?'Microphone on · you can reply directly':'Microphone on · say “Sara”';setCharacter('listening');
  };
  rec.onresult=event=>{
    if(recognition!==rec || !canListen())return;
    for(let i=event.resultIndex;i<event.results.length;i++) {
      if(!event.results[i].isFinal)continue;
      const transcript=event.results[i][0].transcript.trim();
      const hasWake=/(?:\bsara\b|सारा)/i.test(transcript);
      if(!hasWake && Date.now()>state.wakeUntil)continue;
      state.recognitionFailures=0;state.voiceConversation=true;openFollowUpWindow();
      const cleaned=transcript.replace(/^\s*(?:(?:hey|okay|ok|hello)\s+)?(?:sara|सारा)[\s,.:;-]*/i,'').trim();
      if(cleaned){submitMessage(cleaned);break;}
      $('#voice-status').textContent='Listening · what would you like to do?';
    }
  };
  rec.onerror=event=>recognitionFailed(rec,event.error);
  rec.onend=()=>{
    if(recognition!==rec)return;
    clearTimeout(recognitionStartTimer);recognitionStartTimer=null;
    recognition=null;state.recognizing=false;state.recognitionStarting=false;
    $('#mic-button').setAttribute('aria-pressed','false');$('#mic-button').setAttribute('aria-label','Start hands-free conversation');$('#mic-button').title='Start or retry hands-free conversation';
    if(!state.speaking && !state.busy){$('#voice-status').textContent=listeningStatus();setCharacter('ready');}
    if(Date.now()-startedAt<1000){state.recognitionFailures=Math.min(state.recognitionFailures+1,5);state.recognitionRetryAt=Date.now()+Math.min(8000,500*2**state.recognitionFailures);}
    else {state.recognitionFailures=0;state.recognitionRetryAt=0;}
    scheduleWake();
  };
  recognitionStartTimer=setTimeout(()=>recognitionFailed(rec,'start-timeout'),5000);
  try {rec.start();} catch(error) {
    recognitionFailed(rec,['NotAllowedError','SecurityError'].includes(error.name)?'not-allowed':'start-retry');
  }
}
async function togglePause(forceStop=false) {
  const button=$('#pause-actions');button.disabled=true;
  try {
    const stopped=forceStop || !state.stopped;
    await api(stopped?'/api/policy/stop':'/api/policy/resume',{});
    if(stopped){pauseRecognition();stopSpeech();closeReview();scheduleWake();}
    renderPolicy(await api('/api/policy'));toast(stopped?'New actions paused. You can still talk to SARA.':'Actions resumed under your selected access mode.');
  } catch(error){toast(error.message);} finally{button.disabled=false;}
}

document.addEventListener('click',event=>{
  const view=event.target.closest('button[data-view], a[data-view]');if(view){setView(view.dataset.view);return;}
  const prompt=event.target.closest('[data-prompt]');if(prompt){submitMessage(prompt.dataset.prompt);return;}
  const compose=event.target.closest('[data-compose]');if(compose){setView('chat');$('#message').value=compose.dataset.compose;resizeComposer();$('#message').focus();}
});
window.addEventListener('hashchange',()=>setView(location.hash.slice(1),false));
$('#start-conversation').addEventListener('click',()=>{
  cancelCheckIn();
  setView('chat');$('#message').focus();setSpeakPreference(true);
  state.lastInteraction=Date.now();state.voiceConversation=true;setWakePreference(true);openFollowUpWindow();
  void conversationCheckIn(true);
});
$('#chat-form').addEventListener('submit',event=>{event.preventDefault();submitMessage($('#message').value);});
$('#message').addEventListener('input',resizeComposer);
$('#message').addEventListener('keydown',event=>{if(event.key==='Enter' && !event.shiftKey && !event.isComposing){event.preventDefault();$('#chat-form').requestSubmit();}});
const taskOptions=el('div','productivity-row');taskOptions.innerHTML='<label>Priority <select id="task-priority"><option>medium</option><option>high</option><option>low</option></select></label><label>Category <select id="task-category"><option>general</option><option>work</option><option>study</option><option>shopping</option><option>personal</option></select></label><label>Due (optional) <input id="task-due" type="datetime-local"></label>';
$('#task-form').append(taskOptions);
$('#task-form').addEventListener('submit',async event=>{event.preventDefault();const text=$('#task-text').value.trim(),due=$('#task-due').value;if(due&&Number.isNaN(new Date(due).getTime()))return toast('Choose a valid due date.');if(text && await reviewAction({type:'create_task',text,priority:$('#task-priority').value,category:$('#task-category').value,...(due?{due_at:new Date(due).toISOString()}:{}),label:'Add this task to your local planner'}))$('#task-text').value='';});
$('#memory-form').addEventListener('submit',async event=>{event.preventDefault();const text=$('#memory-text').value.trim();if(text && await reviewAction({type:'save_memory',text,label:'Remember this approved preference for future conversations'}))$('#memory-text').value='';});
$('#memory-search').addEventListener('input',renderMemories);
$('#pause-actions').addEventListener('click',()=>togglePause());
$('#retry-refresh').addEventListener('click',()=>refreshData());
$('#speaker-toggle').addEventListener('click',()=>setSpeakPreference(!state.speak));
$('#auto-speak').addEventListener('change',event=>setSpeakPreference(event.target.checked));
$('#stop-speech').addEventListener('click',()=>{stopSpeech();openFollowUpWindow();scheduleWake();});
const testVoiceButton=$('#test-voice');
testVoiceButton.textContent='Test system voice';
testVoiceButton.addEventListener('click',()=>speak('नमस्ते, मैं सारा हूँ। आपकी आवाज़ और बोलने की गति कैसी लग रही है? This is a short English voice check.',true,true));
$('#voice-select').addEventListener('change',event=>{const voice=systemVoices().find(item=>item.voiceURI===event.target.value);saveVoiceSelection(voice||null);});
$('#voice-rate').addEventListener('input',event=>{$('#rate-value').textContent=Number(event.target.value).toFixed(2)+'×';prefs.set('sara-voice-rate',event.target.value);});
$('#recognition-language').addEventListener('change',event=>{prefs.set('sara-recognition-language',event.target.value);pauseRecognition();if(state.recognitionBlocked==='language-not-supported')state.recognitionBlocked='';state.recognitionRetryAt=0;scheduleWake();});
$('#mic-button').addEventListener('click',()=>{
  if(state.recognizing || state.recognitionStarting){stopMicrophone(true);return;}
  state.voiceConversation=true;setWakePreference(true);openFollowUpWindow();
});
$('#wake-toggle').addEventListener('change',event=>setWakePreference(event.target.checked));
$('#proactive-toggle').addEventListener('change',event=>{state.proactive=event.target.checked;prefs.set('sara-proactive',state.proactive);if(!state.proactive)cancelCheckIn();refreshSuggestions();});
$('#proactive-vision').addEventListener('change',()=>{if(!$('#proactive-vision').checked && state.checkInVisual)cancelCheckIn();});
document.addEventListener('keydown',event=>{if(event.ctrlKey && event.altKey && event.key==='.'){event.preventDefault();togglePause(true);}});
document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelCheckIn();stopMicrophone(false);stopSpeech();}else{openFollowUpWindow();void refreshData();scheduleWake();}});
window.addEventListener('pagehide',()=>{cancelCheckIn();stopMicrophone(false);stopSpeech();});
window.addEventListener('online',()=>{state.recognitionRetryAt=0;state.recognitionFailures=0;scheduleWake();});

function updateClock() {
  const now=new Date(),hour=now.getHours();
  $('#greeting').textContent=(hour<12?'Good morning.':hour<17?'Good afternoon.':'Good evening.')+' Your command center.';
  $('#today-date').textContent=now.toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric'});
  $('#today-short').textContent=now.toLocaleDateString(undefined,{month:'short',day:'numeric'});
}
function cancelCheckIn() {
  state.checkInEpoch=(state.checkInEpoch || 0)+1;
  state.checkInController?.abort();
  state.checkInController=null;state.checkingIn=false;state.checkInVisual=false;
}
async function conversationCheckIn(greeting=false) {
  if(!state.historyLoaded || state.busy || state.speaking || state.dialog || document.hidden || state.checkingIn || (!greeting && !state.proactive))return;
  const activity=state.lastInteraction,epoch=state.checkInEpoch || 0,controller=new AbortController();
  state.checkingIn=true;state.checkInController=controller;state.lastCheckIn=Date.now();
  try {
    const image=!greeting && $('#proactive-vision').checked ? await visualInputs.captureSharedView() : null;
    state.checkInVisual=Boolean(image);
    if(controller.signal.aborted || document.hidden || epoch!==(state.checkInEpoch || 0))return;
    const data=await api('/api/check-in',{kind:greeting?'greeting':'suggestion',...(image?{visual:true,attachments:[image]}:{})},image?120000:12000,controller.signal);
    if(!data.reply || controller.signal.aborted || document.hidden || epoch!==(state.checkInEpoch || 0) || state.busy || state.speaking || state.dialog || state.lastInteraction!==activity)return;
    if(!greeting && (!state.proactive || (image && !$('#proactive-vision').checked)))return;
    addMessage(data.reply,'sara','local-check-in');
    if(state.speak)void speak(data.reply);
  } catch(error){if(greeting && !controller.signal.aborted)toast(error.message);}
  finally {if(state.checkInController===controller){state.checkingIn=false;state.checkInVisual=false;state.checkInController=null;}}
}
updateClock();setInterval(updateClock,60000);
const retryVoice=el('button','text-button','Retry voice');retryVoice.id='retry-voice';retryVoice.type='button';retryVoice.hidden=true;
$('#stop-speech').after(retryVoice);
retryVoice.addEventListener('click',()=>{setSpeakPreference(true);void speak(state.lastSpeechText || 'नमस्ते, मैं सारा हूँ। अब मेरी आवाज़ सुनाई दे रही है?',true);});
void api('/api/voices/windows',undefined,12000).then(data=>{state.windowsVoices=data.available&&Array.isArray(data.voices)?data.voices:[];populateVoices();}).catch(()=>{});
const proactiveMinutes=$('#proactive-minutes');
proactiveMinutes.value=['5','15','30','60'].includes(prefs.get('sara-proactive-minutes'))?prefs.get('sara-proactive-minutes'):'15';
proactiveMinutes.addEventListener('change',()=>prefs.set('sara-proactive-minutes',proactiveMinutes.value));
setInterval(()=>{
  const interval=Number(proactiveMinutes.value || 15)*60000;
  if(state.proactive && Date.now()-Math.max(state.lastInteraction,state.lastCheckIn || 0)>=interval)void conversationCheckIn();
},60000);
$('#voice-rate').min='0.85';$('#voice-rate').max='1.4';
$('#voice-rate').value=String(Math.min(1.4,Math.max(.85,Number(prefs.get('sara-voice-rate','1.15'))||1.15)));
$('#rate-value').textContent=Number($('#voice-rate').value).toFixed(2)+'×';
$('#recognition-language').value=['en-IN','hi-IN','en-US'].includes(prefs.get('sara-recognition-language'))?prefs.get('sara-recognition-language'):'en-IN';
initializeVoiceModeControl();
$('#proactive-toggle').checked=state.proactive;setSpeakPreference(state.speak);setWakePreference(state.wake,false);populateVoices();
window.speechSynthesis?.addEventListener('voiceschanged',()=>{voiceListWaitCompleted=false;populateVoices();});
if(!SpeechRecognition){$('#mic-button').disabled=true;$('#wake-toggle').disabled=true;$('#voice-status').textContent='Voice input unavailable in this browser · text chat is ready';}
ensurePronunciationSettings();
ensureAppSettings();
ensureCapabilityRequestSettings();
setView(location.hash.slice(1)||'home',false);
// Speech recognition requires a browser permission and, on some browsers, one user gesture.
// Keep wake mode armed across reloads and start it as soon as that permission is available.
const wakeGesture=()=>{state.lastInteraction=Date.now();if(state.wake&&!state.recognizing&&!state.busy&&!state.speaking){state.wakeGestureReady=true;scheduleWake();}};
document.addEventListener('pointerdown',wakeGesture,{passive:true});
document.addEventListener('keydown',wakeGesture,{passive:true});
// Permission may already be granted on a later visit. Reading its state does
// not request access; a denial remains blocked until permission changes/retry.
navigator.permissions?.query({name:'microphone'}).then(permission=>{
  const changed=()=>{if(permission.state==='granted'){
    if(['not-allowed','service-not-allowed'].includes(state.recognitionBlocked))state.recognitionBlocked='';
    state.wakeGestureReady=true;scheduleWake();
  }else if(permission.state==='denied' && state.wake){
    pauseRecognition();state.recognitionBlocked='not-allowed';$('#voice-status').textContent='Microphone permission needed · allow access in browser settings';
  }};
  permission.addEventListener('change',changed);changed();
}).catch(()=>{ /* Some browsers do not expose microphone permission status. */ });
$('#send-button').disabled=true;
state.ready=true;
void refreshData(true);
try {await chatLibrary.load();state.historyLoaded=true;scheduleWake();$('#send-button').disabled=false;}
catch {toast('Chats could not load. Refresh after starting SARA; chat is paused to protect conversation history.');}
void api('/api/action-state?session_id='+encodeURIComponent(SESSION_ID)).then(data=>{if(data.pending && !state.pendingAction && !state.busy){const action={...data.pending.action,proposal_id:data.pending.id};attachProposal(addMessage('Is session ka ek action abhi approval ke liye pending hai.','sara','action-state'),action);}}).catch(()=>{});
if(state.wake && !state.recognitionBlocked && !state.recognizing) {$('#voice-status').textContent=state.wakeGestureReady?listeningStatus():'Wake mode ready · tap microphone once to begin';scheduleWake();}
setInterval(()=>{if(!document.hidden && !state.busy && !state.dialog)refreshData();},30000);
