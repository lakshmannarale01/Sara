// Appearance changes keep the existing chat, capture and review controls in place.
const THEMES = {
  jarvis: {name:'Jarvis', accent:'#68e7ff', secondary:'#ff984f', style:'rings', bg:'#04090e', surface:'#08131c'},
  companion: {name:'Warm companion', accent:'#ffbb91', secondary:'#ead495', style:'orbit', bg:'#171015', surface:'#261d24'},
  playful: {name:'Playful buddy', accent:'#c8a8ff', secondary:'#91e8d0', style:'buddy', bg:'#141024', surface:'#211a36'},
  aurora: {name:'Aurora', accent:'#81ebc6', secondary:'#b7acff', style:'orbit', bg:'#071714', surface:'#102924'},
  minimal: {name:'Focus', accent:'#d0dbe7', secondary:'#94b9c9', style:'minimal', bg:'#101419', surface:'#1a2028'},
};
const KEYS=Object.keys(THEMES), MODES=['manual','daily','session'];
export function initializeAppearance({canRotate=()=>true}={}) {
  const read=(key,fallback)=>{try{return localStorage.getItem(key)||fallback;}catch{return fallback;}};
  const save=(key,value)=>{try{localStorage.setItem(key,value);}catch{/* Session-only choice. */}};
  let theme=read('sara-look','jarvis'), mode=read('sara-look-mode','daily');
  if(!THEMES[theme])theme='jarvis'; if(!MODES.includes(mode))mode='manual';
  let lastSlot='';
  const card=document.createElement('section'); card.className='panel settings-card appearance-card';
  card.innerHTML='<h2>Make SARA yours</h2><p>Choose a look, or let it change with your day.</p><label for="sara-look">Dashboard look</label><select id="sara-look"></select><label for="sara-look-mode">Change automatically</label><select id="sara-look-mode"><option value="manual">Keep my choice</option><option value="daily">A different look each day</option><option value="session">Every 30 minutes while idle</option></select><button type="button" id="sara-next-look" class="quiet-button">Try another look</button><p class="card-note">Looks change colours and the animated companion. Voice, chat, sharing and approvals keep their current state. Motion follows your system accessibility preference.</p>';
  document.querySelector('#view-settings .settings-grid')?.prepend(card);
  const select=card.querySelector('#sara-look'), schedule=card.querySelector('#sara-look-mode');
  for(const [key,value] of Object.entries(THEMES)){const option=document.createElement('option');option.value=key;option.textContent=value.name;select.append(option);}
  const quick=document.createElement('button');quick.type='button';quick.className='quiet-button appearance-quick';quick.setAttribute('aria-label','Change SARA dashboard look');
  document.querySelector('.topbar-right')?.prepend(quick);
  function apply(){
    const value=THEMES[theme], root=document.documentElement;
    root.dataset.look=theme;root.dataset.coreStyle=value.style;
    for(const [name,color] of Object.entries({accent:value.accent,'look-secondary':value.secondary,bg:value.bg,surface:value.surface}))root.style.setProperty('--'+name,color);
    select.value=theme;schedule.value=mode;quick.textContent='Look: '+value.name;
    save('sara-look',theme);save('sara-look-mode',mode);
    document.dispatchEvent(new CustomEvent('sara-appearance',{detail:value}));
  }
  function rotate(){
    if(mode==='manual'||document.hidden||!canRotate())return;
    const now=new Date(), day=Math.floor(Date.UTC(now.getFullYear(),now.getMonth(),now.getDate())/86400000);
    const slot=mode==='daily'?day:Math.floor(Date.now()/1800000);
    if(lastSlot===mode+slot)return;
    lastSlot=mode+slot;theme=KEYS[((slot%KEYS.length)+KEYS.length)%KEYS.length];apply();
  }
  function next(){mode='manual';theme=KEYS[(KEYS.indexOf(theme)+1)%KEYS.length];apply();}
  select.addEventListener('change',()=>{theme=select.value;mode='manual';apply();});
  schedule.addEventListener('change',()=>{mode=schedule.value;lastSlot='';apply();rotate();});
  quick.addEventListener('click',next);card.querySelector('#sara-next-look').addEventListener('click',next);
  apply();rotate();const timer=setInterval(rotate,30000);document.addEventListener('visibilitychange',rotate);
  return {destroy(){clearInterval(timer);document.removeEventListener('visibilitychange',rotate);quick.remove();card.remove();}};
}
