// Procedural SARA HUD. Geometry is drawn locally; no image, video or audio input.
const STATES = new Set(['ready', 'thinking', 'listening', 'speaking', 'review']);
const TAU = Math.PI * 2;

export function createHudCore(canvas, stage = canvas?.parentElement) {
  let context;
  try { context = canvas?.getContext('2d', { alpha: true }); } catch { /* Canvas may be unavailable. */ }
  if (!context || !stage) {
    if (canvas) canvas.dataset.renderer = 'unavailable';
    return { setState() {}, destroy() {} };
  }

  const doc = canvas.ownerDocument;
  const win = doc.defaultView;
  const preference = win.matchMedia?.('(prefers-reduced-motion: reduce)');
  let state = STATES.has(stage.dataset.state) ? stage.dataset.state : 'ready';
  let width = 0, height = 0, density = 1, phase = 0, frames = 0;
  let raf = 0, previous = 0, drawnAt = 0, destroyed = false, intersecting = true;
  canvas.dataset.renderer = 'canvas';
  canvas.dataset.frame = '0';
  canvas.dataset.state = state;

  const visible = () => !destroyed && !doc.hidden && intersecting && canvas.isConnected
    && canvas.getClientRects().length > 0 && width > 0 && height > 0;
  const reduced = () => Boolean(preference?.matches);
  const arc = (radius, from, to, color, line = 1, glow = 0) => {
    context.beginPath(); context.arc(0, 0, radius, from, to);
    context.strokeStyle = color; context.lineWidth = line;
    context.shadowColor = color; context.shadowBlur = glow; context.stroke(); context.shadowBlur = 0;
  };
  const line = (x1, y1, x2, y2, color, size = 1) => {
    context.beginPath(); context.moveTo(x1, y1); context.lineTo(x2, y2);
    context.strokeStyle = color; context.lineWidth = size; context.stroke();
  };
  const dot = (x, y, radius, color, glow = 0) => {
    context.beginPath(); context.arc(x, y, radius, 0, TAU);
    context.fillStyle = color; context.shadowColor = color; context.shadowBlur = glow;
    context.fill(); context.shadowBlur = 0;
  };

  function draw() {
    if (!visible()) return;
    const t = reduced() ? 0 : phase;
    const review = state === 'review';
    const primary = review ? '#ffb166' : '#68eaff';
    const accent = '#ff984f';
    const pulse = state === 'speaking' ? .5 + .5 * Math.sin(t * 6.8)
      : state === 'listening' ? .5 + .5 * Math.sin(t * 2.1) : .5;
    const radius = Math.min(width * .39, height * .405);
    const cx = width / 2, cy = height / 2;
    context.setTransform(density, 0, 0, density, 0, 0);
    context.clearRect(0, 0, width, height);

    // Faint drafting grid and fixed edge brackets anchor the moving geometry.
    const grid = Math.max(22, radius / 5);
    for (let x = cx % grid; x < width; x += grid) line(x, 0, x, height, '#3bbbd507', .6);
    for (let y = cy % grid; y < height; y += grid) line(0, y, width, y, '#3bbbd507', .6);
    const haze = context.createRadialGradient(cx, cy, radius * .25, cx, cy, radius * 1.35);
    haze.addColorStop(0, review ? '#ff9c3212' : '#16cce21c');
    haze.addColorStop(.65, review ? '#ff9c3208' : '#129bc50e'); haze.addColorStop(1, '#00000000');
    context.fillStyle = haze; context.fillRect(0, 0, width, height);
    context.save(); context.translate(cx, cy);
    const edge = radius * 1.19, corner = radius * .16;
    for (const sx of [-1, 1]) for (const sy of [-1, 1]) {
      line(sx * edge, sy * (edge - corner), sx * edge, sy * edge, '#43b7d065', 1);
      line(sx * edge, sy * edge, sx * (edge - corner), sy * edge, '#43b7d065', 1);
    }
    line(-edge, 0, -radius * 1.07, 0, '#7eeaff50');
    line(radius * 1.07, 0, edge, 0, '#7eeaff50');
    line(0, -edge, 0, -radius * 1.07, '#7eeaff50');
    line(0, radius * 1.07, 0, edge, '#7eeaff50');
    arc(radius * 1.04, 0, TAU, '#67d9ee20', .7);
    arc(radius * .91, 0, TAU, '#5ed5ef20', .6);
    arc(radius * .63, 0, TAU, '#5ed5ef25', .7);

    // Outer calibrated dial. Its major ticks stay legible while rotating slowly.
    context.save(); context.rotate(t * .028);
    for (let tick = 0; tick < 144; tick++) {
      const angle = tick / 144 * TAU;
      const major = tick % 12 === 0, middle = tick % 3 === 0;
      const inner = radius * (major ? .984 : middle ? 1.005 : 1.019);
      line(Math.cos(angle) * inner, Math.sin(angle) * inner,
        Math.cos(angle) * radius * 1.04, Math.sin(angle) * radius * 1.04,
        major ? '#c5f7ffb0' : middle ? '#5bd6ed70' : '#4d9cb038', major ? 1.5 : .8);
    }
    context.restore();

    // Mechanical rings alternate direction; gaps and secondary tracks provide depth.
    const speed = state === 'thinking' ? .43 : state === 'speaking' ? .23 : .095;
    for (let index = 0; index < 12; index++) {
      const start = index / 12 * TAU + t * speed;
      arc(radius * .96, start, start + TAU / 12 * .77,
        index === 2 || index === 8 ? accent : primary, index % 3 === 0 ? 3 : 1.4,
        index % 3 === 0 ? 6 : 0);
      arc(radius * .855, -start * .8, -start * .8 + TAU / 12 * .35, '#7ceaff65', 1);
    }
    context.save(); context.rotate(-t * speed * .7 - .22);
    for (let index = 0; index < 48; index++) {
      const start = index / 48 * TAU;
      const active = index % 12 < 8;
      arc(radius * .807, start, start + TAU / 48 * .7,
        active ? (index % 16 === 0 ? '#efffff' : primary) : '#5ed5ef20', active ? radius * .025 : 1,
        active && index % 8 === 0 ? 8 : 0);
    }
    context.restore();
    const bandRotation = t * speed * .48;
    for (const offset of [0, Math.PI]) {
      arc(radius * .73, bandRotation + offset, bandRotation + offset + Math.PI * .7, primary, 1.5, 4);
      arc(radius * .705, -bandRotation + offset + .38, -bandRotation + offset + 1.15, '#b5f6ff90', .8);
    }
    // Low-opacity scanner sweep stays behind the actual speaking display.
    const sweep = t * (state === 'thinking' ? .9 : .17);
    for (let trail = 0; trail < 12; trail++) {
      context.globalAlpha = (1 - trail / 12) * .075;
      arc(radius * (.69 - trail * .003), sweep - trail * .019, sweep + .1, primary, radius * .095);
    }
    context.globalAlpha = 1;

    // Speech motion is a presentation driven only by the parent's actual TTS events.
    // This is not a microphone waveform or a claim to measure audio amplitude.
    if (state === 'speaking') {
      for (let index = 0; index < 80; index++) {
        const angle = index / 80 * TAU;
        const envelope = .5 + .5 * Math.sin(index * 1.37 + t * 7.5) * Math.cos(index * .43 - t * 4.1);
        const inner = radius * .53, outer = inner + radius * (.022 + envelope * .085);
        line(Math.cos(angle) * inner, Math.sin(angle) * inner,
          Math.cos(angle) * outer, Math.sin(angle) * outer,
          index % 8 === 0 ? '#eeffffe0' : '#64ebff9c', 1.6);
      }
    } else if (state === 'listening') {
      for (let index = 0; index < 3; index++) {
        const progress = reduced() ? index / 3 : ((t * .22 + index / 3) % 1);
        context.globalAlpha = (1 - progress) * .34;
        arc(radius * (.48 + progress * .18), 0, TAU, primary, 1.1);
      }
      context.globalAlpha = 1;
    } else if (state === 'thinking') {
      for (let index = 0; index < 3; index++) {
        const angle = t * 1.25 + index / 3 * TAU;
        arc(radius * .565, angle - .4, angle, index === 0 ? accent : primary, 2, 7);
        dot(Math.cos(angle) * radius * .565, Math.sin(angle) * radius * .565, 2.3, '#e0fcff', 8);
      }
    } else {
      arc(radius * .565, -.35, .95, review ? accent : '#73eaff75', 1);
      arc(radius * .565, Math.PI - .35, Math.PI + .95, review ? accent : '#73eaff75', 1);
    }

    // Stable optical center with cyan-white edges, useful even with reduced motion.
    arc(radius * .445, 0, TAU, '#ccfaff95', 1.4, 3);
    arc(radius * .414, -.7 + t * .15, 1.8 + t * .15, primary, 2, 6);
    arc(radius * .414, 2.45 + t * .15, 4.9 + t * .15, primary, 2, 6);
    arc(radius * .35, 0, TAU, '#69c7dd20', .8);
    const core = context.createRadialGradient(0, 0, 0, 0, 0, radius * .34);
    core.addColorStop(0, review ? '#f6902918' : '#4edcf321'); core.addColorStop(1, '#06151b08');
    context.fillStyle = core; context.beginPath(); context.arc(0, 0, radius * .34, 0, TAU); context.fill();
    context.save(); context.rotate(-Math.PI / 4);
    const inset = radius * .128;
    context.strokeStyle = primary; context.lineWidth = 1.1;
    context.strokeRect(-inset, -inset, inset * 2, inset * 2);
    context.restore();
    line(-radius * .21, 0, -radius * .085, 0, '#c5faff90', .8);
    line(radius * .085, 0, radius * .21, 0, '#c5faff90', .8);
    line(0, -radius * .21, 0, -radius * .085, '#c5faff90', .8);
    line(0, radius * .085, 0, radius * .21, '#c5faff90', .8);
    dot(0, 0, Math.max(1.7, radius * (.012 + pulse * .006)), primary, 10);
    // Orange index markers echo the reference's warm mechanical accents.
    for (const angle of [-.54, -.39, -.24]) {
      arc(radius * 1.105, angle, angle + .065, accent, radius * .032, 3);
    }
    context.restore();
    canvas.dataset.frame = String(++frames);
    canvas.dataset.state = state;
    canvas.dataset.motion = reduced() ? 'reduced' : 'animated';
  }

  function stop() {
    if (raf) win.cancelAnimationFrame(raf);
    raf = 0; previous = 0; drawnAt = 0;
  }
  function tick(now) {
    raf = 0;
    if (!visible() || reduced()) { previous = 0; return; }
    if (!drawnAt || now - drawnAt >= 1000 / 30) {
      phase += previous ? Math.min((now - previous) / 1000, .1) : 0;
      previous = now; drawnAt = now; draw();
    }
    raf = win.requestAnimationFrame(tick);
  }
  function refresh() {
    stop();
    if (!visible()) return;
    draw();
    if (!reduced()) raf = win.requestAnimationFrame(tick);
  }
  function resize() {
    if (destroyed) return;
    const rect = canvas.getBoundingClientRect();
    width = rect.width; height = rect.height; density = Math.min(win.devicePixelRatio || 1, 2);
    if (width > 0 && height > 0) {
      const pixelWidth = Math.round(width * density), pixelHeight = Math.round(height * density);
      if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
        canvas.width = pixelWidth; canvas.height = pixelHeight;
      }
    }
    refresh();
  }
  const resized = win.ResizeObserver ? new win.ResizeObserver(resize) : null;
  resized?.observe(canvas);
  const intersection = win.IntersectionObserver ? new win.IntersectionObserver(entries => {
    intersecting = entries.some(entry => entry.isIntersecting); refresh();
  }) : null;
  intersection?.observe(canvas);
  const mutations = win.MutationObserver ? new win.MutationObserver(() => {
    const next = stage.dataset.state;
    if (STATES.has(next)) state = next;
    refresh();
  }) : null;
  mutations?.observe(stage, { attributes: true, attributeFilter: ['data-state', 'hidden'] });
  preference?.addEventListener?.('change', refresh);
  doc.addEventListener('visibilitychange', refresh);
  win.addEventListener('resize', resize, { passive: true });
  resize();

  return {
    setState(next) {
      if (destroyed) return;
      state = STATES.has(next) ? next : 'ready';
      if (stage.dataset.state !== state) stage.dataset.state = state;
      refresh();
    },
    destroy() {
      if (destroyed) return;
      stop(); destroyed = true;
      resized?.disconnect(); intersection?.disconnect(); mutations?.disconnect();
      preference?.removeEventListener?.('change', refresh);
      doc.removeEventListener('visibilitychange', refresh);
      win.removeEventListener('resize', resize);
      canvas.dataset.motion = 'stopped';
    },
  };
}
