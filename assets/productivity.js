// Free local focus and study tools. Timers use deadlines to survive hidden tabs.
export function initializeProductivity({onError,onCommand}) {
  const host=document.querySelector('#view-day');
  const panel=document.createElement('section');panel.className='panel productivity-panel';
  panel.innerHTML='<h2>Focus & study</h2><div class="productivity-row"><label>Focus minutes <input id="focus-minutes" type="number" min="1" max="120" value="25"></label><label>Break minutes <input id="break-minutes" type="number" min="1" max="60" value="5"></label></div><strong id="focus-phase">Focus</strong><output id="focus-clock" class="focus-clock">25:00</output><div class="productivity-row"><button id="focus-start">Start</button><button id="focus-pause">Pause</button><button id="focus-reset">Reset</button><button id="focus-next">Switch to break</button><span id="focus-count"></span></div><p id="focus-status" role="status"></p><h2>Flashcards</h2><p>One question :: answer per line. Cards and timer stay in this browser.</p><textarea id="study-source" maxlength="30000" aria-label="Flashcards" placeholder="What is velocity? :: Speed in a given direction"></textarea><div class="productivity-row"><button id="study-save">Save deck</button><button id="study-clear">Delete deck</button><button id="study-help">Ask SARA for a quiz</button></div><div id="study-card" class="study-card" aria-live="polite">Add a deck to begin.</div><div class="productivity-row"><button id="study-flip">Show answer</button><button id="study-known">I knew it</button><button id="study-again">Review again</button><span id="study-progress"></span></div>';
  host.append(panel);const $=id=>panel.querySelector('#'+id);
  const read=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key))||fallback;}catch{return fallback;}};
  const save=(key,value)=>{try{localStorage.setItem(key,JSON.stringify(value));return true;}catch{onError('Browser storage is full or unavailable. This change could not be saved.');return false;}};
  let timer=read('sara-focus',{phase:'focus',remaining:1500000,end:0,completed:0});
  if(!['focus','break'].includes(timer.phase)||!Number.isFinite(timer.remaining)||timer.remaining<0||!Number.isFinite(timer.end)||!Number.isInteger(timer.completed))timer={phase:'focus',remaining:1500000,end:0,completed:0};
  const minutes=id=>Math.max(1,Math.min(id==='focus-minutes'?120:60,Number($(id).value)|| (id==='focus-minutes'?25:5)));
  if(Number.isFinite(timer.focusMinutes))$('focus-minutes').value=String(Math.max(1,Math.min(120,timer.focusMinutes)));
  if(Number.isFinite(timer.breakMinutes))$('break-minutes').value=String(Math.max(1,Math.min(60,timer.breakMinutes)));
  function draw(){
    let left=timer.end?Math.max(0,timer.end-Date.now()):timer.remaining;
    if(timer.end&&left===0){if(timer.phase==='focus')timer.completed++;timer.end=0;timer.remaining=0;save('sara-focus',timer);$('focus-status').textContent=timer.phase==='focus'?'Focus complete. Take a break when ready.':'Break complete. Ready for the next focus session?';}
    const seconds=Math.ceil(left/1000);$('focus-clock').textContent=String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');
    $('focus-phase').textContent=timer.phase==='focus'?'Focus':'Break';$('focus-count').textContent=timer.completed+' sessions completed';
    $('focus-start').disabled=Boolean(timer.end);$('focus-pause').disabled=!timer.end;$('focus-next').textContent=timer.phase==='focus'?'Switch to break':'Switch to focus';
  }
  function reset(){timer.end=0;timer.focusMinutes=minutes('focus-minutes');timer.breakMinutes=minutes('break-minutes');timer.remaining=minutes(timer.phase==='focus'?'focus-minutes':'break-minutes')*60000;$('focus-status').textContent='';save('sara-focus',timer);draw();}
  $('focus-start').onclick=()=>{if(timer.remaining<=0)reset();timer.end=Date.now()+timer.remaining;save('sara-focus',timer);draw();};
  $('focus-pause').onclick=()=>{timer.remaining=Math.max(0,timer.end-Date.now());timer.end=0;save('sara-focus',timer);draw();};
  $('focus-reset').onclick=reset;$('focus-next').onclick=()=>{timer.phase=timer.phase==='focus'?'break':'focus';reset();};
  for(const id of ['focus-minutes','break-minutes'])$(id).onchange=()=>{if(!timer.end&&((timer.phase==='focus')===(id==='focus-minutes')))reset();};
  setInterval(draw,1000);draw();
  let deck=read('sara-study-deck',[]),index=0,revealed=false,known=0;
  if(!Array.isArray(deck)||deck.length>100||deck.some(c=>typeof c.q!=='string'||typeof c.a!=='string'))deck=[];
  $('study-source').value=deck.map(c=>c.q+' :: '+c.a).join('\n');
  function render(){const card=deck[index];$('study-card').textContent=card?(revealed?card.a:card.q):'Add a deck to begin.';$('study-flip').textContent=revealed?'Show question':'Show answer';$('study-progress').textContent=deck.length?`${index+1}/${deck.length} · ${known} correct this round`:'';for(const id of ['study-flip','study-known','study-again'])$(id).disabled=!card||(id!=='study-flip'&&!revealed);}
  $('study-save').onclick=()=>{const lines=$('study-source').value.split('\n').filter(x=>x.trim());if(!lines.length||lines.length>100||lines.some(x=>!x.includes('::')||!x.split('::')[0].trim()||!x.slice(x.indexOf('::')+2).trim()))return onError('Use 1–100 cards, each as question :: answer.');const next=lines.map(line=>({q:line.slice(0,line.indexOf('::')).trim(),a:line.slice(line.indexOf('::')+2).trim()}));if(save('sara-study-deck',next)){deck=next;index=0;known=0;revealed=false;render();}};
  $('study-clear').onclick=()=>{if(confirm('Delete this saved flashcard deck?')&&save('sara-study-deck',[])){deck=[];index=0;known=0;$('study-source').value='';render();}};
  $('study-flip').onclick=()=>{revealed=!revealed;render();};
  function next(correct){if(correct)known++;if(index+1===deck.length){onError(`Round finished: ${known} of ${deck.length} correct.`);index=0;known=0;}else index++;revealed=false;render();}
  $('study-known').onclick=()=>next(true);$('study-again').onclick=()=>next(false);
  $('study-help').onclick=()=>onCommand('Help me study. Ask which topic I want to practise, then quiz me one question at a time and explain my mistakes.');render();
}
