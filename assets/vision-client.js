// Images stay in this page's memory. Capture begins only from explicit controls.
const MAX_IMAGES = 4;
const MAX_BYTES = 10 * 1024 * 1024;
const MAX_EDGE = 1600;
const IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp']);

export function initializeVisionControls({request, onError = () => {}, onImagesChange = () => {}} = {}) {
  const find = id => document.getElementById(id);
  const input = find('attachment-input'), list = find('attachment-list');
  const message = find('message'), stage = find('visual-preview');
  const video = find('visual-video'), status = find('visual-status');
  const screenButton = find('share-screen'), cameraButton = find('share-camera');
  const captureButton = find('capture-frame'), stopButton = find('stop-visual');
  const includeLive = find('include-live-view'), errorNode = find('attachment-error');
  if (!input || !list || !message || !video) {
    return {attachmentsForMessage: async () => [], captureSharedView: async () => null, getChatAttachments: () => [], clearSentAttachments() {}, destroy() {}};
  }
  let queue = [], stream = null, source = '', starting = false, serial = Promise.resolve();
  let nextId = 0, mediaEpoch = 0, destroyed = false, preparing = 0;
  const listeners = [];
  const screenSupported = Boolean(navigator.mediaDevices?.getDisplayMedia);
  const cameraSupported = Boolean(navigator.mediaDevices?.getUserMedia);
  const listen = (node, name, handler) => {
    node?.addEventListener(name, handler);
    listeners.push(() => node?.removeEventListener(name, handler));
  };
  const report = error => {
    const text = error?.message || String(error);
    errorNode.textContent = text; errorNode.hidden = false; onError(text);
  };
  const clearError = () => {errorNode.hidden = true; errorNode.textContent = '';};
  const byteSize = data => Math.floor((data.length - data.indexOf(',') - 1) * 3 / 4);
  const changed = () => {
    message.required = !queue.length && !(stream && includeLive.checked);
    list.replaceChildren(); list.hidden = !queue.length;
    for (const item of queue) {
      const card = document.createElement('div'); card.className = 'attachment-card';
      const image = document.createElement('img'); image.src = item.data_url; image.alt = item.name;
      const caption = document.createElement('span'); caption.textContent = item.name;
      const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '×';
      remove.className = 'attachment-remove'; remove.setAttribute('aria-label', 'Remove ' + item.name);
      remove.addEventListener('click', () => {queue = queue.filter(entry => entry.id !== item.id); changed();});
      card.append(image, caption, remove); list.append(card);
    }
    find('attachment-count').textContent = preparing ? 'Preparing image…' : queue.length ? queue.length + ' / ' + MAX_IMAGES + ' images ready' : 'Paste or drop an image';
    onImagesChange({count: queue.length, activeSource: source, preparing: Boolean(preparing)});
  };
  function updateMedia() {
    stage.hidden = !stream;
    stopButton.hidden = !stream && !starting;
    captureButton.hidden = !stream;
    screenButton.disabled = starting || !screenSupported;
    cameraButton.disabled = starting || !cameraSupported;
    screenButton.setAttribute('aria-pressed', String(source === 'screen'));
    cameraButton.setAttribute('aria-pressed', String(source === 'camera'));
    status.textContent = starting ? 'Waiting for your permission…' : stream
      ? (source === 'screen' ? 'Screen' : 'Camera') + ' preview active · only sent snapshots reach SARA'
      : 'Screen and camera are off';
    status.classList.toggle('is-live', Boolean(stream)); changed();
  }
  function stopVisual() {
    mediaEpoch++; starting = false;
    const previous = stream; stream = null; source = '';
    previous?.getTracks().forEach(track => track.stop());
    video.pause(); video.srcObject = null; updateMedia();
  }
  function mediaError(error) {
    if (error?.name === 'NotAllowedError' || error?.name === 'PermissionDeniedError') {
      return new Error('Access was not granted. Click Share screen or Camera again and allow it in the browser/Windows permission prompt.');
    }
    if (error?.name === 'NotFoundError') return new Error('No camera was found. Connect one and try again.');
    if (error?.name === 'NotReadableError') return new Error('The camera or screen is busy. Close another app using it, then try again.');
    return new Error(error?.message || 'Visual access could not start. Use the image attachment button instead.');
  }
  async function startVisual(kind) {
    if (destroyed || starting) return;
    clearError(); stopVisual();
    const epoch = ++mediaEpoch; starting = true; updateMedia();
    try {
      // Keep this call in the click activation, before the first await.
      const pending = kind === 'screen'
        ? navigator.mediaDevices.getDisplayMedia({video: {frameRate: {ideal: 5, max: 10}}, audio: false})
        : navigator.mediaDevices.getUserMedia({video: {width: {ideal: 1280}, height: {ideal: 720}}, audio: false});
      const granted = await pending;
      if (destroyed || epoch !== mediaEpoch) {granted.getTracks().forEach(track => track.stop()); return;}
      stream = granted; source = kind; video.srcObject = stream; includeLive.checked = true;
      granted.getVideoTracks().forEach(track => track.addEventListener('ended', () => {if (stream === granted) stopVisual();}, {once: true}));
      await video.play();
    } catch (error) {
      if (epoch === mediaEpoch && !destroyed) {stopVisual(); report(mediaError(error));}
    } finally {
      if (epoch === mediaEpoch) {starting = false; updateMedia();}
    }
  }
  function encodeImage(image, width, height) {
    if (!width || !height || width * height > 40000000) throw new Error('The image dimensions are unsupported. Use an image smaller than 40 megapixels.');
    const scale = Math.min(1, MAX_EDGE / Math.max(width, height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(width * scale)); canvas.height = Math.max(1, Math.round(height * scale));
    const context = canvas.getContext('2d');
    if (!context) throw new Error('This browser cannot prepare images. Try the current Edge or Chrome browser.');
    context.fillStyle = '#fff'; context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', .9);
  }
  function addPrepared(data_url, origin, name) {
    if (destroyed) return;
    if (queue.length >= MAX_IMAGES) throw new Error('Up to four images can be sent together. Remove an image or send this message first.');
    const bytes = byteSize(data_url);
    if (queue.reduce((total, entry) => total + entry.bytes, 0) + bytes > MAX_BYTES) throw new Error('Images must total less than 10 MB. Remove an image or choose smaller files.');
    queue.push({id: ++nextId, data_url, source: origin, name, bytes}); changed();
  }
  async function loadFile(file) {
    if (!IMAGE_TYPES.has(file.type)) throw new Error('Choose a PNG, JPEG or WebP image. Other file types are not supported.');
    if (!file.size || file.size > MAX_BYTES) throw new Error('Choose a non-empty image smaller than 10 MB.');
    if (queue.length >= MAX_IMAGES) throw new Error('Up to four images can be sent together. Remove an image first.');
    const url = URL.createObjectURL(file);
    try {
      const image = new Image(); image.src = url; await image.decode();
      addPrepared(encodeImage(image, image.naturalWidth, image.naturalHeight), 'upload', file.name || 'Pasted image');
    } catch (error) {
      if (error?.name === 'EncodingError') throw new Error('The image could not be decoded. Try another PNG, JPEG or WebP file.');
      throw error;
    } finally {URL.revokeObjectURL(url);}
  }
  function ingest(files) {
    if (!files.length) return;
    clearError(); preparing += files.length; changed();
    for (const file of files) {
      serial = serial.then(() => destroyed ? undefined : loadFile(file)).catch(report).finally(() => {preparing--; if (!destroyed) changed();});
    }
  }
  async function snapshot() {
    if (!stream || !stream.getVideoTracks().some(track => track.readyState === 'live')) throw new Error('Visual sharing stopped. Start screen or camera sharing again.');
    if (!video.videoWidth || !video.videoHeight || video.readyState < 2) throw new Error('The preview is still starting. Wait a moment before sending a snapshot.');
    return {data_url: encodeImage(video, video.videoWidth, video.videoHeight), source};
  }
  listen(find('attach-image'), 'click', () => input.click());
  listen(input, 'change', () => {ingest([...input.files]); input.value = '';});
  listen(message, 'paste', event => {
    const images = [...(event.clipboardData?.items || [])].filter(item => item.kind === 'file' && item.type.startsWith('image/')).map(item => item.getAsFile()).filter(Boolean);
    if (images.length) {event.preventDefault(); ingest(images);}
  });
  const conversation = find('conversation-panel');
  listen(conversation, 'dragover', event => {if ([...(event.dataTransfer?.types || [])].includes('Files')) {event.preventDefault(); conversation.classList.add('image-dragover');}});
  listen(conversation, 'dragleave', event => {if (!conversation.contains(event.relatedTarget)) conversation.classList.remove('image-dragover');});
  listen(conversation, 'drop', event => {conversation.classList.remove('image-dragover'); if (event.dataTransfer?.files.length) {event.preventDefault(); ingest([...event.dataTransfer.files]);}});
  listen(screenButton, 'click', () => {if (screenSupported) void startVisual('screen'); else report(new Error('Screen sharing is unavailable in this browser. Use Edge/Chrome at the local SARA address.'));});
  listen(cameraButton, 'click', () => {if (cameraSupported) void startVisual('camera'); else report(new Error('Camera access is unavailable in this browser. Use Edge/Chrome at the local SARA address.'));});
  listen(stopButton, 'click', stopVisual);
  listen(includeLive, 'change', changed);
  listen(captureButton, 'click', async () => {
    try {clearError(); const image = await snapshot(); addPrepared(image.data_url, image.source, image.source === 'screen' ? 'Screen snapshot' : 'Camera snapshot'); includeLive.checked = false; changed();}
    catch (error) {report(error);}
  });
  listen(window, 'pagehide', stopVisual);

  const access = find('access-mode'), accessStatus = find('access-mode-status');
  function displayAccess(data) {
    const mode = data?.mode === 'trusted' ? 'trusted' : 'review';
    access.value = mode;
    accessStatus.textContent = mode === 'trusted'
      ? 'Trusted routine mode: supported browsing and app launches run directly. Sending, deleting and sensitive changes still need review.'
      : 'Review mode: SARA asks before running actions. Choose Trusted routine mode to skip repeated browsing/app launch reviews.';
    return mode;
  }
  let savedMode = 'review';
  if (request && access) {
    access.disabled = true;
    void request('/api/access-mode').then(data => {savedMode = displayAccess(data); access.disabled = false;}).catch(() => {accessStatus.textContent = 'Access settings could not load. Restart SARA and reload this page.';});
    listen(access, 'change', async () => {
      const requested = access.value; access.disabled = true;
      try {savedMode = displayAccess(await request('/api/access-mode', {mode: requested}));}
      catch (error) {access.value = savedMode; report(error);}
      finally {access.disabled = false;}
    });
  }
  const modelStatus = find('vision-model-status'), refreshModel = find('refresh-vision-model');
  async function refreshVisionModel() {
    if (!request || !modelStatus || destroyed) return;
    refreshModel.disabled = true;
    try {
      const data = await request('/api/vision/status', undefined, 20000);
      if (destroyed) return;
      modelStatus.textContent = data.available
        ? 'Local image model: ' + data.model + ' · snapshots stay local'
        : data.reason || 'No local vision model is ready. Install a vision-capable Ollama model to understand images.';
      modelStatus.classList.toggle('vision-unavailable', !data.available);
    } catch {
      if (!destroyed) {modelStatus.textContent = 'Image model status unavailable. Start SARA/Ollama, then refresh.'; modelStatus.classList.add('vision-unavailable');}
    } finally {if (!destroyed) refreshModel.disabled = false;}
  }
  listen(refreshModel, 'click', () => void refreshVisionModel());
  void refreshVisionModel();
  updateMedia();
  return {
    // Called only from a user-visible command response; permission remains browser-controlled.
    startCamera() { if (cameraSupported) return startVisual('camera'); report(new Error('Camera access is unavailable in this browser.')); return Promise.resolve(); },
    startScreen() { if (screenSupported) return startVisual('screen'); report(new Error('Screen sharing is unavailable in this browser.')); return Promise.resolve(); },
    getChatAttachments() {return queue.map(({data_url, source}) => ({data_url, source}));},
    // The caller gates optional check-ins with explicit proactive-vision consent.
    // This reads only an already shared stream, never the user's pasted images.
    async captureSharedView() {return stream ? snapshot() : null;},
    async attachmentsForMessage() {
      await serial;
      const selected = queue.slice();
      const attachments = selected.map(({data_url, source}) => ({data_url, source}));
      if (stream && includeLive.checked) {
        if (attachments.length >= MAX_IMAGES) throw new Error('There are already four images queued. Uncheck “Include live view” or remove an image.');
        attachments.push(await snapshot());
      }
      if (attachments.reduce((total, image) => total + byteSize(image.data_url), 0) > MAX_BYTES) throw new Error('Images must total less than 10 MB. Remove an image before sending.');
      Object.defineProperty(attachments, 'queueIds', {value: selected.map(item => item.id)});
      return attachments;
    },
    clearSentAttachments(sent) {
      // A new image added during a slow model response must remain queued.
      if (!Array.isArray(sent)) return;
      const ids = new Set(sent.queueIds || []);
      queue = queue.filter(item => !ids.has(item.id)); clearError(); changed();
    },
    destroy() {
      if (destroyed) return;
      stopVisual(); destroyed = true; listeners.forEach(remove => remove()); queue = []; list.replaceChildren();
    },
  };
}
