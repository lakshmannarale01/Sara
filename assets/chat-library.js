export function initializeChats({request,onSelect,isBusy,onError}) {
  let selected='',rows=[],loading=false;
  const bar=document.createElement('div');bar.className='chat-library';
  bar.innerHTML='<label class="sr-only" for="chat-picker">Saved chats</label><select id="chat-picker" aria-label="Saved chats"></select><button id="new-chat" type="button">+ New chat</button><button id="rename-chat" type="button">Rename</button><button id="export-chat" type="button">Export</button><button id="delete-chat" type="button">Delete</button>';
  document.querySelector('#conversation-panel .panel-header').after(bar);
  const picker=bar.querySelector('select');
  function render(){picker.replaceChildren();for(const row of rows){const option=document.createElement('option');option.value=row.id;option.textContent=row.title;picker.append(option);}picker.value=selected;}
  async function refresh(){rows=await request('/api/chats');render();}
  async function choose(id){
    const messages=await request('/api/conversations?chat_id='+encodeURIComponent(id));
    await onSelect(id,messages);selected=id;
    try{localStorage.setItem('sara-active-chat',id);}catch{}
    render();
  }
  async function run(fn){
    if(loading||isBusy()){render();onError('Finish the current reply/review or clear your draft before changing chats.');return;}
    loading=true;for(const node of bar.children)node.disabled=true;
    try{await fn();}catch(error){onError(error.message);render();}
    finally{loading=false;for(const node of bar.children)node.disabled=false;}
  }
  picker.addEventListener('change',()=>void run(()=>choose(picker.value)));
  bar.querySelector('#new-chat').onclick=()=>void run(async()=>{const row=await request('/api/chats/create',{chat_id:null});await refresh();await choose(row.id);});
  bar.querySelector('#rename-chat').onclick=()=>void run(async()=>{const title=prompt('Chat name',rows.find(row=>row.id===selected)?.title||'');if(title?.trim()){await request('/api/chats/rename',{chat_id:selected,title:title.trim()});await refresh();}});
  bar.querySelector('#delete-chat').onclick=()=>void run(async()=>{
    if(!confirm('Delete this chat and its saved messages? This cannot be undone.'))return;
    await request('/api/chats/delete',{chat_id:selected,confirmed:true});await refresh();
    if(!rows.length){await request('/api/chats/create',{chat_id:null});await refresh();}
    await choose(rows[0].id);
  });
  bar.querySelector('#export-chat').onclick=()=>void run(async()=>{
    const messages=await request('/api/conversations?chat_id='+selected),title=rows.find(row=>row.id===selected)?.title||'SARA chat';
    const text=title+'\n\n'+messages.map(item=>(item.initiated_by==='sara'?'':('You: '+(item.question||'')+'\n'))+'SARA: '+(item.answer||'')).join('\n\n');
    const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='sara-chat.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  return {refresh,async load(){await refresh();if(!rows.length){await request('/api/chats/create',{chat_id:null});await refresh();}let saved;try{saved=localStorage.getItem('sara-active-chat');}catch{}await choose(rows.some(row=>row.id===saved)?saved:rows[0].id);}};
}
