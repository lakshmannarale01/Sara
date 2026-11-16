// UI controls submit named commands or reviewed routine definitions, never OS input.
const MAX_STEPS = 8;
const MEDIA = [
  ['set_volume', 'Set volume'], ['volume_up', 'Volume up'], ['volume_down', 'Volume down'],
  ['mute', 'Mute'], ['unmute', 'Unmute'], ['play_pause', 'Play / pause'],
  ['next_track', 'Next track'], ['previous_track', 'Previous track'], ['stop', 'Stop playback'],
];
const node = (tag, className = '', text = '') => {
  const item = document.createElement(tag); item.className = className;
  if (text) item.textContent = text;
  return item;
};
function button(text, id = '', className = 'quiet-button') {
  const item = node('button', className, text); item.type = 'button'; if (id) item.id = id; return item;
}
function select(options, role) {
  const item = node('select'); item.dataset.role = role;
  for (const [value, text] of options) item.add(new Option(text, value));
  return item;
}
function field(label, input) {
  const wrapper = node('label', 'ability-field'); wrapper.append(node('span', '', label), input); return wrapper;
}
function stepDescription(step) {
  if (step.type === 'open_app') return 'Open ' + step.app;
  if (step.type === 'youtube_play') return 'Play on YouTube: ' + step.query;
  if (step.type === 'media_control') return (MEDIA.find(([value]) => value === step.command)?.[1] || 'Audio command') + (step.command === 'set_volume' ? ' · ' + step.level + '%' : '');
  if (step.type === 'open_browser_url' || step.type === 'browser_open') return 'Open ' + step.url;
  return 'Unsupported step';
}

export function initializeAbilities({request, onCommand, onReview, onError = () => {}} = {}) {
  const host = document.querySelector('#view-settings .settings-grid');
  if (!host || document.getElementById('assistant-abilities')) return {refresh: async () => {}, destroy() {}};
  const panel = node('section', 'panel settings-card abilities-panel'); panel.id = 'assistant-abilities';
  panel.setAttribute('aria-labelledby', 'abilities-heading');
  const heading = node('h2', '', 'Audio & saved routines'); heading.id = 'abilities-heading';
  panel.append(heading, node('p', 'card-note', 'Use a quick command, or save a few supported steps to run together. SARA applies your current action permissions.'));
  const error = node('p', 'ability-error'); error.id = 'abilities-error'; error.role = 'alert'; error.hidden = true;
  panel.append(error);
  const audio = node('div', 'ability-audio');
  const audioHeader = node('div', 'ability-section-header');
  audioHeader.append(node('h3', '', 'Speaker & playback'));
  const audioRefresh = button('Refresh audio', 'abilities-audio-refresh'); audioHeader.append(audioRefresh);
  const audioStatus = node('p', 'card-note', 'Checking Windows audio…'); audioStatus.id = 'abilities-audio-status'; audioStatus.role = 'status';
  const volumeRow = node('div', 'ability-volume-row');
  const volume = node('input'); volume.id = 'abilities-volume'; volume.type = 'range'; volume.min = '0'; volume.max = '100'; volume.step = '1'; volume.value = '50';
  const volumeOutput = node('output', '', '50%'); volumeOutput.id = 'abilities-volume-value'; volumeOutput.htmlFor = volume.id;
  const volumeField = field('Volume to request', volume); volumeField.append(volumeOutput);
  const applyVolume = button('Apply volume', 'abilities-volume-apply');
  volumeRow.append(volumeField, applyVolume);
  const mediaButtons = node('div', 'ability-buttons');
  const commands = [['Mute', 'mute karo'], ['Unmute', 'unmute karo'], ['Play / pause', 'play pause'], ['Previous', 'previous song'], ['Next', 'next song']];
  for (const [label, command] of commands) {const item = button(label); item.dataset.command = command; mediaButtons.append(item);}
  audio.append(audioHeader, audioStatus, volumeRow, mediaButtons);
  panel.append(audio);
  const saved = node('div', 'ability-routines');
  const savedHeader = node('div', 'ability-section-header'); savedHeader.append(node('h3', '', 'Your routines'));
  const routinesRefresh = button('Refresh routines', 'routines-refresh'); savedHeader.append(routinesRefresh);
  const list = node('div', 'routine-list'); list.id = 'routine-list'; list.setAttribute('aria-live', 'polite');
  saved.append(savedHeader, list);
  const builder = node('div', 'routine-builder');
  builder.append(node('h3', '', 'Create a routine'), node('p', 'card-note', 'Example: name it Work mode, then add Open Notepad and Set volume. Review the complete steps before saving.'));
  const name = node('input'); name.type = 'text'; name.id = 'routine-name'; name.maxLength = 60; name.placeholder = 'e.g. Work mode';
  builder.append(field('Routine name', name));
  const rows = node('div', 'routine-steps'); rows.id = 'routine-steps'; builder.append(rows);
  const builderButtons = node('div', 'ability-buttons');
  const add = button('Add a step', 'routine-add-step'), save = button('Review & save routine', 'routine-save', 'primary-button');
  builderButtons.append(add, save); builder.append(builderButtons);
  saved.append(builder); panel.append(saved); host.append(panel);
  let destroyed = false, serial = 0, saving = false, audioAvailable = false, volumeEdited = false;
  let audioRequest = 0, routineRequest = 0;
  const listeners = [];
  const listen = (target, event, callback) => {target.addEventListener(event, callback); listeners.push(() => target.removeEventListener(event, callback));};
  const report = problem => {if (destroyed) return; const text = problem?.message || String(problem); error.textContent = text; error.hidden = false; onError(text);};
  const clearError = () => {error.hidden = true; error.textContent = '';};
  const audioInputs = () => [volume, applyVolume, ...mediaButtons.querySelectorAll('button')];
  const enableAudio = enabled => {audioInputs().forEach(item => {item.disabled = !enabled;});};
  async function command(text, control) {
    clearError(); control.disabled = true;
    try {if (!onCommand) throw new Error('Commands are not connected. Reload SARA.'); await onCommand(text);}
    catch (problem) {report(problem);}
    finally {if (!destroyed) control.disabled = control === applyVolume || control.closest('.ability-audio') ? !audioAvailable : false;}
  }
  async function refreshAudio() {
    const epoch = ++audioRequest; audioRefresh.disabled = true;
    try {
      if (!request) throw new Error('Audio status is not connected.');
      const status = await request('/api/audio/status');
      if (destroyed || epoch !== audioRequest) return;
      audioAvailable = status.available === true;
      const actualVolume = typeof status.volume === 'number' && Number.isFinite(status.volume) && status.volume >= 0 && status.volume <= 100 ? Math.round(status.volume) : null;
      audioStatus.textContent = audioAvailable
        ? 'Windows speaker: ' + (actualVolume === null ? 'volume unavailable' : actualVolume + '%') + (typeof status.muted === 'boolean' ? status.muted ? ' · muted' : ' · not muted' : '')
        : status.reason || status.error || 'Windows audio controls are unavailable. Start SARA on Windows, then refresh.';
      if (actualVolume !== null && !volumeEdited) {volume.value = String(actualVolume); volumeOutput.value = actualVolume + '%';}
      enableAudio(audioAvailable);
    } catch (problem) {if (!destroyed && epoch === audioRequest) {audioAvailable = false; enableAudio(false); audioStatus.textContent = 'Audio status could not load. Refresh after SARA starts.'; report(problem);}}
    finally {if (!destroyed && epoch === audioRequest) audioRefresh.disabled = false;}
  }
  function updateRows() {
    [...rows.children].forEach((row, index) => {row.querySelector('legend').textContent = 'Step ' + (index + 1); row.querySelector('[data-role="remove"]').setAttribute('aria-label', 'Remove step ' + (index + 1));});
    add.disabled = rows.children.length >= MAX_STEPS || saving;
  }
  function addStep() {
    if (rows.children.length >= MAX_STEPS || destroyed) return;
    const row = node('fieldset', 'routine-step'); row.dataset.step = String(++serial);
    row.append(node('legend', '', 'Step'));
    const kind = select([['open_app', 'Open an app'], ['search', 'Search the web'], ['youtube_play', 'Play on YouTube'], ['website', 'Open a supported website'], ['media_control', 'Audio / playback']], 'kind');
    kind.setAttribute('aria-label', 'Step action');
    const remove = button('Remove'); remove.dataset.role = 'remove';
    const top = node('div', 'routine-step-top'); top.append(field('Action', kind), remove); row.append(top);
    const app = select([['notepad', 'Notepad'], ['calculator', 'Calculator'], ['chrome', 'Chrome']], 'app');
    const appField = field('Application', app); row.append(appField);
    const query = node('input'); query.type = 'text'; query.dataset.role = 'query'; query.maxLength = 200; query.placeholder = 'What should SARA search or play?';
    const queryField = field('Search or song', query); row.append(queryField);
    const url = node('input'); url.type = 'url'; url.dataset.role = 'url'; url.maxLength = 2000; url.placeholder = 'https://…';
    const urlField = field('Supported website URL', url); row.append(urlField);
    const media = select(MEDIA, 'media'), level = node('input'); level.type = 'number'; level.min = '0'; level.max = '100'; level.step = '1'; level.value = '30'; level.dataset.role = 'level';
    const mediaField = field('Audio command', media), levelField = field('Volume percent (0–100)', level); row.append(mediaField, levelField);
    function update() {
      appField.hidden = kind.value !== 'open_app'; queryField.hidden = !['search', 'youtube_play'].includes(kind.value);
      urlField.hidden = kind.value !== 'website'; mediaField.hidden = kind.value !== 'media_control';
      levelField.hidden = kind.value !== 'media_control' || media.value !== 'set_volume';
    }
    kind.addEventListener('change', update); media.addEventListener('change', update);
    remove.addEventListener('click', () => {row.remove(); updateRows();});
    rows.append(row); update(); updateRows();
  }
  function stepsFromForm() {
    const entries = [...rows.children];
    if (!entries.length || entries.length > MAX_STEPS) throw new Error('Add between one and eight steps.');
    return entries.map((row, index) => {
      const value = role => row.querySelector('[data-role="' + role + '"]').value;
      const kind = value('kind');
      if (kind === 'open_app') return {type: 'open_app', app: value('app')};
      if (kind === 'search' || kind === 'youtube_play') {
        const query = value('query').trim(); if (!query) throw new Error('Enter a search or song for step ' + (index + 1) + '.');
        return kind === 'search' ? {type: 'open_browser_url', url: 'https://www.google.com/search?q=' + encodeURIComponent(query)} : {type: 'youtube_play', query};
      }
      if (kind === 'website') {
        let target; try {target = new URL(value('url').trim());} catch {throw new Error('Enter a complete HTTPS URL for step ' + (index + 1) + '.');}
        if (target.protocol !== 'https:' || target.username || target.password) throw new Error('Step ' + (index + 1) + ' needs an HTTPS URL without login details.');
        return {type: 'open_browser_url', url: target.href};
      }
      if (kind === 'media_control') {
        const command = value('media');
        if (command !== 'set_volume') return {type: 'media_control', command};
        const raw = value('level').trim(), level = Number(raw);
        if (!raw || !Number.isInteger(level) || level < 0 || level > 100) throw new Error('Choose a whole volume percent from 0 to 100 for step ' + (index + 1) + '.');
        return {type: 'media_control', command, level};
      }
      throw new Error('Choose a supported step action.');
    });
  }
  async function refreshRoutines() {
    const epoch = ++routineRequest; routinesRefresh.disabled = true;
    try {
      if (!request) throw new Error('Saved routines are not connected.');
      const data = await request('/api/routines');
      if (destroyed || epoch !== routineRequest) return;
      if (!Array.isArray(data.routines)) throw new Error('SARA returned an invalid routine list.');
      list.replaceChildren();
      if (!data.routines.length) list.append(node('p', 'card-note', 'No saved routines yet. Create one below, then say “run routine Work mode”.'));
      for (const routine of data.routines) {
        if (!routine || typeof routine.name !== 'string' || typeof routine.id !== 'string' || !Array.isArray(routine.steps)) continue;
        const card = node('article', 'saved-routine'); card.append(node('strong', '', routine.name));
        const steps = node('ol'); routine.steps.slice(0, MAX_STEPS).forEach(step => steps.append(node('li', '', stepDescription(step || {})))); card.append(steps);
        const controls = node('div', 'ability-buttons'), run = button('Run routine'), remove = button('Review removal');
        run.dataset.role = 'run'; remove.dataset.role = 'delete';
        run.addEventListener('click', () => {if (/["\r\n]/.test(routine.name)) {report(new Error('This routine name needs updating before voice/chat execution.')); return;} void command('run routine "' + routine.name + '"', run);});
        remove.addEventListener('click', async () => {
          clearError(); remove.disabled = true;
          try {if (!onReview) throw new Error('Action review is not connected.'); if (await onReview({type: 'delete_routine', id: routine.id, revision: routine.revision, name: routine.name, label: 'Remove saved routine: ' + routine.name})) await refreshRoutines();}
          catch (problem) {report(problem);}
          finally {if (!destroyed) remove.disabled = false;}
        });
        controls.append(run, remove); card.append(controls); list.append(card);
      }
    } catch (problem) {if (!destroyed && epoch === routineRequest) {list.replaceChildren(node('p', 'card-note', 'Saved routines could not load. Refresh to try again.')); report(problem);}}
    finally {if (!destroyed && epoch === routineRequest) routinesRefresh.disabled = false;}
  }
  listen(volume, 'input', () => {volumeEdited = true; volumeOutput.value = volume.value + '%';});
  listen(applyVolume, 'click', () => void command('volume ' + volume.value + ' percent karo', applyVolume));
  for (const item of mediaButtons.children) listen(item, 'click', () => void command(item.dataset.command, item));
  listen(audioRefresh, 'click', () => {volumeEdited = false; void refreshAudio();});
  listen(routinesRefresh, 'click', () => void refreshRoutines()); listen(add, 'click', addStep);
  listen(save, 'click', async () => {
    if (saving) return; clearError();
    try {
      const routineName = name.value.trim();
      if (!routineName || routineName.length > 60 || /["\r\n]/.test(routineName)) throw new Error('Choose a routine name from 1 to 60 characters, without quotes or new lines.');
      const steps = stepsFromForm(); if (!onReview) throw new Error('Action review is not connected.');
      saving = true; save.disabled = true; updateRows();
      if (await onReview({type: 'save_routine', name: routineName, steps, label: 'Save routine: ' + routineName})) await refreshRoutines();
    } catch (problem) {report(problem);}
    finally {saving = false; if (!destroyed) {save.disabled = false; updateRows();}}
  });
  addStep(); enableAudio(false);
  async function refresh() {await Promise.allSettled([refreshAudio(), refreshRoutines()]);}
  void refresh();
  return {refresh, destroy() {if (destroyed) return; destroyed = true; audioRequest++; routineRequest++; listeners.forEach(remove => remove()); panel.remove();}};
}
