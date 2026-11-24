// MOSS layout builder AI routes (2026-11-24). One queued ComfyUI graph per action:
//   LFM3-VL (PromptStyler Next "Layout Assist", fast graph decode) writes and describes layouts as JSON;
//   WeVisOne-VL (core "WeVisOne-VL Detect") finds boxes and lettering. An image layout boxes only what matters
//   (subject, a few objects, lettering blocks); the setting and repeated patterns go into the summary caption as
//   the background (Layout Assist's select_regions). Boxes travel as [x1, y1, x2, y2] on
//   a 0-1000 grid; the MOSS node's import converts them onto the canvas. Results are cached by content, so
//   asking again for the same image and settings answers at once. Nothing is saved to the gallery.
import crypto from 'node:crypto';
import { comfy, comfyUrl } from '../server/comfy.js';
import { cancelPrompt, promptTracker } from '../server/comfy-queue.js';
import { jobs, setTerminalJob } from '../server/jobs.js';

export const TASKS = ['image', 'describe', 'text', 'edit', 'snap', 'ocr'];
const LFM3 = /lfm3.*vl/i;
const WEVISONE = /wevisone.*\.safetensors$/i;
const MAX_IMAGE = 12 * 1024 * 1024;
const MAX_ITEMS = 24;
const CACHE_SIZE = 40;
const WEVISONE_TOKENS = { detection: 256, referring: 160, ocr: 640 };
const LETTERING_LABELS = ['title', 'text'];
const headers = { 'content-type': 'application/json' };
const defaultDelay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** What each task's graph runs, in order; the UI animates these and the socket marks the live one. */
export const STEPS = {
  image: [['list', 'Looking at the image'], ['detect', 'Finding objects and lettering'], ['describe', 'Describing every box']],
  describe: [['describe', 'Describing boxes']],
  text: [['assist', 'Planning the layout']],
  edit: [['assist', 'Editing the layout']],
  snap: [['detect', 'Finding it in the reference']],
  ocr: [['ocr', 'Reading lettering']]
};

const fail = (message, status = 400) => Object.assign(new Error(message), { status });
const text = (value, name, limit = 2000) => {
  if (value == null) return '';
  if (typeof value !== 'string') throw fail(`${name} must be text.`);
  if (value.length > limit) throw fail(`${name} is too long.`);
  return value.trim();
};

function box(value) {
  if (!Array.isArray(value) || value.length !== 4 || !value.every((v) => Number.isFinite(v))) return null;
  const [x1, y1, x2, y2] = value.map((v) => Math.max(0, Math.min(1000, Math.round(v))));
  return x2 > x1 && y2 > y1 ? [x1, y1, x2, y2] : null;
}

function cleanLayout(layout) {
  if (layout == null) return { caption: '', items: [] };
  if (typeof layout !== 'object' || Array.isArray(layout)) throw fail('layout must be an object.');
  const items = Array.isArray(layout.items) ? layout.items.slice(0, MAX_ITEMS) : [];
  return {
    caption: text(layout.caption, 'caption', 4000),
    meta: Array.isArray(layout.meta) ? layout.meta.filter((m) => typeof m === 'string').slice(0, 8).map((m) => m.slice(0, 60)) : [],
    items: items.map((item, index) => {
      const bbox = box(item?.bbox);
      if (!bbox) throw fail(`Box ${index + 1} has no usable position.`);
      return {
        label: text(item.label, 'label', 60) || 'object', caption: text(item.caption, 'box caption', 600), bbox,
        ...(item.text ? { text: text(item.text, 'box text', 300) } : {})
      };
    })
  };
}

export function parseImage(dataUrl) {
  if (typeof dataUrl !== 'string') throw fail('Add a reference image first.');
  const match = /^data:(image\/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)$/.exec(dataUrl);
  if (!match) throw fail('The reference must be a PNG, JPEG or WebP image.');
  const buffer = Buffer.from(match[2], 'base64');
  if (!buffer.length || buffer.length > MAX_IMAGE) throw fail('The reference image is too large (12 MB at most).');
  return { buffer, mime: match[1] };
}

/** Normalized request; throws a 400 error with a plain message. */
export function validateAssist(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw fail('The request must be a JSON object.');
  const task = body.task;
  if (!TASKS.includes(task)) throw fail('Unknown layout assistant task.');
  const width = Number(body.width), height = Number(body.height);
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 64 || height < 64 || width > 16384 || height > 16384) throw fail('The canvas size is not valid.');
  const out = { task, width, height, fresh: body.fresh === true };
  const needsImage = task === 'image' || task === 'snap' || task === 'ocr';
  if (needsImage || (task === 'describe' && body.image)) out.image = parseImage(body.image);
  if (task === 'image') {
    out.labels = text(body.labels, 'labels', 400).split(/[\n,]+/).map((s) => s.trim()).filter(Boolean).slice(0, 12);
    out.findText = body.findText !== false;
  }
  if (task === 'describe' || task === 'edit') out.layout = cleanLayout(body.layout);
  if (task === 'describe' && !out.layout.items.length) throw fail('Draw a box to describe first.');
  if (task === 'text' || task === 'edit') {
    out.request = text(body.request, 'request', 1200);
    if (!out.request) throw fail(task === 'text' ? 'Describe the picture you want first.' : 'Write what to change first.');
  }
  if (task === 'describe') out.request = text(body.request, 'scene note', 1200);
  if (task === 'snap') {
    out.query = text(body.query, 'query', 300);
    if (!out.query) throw fail('Give the box a caption or a name to look for.');
  }
  return out;
}

export function cacheKey(args) {
  const hash = crypto.createHash('sha256');
  const { image, fresh, ...rest } = args;
  hash.update(JSON.stringify(rest));
  if (image) hash.update(image.buffer);
  return hash.digest('hex');
}

/** Models and nodes the graphs need, read from ComfyUI's object_info. */
export async function assistModels(request = comfy) {
  const info = async (name) => (await request(`/object_info/${name}`).catch(() => ({})))?.[name];
  const [loader, assist, detect, clip] = await Promise.all(['PSNextLoadUpscaler', 'PSNextLayoutAssist', 'WeVisOneDetect', 'CLIPLoader'].map(info));
  const options = (node, key) => {
    const definition = node?.input?.required?.[key];
    return Array.isArray(definition?.[0]) ? definition[0] : definition?.[1]?.options || [];
  };
  return {
    lfm3: assist ? options(loader, 'model_name').find((name) => LFM3.test(name)) || '' : '',
    wevisone: detect ? options(clip, 'clip_name').find((name) => WEVISONE.test(name)) || '' : ''
  };
}

const json = (value) => JSON.stringify(value);

/** ComfyUI API graph for one task. `name` is the uploaded image's ComfyUI input name. */
export function assistGraph(args, models, name = '') {
  const { task, width, height } = args;
  const graph = {};
  const image = name ? ['img', 0] : null;
  if (name) graph.img = { class_type: 'LoadImage', inputs: { image: name } };
  const lfm3 = () => { graph.load = { class_type: 'PSNextLoadUpscaler', inputs: { model_name: models.lfm3 } }; return ['load', 0]; };
  const wevisone = () => { graph.clip = { class_type: 'CLIPLoader', inputs: { clip_name: models.wevisone, type: 'stable_diffusion', device: 'default' } }; return ['clip', 0]; };
  // Answers run ~20 tokens per box or word. The caps stop a rare repetition loop (seen once: 4096 tokens) and, for
  // detection, the long tail of a label repeated all over (45 roses): the labels come most important first.
  const detect = (id, task, query) => { graph[id] = { class_type: 'WeVisOneDetect', inputs: { clip: ['clip', 0], image, task, query, individual_masks: false, max_length: WEVISONE_TOKENS[task] } }; };
  const assist = (id, inputs) => { graph[id] = { class_type: 'PSNextLayoutAssist', inputs: { upscaler: ['load', 0], request: '', seed: args.seed ?? 0, temperature: args.temperature ?? 0, ...inputs } }; };
  const preview = (from, inspection) => { graph.preview = { class_type: 'PSNextPreviewPrompt', inputs: { base_prompt: from, inspection } }; };
  if (task === 'snap' || task === 'ocr') {
    wevisone();
    detect(task === 'ocr' ? 'ocr' : 'detect', task === 'ocr' ? 'ocr' : 'referring', task === 'ocr' ? '' : args.query);
    const id = task === 'ocr' ? 'ocr' : 'detect';
    preview([id, 3], [id, 3]);
    return graph;
  }
  lfm3();
  if (task === 'image') {
    if (!models.wevisone) {
      assist('describe', { task: 'image_layout', image, layout: json({ width, height }) });
    } else {
      // One detector call finds the objects and the lettering blocks: the list adds "title"/"text" to its labels
      // when it sees lettering, and LFM3 reads the words while it captions (no OCR pass, one model swap less).
      wevisone();
      let query = [...args.labels, ...(args.labels.length && args.findText ? LETTERING_LABELS : [])].join('\n');
      let scene = {};
      if (!query) { assist('list', { task: 'list_objects', image }); query = ['list', 1]; scene = { scene: ['list', 0] }; }
      detect('detect', 'detection', query);
      assist('describe', { task: 'describe_regions', image, objects: ['detect', 1], ...scene, ...(args.findText ? {} : { read_words: false }), layout: json({ width, height }) });
    }
    preview(['describe', 0], ['describe', 2]);
    return graph;
  }
  if (task === 'describe') {
    assist('describe', { task: 'describe_regions', ...(image ? { image } : {}), request: args.request || args.layout.caption, layout: json({ ...args.layout, width, height }) });
    preview(['describe', 0], ['describe', 2]);
    return graph;
  }
  assist('assist', { task: task === 'text' ? 'text_layout' : 'edit_layout', request: args.request, layout: json({ ...(args.layout || {}), width, height }) });
  preview(['assist', 0], ['assist', 2]);
  return graph;
}

/** Finished steps when `step` goes live: moving forward finishes every earlier step (a skipped one too); a
 *  step that runs again late (OCR, asked for lazily by describe) is live, not finished, until the next one. */
export function stepsDone(progress, step) {
  if (!progress.started) return [];
  const done = new Set(progress.done);
  if (step > progress.step) for (let index = 0; index < step; index += 1) done.add(index);
  done.delete(step);
  return [...done].sort((a, b) => a - b);
}

/** WeVisOne's raw answer ("<ref>dog</ref><box><x1><y1><x2><y2>,...</box>") as xyxy boxes on 0-1000. */
export function parseGrounding(raw) {
  const boxes = [];
  for (const match of String(raw || '').matchAll(/<ref>(.*?)<\/ref>\s*<box>(.*?)(?:<\/box>|(?=<ref>)|$)/gs)) {
    const label = match[1].trim() || 'object';
    for (const segment of match[2].split(',')) {
      const values = [...segment.matchAll(/<(\d{1,4})>/g)].map((m) => Number(m[1]));
      for (let i = 0; i + 3 < values.length; i += 4) {
        const b = box(values.slice(i, i + 4));
        if (b) boxes.push({ label, bbox: b });
      }
    }
  }
  return boxes;
}

function watchSteps(id, graphStepIds, onStep) {
  let socket;
  try { socket = new WebSocket(`${comfyUrl.replace(/^http/i, 'ws')}/ws?clientId=${encodeURIComponent(id)}`); } catch { return null; }
  socket.addEventListener('message', (event) => {
    if (typeof event.data !== 'string') return;
    try {
      const message = JSON.parse(event.data);
      const data = message.data || {};
      if (message.type === 'executing' && graphStepIds.includes(data.node)) onStep({ node: data.node });
      if (message.type === 'progress' && graphStepIds.includes(data.node)) onStep({ node: data.node, tokens: Number(data.value) || 0 });
    } catch { /* not ours */ }
  });
  socket.addEventListener('error', () => {});
  return socket;
}

function waitForOpen(socket) {
  if (!socket || socket.readyState === WebSocket.OPEN) return Promise.resolve();
  return new Promise((resolve) => {
    socket.addEventListener('open', () => resolve(), { once: true });
    socket.addEventListener('error', () => resolve(), { once: true });
    setTimeout(resolve, 800);
  });
}

async function defaultUpload(image) {
  const { uploadBufferToComfy } = await import('../server/reference-assets.js');
  return (await uploadBufferToComfy({ buffer: image.buffer, mime: image.mime, name: 'layout-reference' })).comfyName;
}

export function createLayoutAssist({
  jobMap = jobs, terminal = setTerminalJob, request = comfy, cancel = cancelPrompt, tracker = promptTracker,
  uuid = crypto.randomUUID, delay = defaultDelay, upload = defaultUpload, models = () => assistModels(request),
  watch = watchSteps, cache = new Map()
} = {}) {
  const remember = (key, value) => {
    cache.delete(key); cache.set(key, value);
    while (cache.size > CACHE_SIZE) cache.delete(cache.keys().next().value);
  };

  async function run(id, args, key) {
    let promptId = '', socket = null;
    const started = Date.now();
    const patch = (change) => { const job = jobMap.get(id); if (job && job.status !== 'canceling' && job.status !== 'canceled') jobMap.set(id, { ...job, ...change }); };
    const canceled = () => { const job = jobMap.get(id); return !job || job.status === 'canceling' || job.status === 'canceled'; };
    try {
      const found = await models();
      if (!found.lfm3 && !['snap', 'ocr'].includes(args.task)) throw fail('Restart ComfyUI so the LFM3 layout assistant loads (PromptStyler Next, LFM3-VL file).', 503);
      if (!found.wevisone && ['snap', 'ocr'].includes(args.task)) throw fail('Put wevisone_vl_2b_int8_convrot.safetensors in models/text_encoders and restart ComfyUI.', 503);
      const name = args.image ? await upload(args.image) : '';
      const graph = assistGraph(args, found, name);
      const steps = STEPS[args.task].filter(([node]) => graph[node]);
      patch({ progress: { phase: steps[0]?.[1] || 'Working…', steps: steps.map(([, label]) => label), step: 0, done: [], tokens: 0 } });
      // ComfyUI picks its own order among ready nodes: track the live step and the finished ones by node.
      socket = watch(id, steps.map(([node]) => node), ({ node, tokens }) => {
        const step = steps.findIndex(([n]) => n === node);
        const job = jobMap.get(id);
        if (step < 0 || !job?.progress) return;
        const { progress } = job;
        if (tokens != null) { if (step === progress.step) patch({ progress: { ...progress, tokens } }); return; }
        patch({ progress: { ...progress, step, started: true, done: stepsDone(progress, step), phase: steps[step][1], tokens: 0 } });
      });
      await waitForOpen(socket);
      if (canceled()) { terminal(id, { status: 'canceled' }); return; }
      const queued = await request('/prompt', { method: 'POST', headers, body: JSON.stringify({ prompt: graph, client_id: id }) });
      promptId = String(queued?.prompt_id || '');
      if (!promptId) throw new Error('ComfyUI did not return a prompt ID.');
      patch({ status: 'running', promptId });
      const watcher = tracker(promptId, { request });
      while (true) {
        if (canceled()) { await cancel(promptId).catch(() => null); terminal(id, { status: 'canceled', promptId }); return; }
        const checked = await watcher.check();
        if (checked.state === 'done') {
          const entry = checked.entry;
          if (entry?.status?.status_str === 'error') {
            const failure = entry.status.messages?.find(([type]) => type === 'execution_error')?.[1];
            throw new Error(failure?.exception_message?.trim() || 'The layout assistant failed.');
          }
          const out = entry?.outputs?.preview;
          const answer = out?.text?.[0];
          if (typeof answer !== 'string') throw new Error('ComfyUI returned no layout.');
          let result;
          if (args.task === 'snap' || args.task === 'ocr') {
            result = { boxes: parseGrounding(answer) };
          } else {
            let inspection = {};
            try { inspection = JSON.parse(out?.inspection?.[0] || '{}'); } catch { /* optional */ }
            result = { layout: JSON.parse(answer), stats: { tokensPerSecond: inspection.tokens_per_second ?? null, tokens: inspection.generated_tokens ?? null, engine: inspection.engine || null } };
          }
          result.seconds = Math.round((Date.now() - started) / 100) / 10;
          if (!args.fresh) remember(key, result);
          terminal(id, { status: 'done', promptId, result });
          return;
        }
        await delay(checked.state === 'reconnecting' ? checked.delayMs : 100);
      }
    } catch (error) {
      if (canceled()) {
        if (promptId) await cancel(promptId).catch(() => null);
        terminal(id, { status: 'canceled', promptId });
      } else {
        terminal(id, { status: 'error', promptId, error: error?.message || 'The layout assistant failed.', ...(error?.status === 503 ? { restart: true } : {}) });
      }
    } finally {
      try { socket?.close(); } catch { /* closed */ }
    }
  }

  return function start(body) {
    const args = validateAssist(body);
    if (args.fresh) { args.seed = crypto.randomInt(0, 2 ** 31); args.temperature = 0.5; }
    const key = cacheKey({ ...args, fresh: false, seed: undefined, temperature: undefined });
    const id = uuid();
    if (!args.fresh && cache.has(key)) {
      const result = { ...cache.get(key), cached: true };
      remember(key, cache.get(key));
      jobMap.set(id, { status: 'done', kind: 'layout-assist', startedAt: Date.now(), result });
      return { jobId: id, cached: true };
    }
    jobMap.set(id, { status: 'queued', kind: 'layout-assist', startedAt: Date.now(), progress: { phase: 'Starting…', steps: STEPS[args.task].map(([, l]) => l), step: 0 } });
    setTimeout(() => { void run(id, args, key); }, 0);
    return { jobId: id };
  };
}

export function mountLayoutAssistRoutes(app, { start = createLayoutAssist(), request = comfy } = {}) {
  app.post('/api/moss-layout-ai', (req, res) => {
    res.set('Cache-Control', 'no-store');
    try { res.json(start(req.body)); }
    catch (error) { res.status(error.status || 400).json({ error: error.message }); }
  });
  app.get('/api/moss-layout-ai/status', async (_req, res) => {
    res.set('Cache-Control', 'no-store');
    try {
      const found = await assistModels(request);
      res.json({ lfm3: Boolean(found.lfm3), wevisone: Boolean(found.wevisone) });
    } catch { res.json({ lfm3: false, wevisone: false, offline: true }); }
  });
}
