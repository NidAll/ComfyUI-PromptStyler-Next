import test from 'node:test';
import assert from 'node:assert/strict';
import { layoutRequest, mountLayoutRoutes } from './studio-layout-builder.mjs';
import { deflateSync } from 'node:zlib';
import { layoutInfo, studioSize, findLayout, inferSourceSize, normalizeLayout, gridRects, keepAspect, pngTexts,
  foreignKind, regionsToGrid, gridRect, overlap, keepLocked, carryColours, ocrLines, toIdeogram, fitRect, pastedFile } from './studio-layout-ui.mjs';

/** A minimal Express stand-in: records the route and replays requests through it. */
function fakeApp() {
  const routes = {};
  return { post: (path, handler) => { routes[path] = handler; }, routes };
}
function run(handler, operation, body) {
  return new Promise((resolve) => {
    const res = { code: 200, headers: {}, set(key, value) { this.headers[key] = value; return this; }, status(code) { this.code = code; return this; }, json(data) { resolve({ code: this.code, data, headers: this.headers }); } };
    void handler({ params: { operation }, body }, res);
  });
}

test('only node fields of the right type are forwarded; import_json never is', () => {
  const out = layoutRequest('serialize', { width: 896, height: 1152, summary_caption: 'A cup.', layers_data: '[]', import_json: '{"x":1}', meta: 'poster', extra: 1 });
  assert.deepEqual(out, { width: 896, height: 1152, summary_caption: 'A cup.', meta: 'poster', layers_data: '[]' });
  assert.deepEqual(layoutRequest('import', { prompt: 'x', width: 1024, height: 1024, summary_caption: 'no' }), { prompt: 'x', width: 1024, height: 1024 });
  assert.throws(() => layoutRequest('serialize', { width: '1024' }), /integer/);
  assert.throws(() => layoutRequest('serialize', { meta: ['a'] }), /string/);
  assert.throws(() => layoutRequest('delete', {}), /Unknown/);
  assert.throws(() => layoutRequest('import', []), /JSON object/);
  assert.throws(() => layoutRequest('import', { prompt: 'x'.repeat(400_001) }), /too large/);
});

test('route proxies to the MOSS node and explains a missing node or offline ComfyUI', async () => {
  const calls = [];
  const replies = [
    { ok: true, status: 200, json: async () => ({ prompt: '{"summary":{}}', warnings: [] }) },
    { ok: false, status: 400, json: async () => ({ error: 'Summary caption is required' }) },
    { ok: false, status: 404, json: async () => ({}) }
  ];
  const app = fakeApp();
  mountLayoutRoutes(app, { assist: false, base: () => 'http://127.0.0.1:9999', fetcher: async (url, options) => { calls.push([url, JSON.parse(options.body)]); const next = replies.shift(); if (!next) throw new TypeError('fetch failed'); return next; } });
  const handler = app.routes['/api/moss-layout/:operation'];
  let reply = await run(handler, 'serialize', { width: 1024, height: 1024, layers_data: '[]' });
  assert.equal(reply.code, 200);
  assert.equal(reply.headers['Cache-Control'], 'no-store');
  assert.deepEqual(calls[0], ['http://127.0.0.1:9999/moss_prompt_builder/serialize', { width: 1024, height: 1024, layers_data: '[]' }]);
  reply = await run(handler, 'serialize', { width: 1024, height: 1024 });
  assert.deepEqual([reply.code, reply.data.error], [400, 'Summary caption is required']);
  reply = await run(handler, 'import', { prompt: 'x', width: 1024, height: 1024 });
  assert.deepEqual([reply.code, reply.data.restart], [503, true]);
  reply = await run(handler, 'import', { prompt: 'x', width: 1024, height: 1024 });
  assert.equal(reply.code, 503);
  assert.match(reply.data.error, /not reachable/);
  reply = await run(handler, 'nope', {});
  assert.equal(reply.code, 404);
  assert.equal(calls.length, 4);
});

test('layout prompts are recognised; captions and other JSON are not', () => {
  const layout = JSON.stringify({ summary: { caption: 'x' }, items: [{ label: 'text', caption: 'y', text: 'HI', bbox: [0, 0, 1, 1] }, { label: 'object', caption: 'z', bbox: [0, 0, 1, 1] }], bbox_coord_space: 'abs_centralized', bbox_format: 'yxyx' });
  assert.deepEqual(layoutInfo(layout), { items: 2, text: 1 });
  assert.equal(layoutInfo('A red fox in the snow.'), null);
  assert.equal(layoutInfo('{"caption":"x"}'), null);
  assert.equal(layoutInfo('{broken'), null);
});

test('the generation size comes from the composer draft, with a safe fallback', () => {
  const store = {};
  globalThis.localStorage = { getItem: (key) => store[key] ?? null, setItem: (key, value) => { store[key] = value; } };
  try {
    assert.deepEqual(studioSize(), { width: 1024, height: 1024 });
    store['heiss-ui-draft'] = JSON.stringify({ prompt: 'x', width: 896, height: 1152 });
    assert.deepEqual(studioSize(), { width: 896, height: 1152 });
    store['heiss-ui-draft'] = '{oops';
    assert.deepEqual(studioSize(), { width: 1024, height: 1024 });
  } finally { delete globalThis.localStorage; }
});

const sample = (items, extra = {}) => JSON.stringify({ summary: { caption: 'x' }, items, bbox_coord_space: 'abs_centralized', bbox_format: 'yxyx', ...extra });

test('a layout that reaches past the canvas gets a same-shaped source size; one that fits does not', () => {
  // Made at 1024 x 1024: x reaches 512, past the 896-wide canvas.
  const wide = sample([{ label: 'object', caption: 'a', bbox: [-512, -512, 512, 512] }]);
  const size = inferSourceSize(wide, { width: 896, height: 1152 });
  assert.equal(size.width % 16, 0); assert.equal(size.height % 16, 0);
  assert.ok(size.width >= 1024 && Math.abs(size.width / size.height - 896 / 1152) < 0.02, JSON.stringify(size));
  assert.equal(inferSourceSize(sample([{ label: 'object', caption: 'a', bbox: [-576, -448, 576, 448] }]), { width: 896, height: 1152 }), null);
  assert.equal(inferSourceSize(JSON.stringify({ items: [{ bbox: [0, 0, 2000, 2000] }], bbox_coord_space: 'abs', bbox_format: 'xyxy', width: 2000, height: 2000 }), { width: 896, height: 1152 }), null);
  assert.equal(inferSourceSize('{broken', { width: 896, height: 1152 }), null);
});

test('editor extras from other tools are dropped; their size and locks are kept', () => {
  const bbox = sample([{ label: 'object', caption: 'back', bbox: [-100, -100, 100, 100], color: '#fff', locked: true, aspect_locked: false },
    { label: 'text', caption: 'front', text: 'HI', bbox: [0, 0, 50, 50], color: '#000', locked: false }], { width: 1080, height: 1920 });
  const out = normalizeLayout(bbox);
  assert.deepEqual(out.size, { width: 1088, height: 1920 });
  assert.deepEqual(out.locks, [true, false]);
  const clean = JSON.parse(out.text);
  assert.equal('width' in clean, false);
  assert.deepEqual(Object.keys(clean.items[0]).sort(), ['bbox', 'caption', 'label']);
  const plainLayout = sample([{ label: 'object', caption: 'a', bbox: [0, 0, 1, 1] }]);
  assert.equal(normalizeLayout(plainLayout).text, plainLayout);
});

test('layouts are found inside ComfyUI graphs and project files', () => {
  const layout = sample([{ label: 'object', caption: 'a', bbox: [0, 0, 10, 10] }]);
  const graph = JSON.stringify({ 3: { class_type: 'KSampler', inputs: { seed: 1 } }, 6: { class_type: 'CLIPTextEncode', inputs: { text: layout } } });
  assert.equal(findLayout(graph), layout);
  const project = JSON.stringify({ format: 'bbox-studio-project', layout: JSON.parse(layout) });
  assert.deepEqual(JSON.parse(findLayout(project)), JSON.parse(layout));
  assert.equal(findLayout('A plain caption.'), null);
  assert.equal(findLayout(JSON.stringify({ 1: { inputs: { text: 'no layout' } } })), null);
});

test('placement grids tile the canvas with even gutters', () => {
  const [a, b] = gridRects(2, 1, [[0, 0], [1, 0]], 0.02, 0.01);
  assert.ok(Math.abs(a.x - 0.02) < 1e-9 && Math.abs(b.x + b.w - 0.98) < 1e-9);
  assert.ok(Math.abs(b.x - (a.x + a.w) - 0.02) < 1e-9);
  assert.ok(Math.abs(a.y - 0.01) < 1e-9 && Math.abs(a.h - 0.98) < 1e-9);
  const quad = gridRects(2, 2, [[1, 1]]);
  assert.deepEqual(quad, [{ x: 0.5, y: 0.5, w: 0.5, h: 0.5 }]);
});

test('Shift resize keeps proportions and stays on the canvas', () => {
  const W = 1000, H = 1000;
  const start = { x: 0.1, y: 0.1, w: 0.2, h: 0.1 }; // 2:1
  let r = keepAspect('se', start, { left: 0.1, top: 0.1, right: 0.5, bottom: 0.25 }, 2, false, W, H);
  assert.ok(Math.abs((r.right - r.left) / (r.bottom - r.top) - 2) < 1e-9);
  assert.ok(Math.abs(r.left - 0.1) < 1e-9 && Math.abs(r.top - 0.1) < 1e-9);
  r = keepAspect('se', start, { left: 0.1, top: 0.1, right: 3, bottom: 3 }, 2, false, W, H);
  assert.ok(r.right <= 1 + 1e-9 && r.bottom <= 1 + 1e-9);
  r = keepAspect('e', start, { left: 0.1, top: 0.1, right: 0.5, bottom: 0.2 }, 2, false, W, H);
  assert.ok(Math.abs((r.top + r.bottom) / 2 - 0.15) < 1e-9, 'an edge handle keeps the other axis centred');
  r = keepAspect('es', { x: 0.5, y: 0.5, w: 0, h: 0 }, { left: 0.5, top: 0.5, right: 0.7, bottom: 0.6 }, 1, false, W, H);
  assert.ok(Math.abs((r.right - r.left) - (r.bottom - r.top)) < 1e-9, 'drawing with Shift makes a square');
});

test('PNG text chunks (tEXt, zTXt, iTXt) are read', async () => {
  const crcTable = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc = (buf) => { let c = 0xffffffff; for (const b of buf) c = crcTable[(c ^ b) & 255] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const chunk = (type, data) => { const out = Buffer.alloc(12 + data.length); out.writeUInt32BE(data.length, 0); out.write(type, 4, 'latin1'); data.copy(out, 8); out.writeUInt32BE(crc(out.subarray(4, 8 + data.length)), 8 + data.length); return out; };
  const png = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', Buffer.alloc(13)),
    chunk('tEXt', Buffer.concat([Buffer.from('moss\0'), Buffer.from('{"a":1}')])),
    chunk('zTXt', Buffer.concat([Buffer.from('prompt\0\0'), deflateSync(Buffer.from('{"b":2}'))])),
    chunk('iTXt', Buffer.concat([Buffer.from('workflow\0\x01\0en\0\0'), deflateSync(Buffer.from('{"c":"é"}'))])),
    chunk('iTXt', Buffer.concat([Buffer.from('plain\0\0\0\0\0'), Buffer.from('{"d":4}')])),
    chunk('IEND', Buffer.alloc(0))]);
  assert.deepEqual(await pngTexts(png.buffer.slice(png.byteOffset, png.byteOffset + png.length)), ['{"a":1}', '{"b":2}', '{"c":"é"}', '{"d":4}']);
  assert.deepEqual(await pngTexts(new ArrayBuffer(4)), []);
});

const ideogram = { high_level_description: 'A poster.', compositional_deconstruction: { background: 'night sky', elements: [{ type: 'text', bbox: [50, 100, 150, 900], text: 'HELLO', desc: 'neon' }] } };
const assistant = { grid: 'xyxy-1000', caption: 'A dog.', items: [{ label: 'dog', caption: 'a dog', bbox: [100, 200, 600, 900] }] };

test('Ideogram 4 captions and assistant layouts are found and never re-scaled as MOSS boxes', () => {
  assert.equal(foreignKind(ideogram), 'ideogram');
  assert.equal(foreignKind(assistant), 'assistant');
  assert.equal(foreignKind({ items: [] }), null);
  assert.equal(foreignKind({ compositional_deconstruction: [] }), null);
  assert.deepEqual(JSON.parse(findLayout(JSON.stringify(ideogram))), ideogram);
  assert.deepEqual(JSON.parse(findLayout(JSON.stringify({ 7: { inputs: { text: JSON.stringify(assistant) } } }))), assistant);
  assert.equal(layoutInfo(JSON.stringify(ideogram)), null);
  assert.equal(inferSourceSize(JSON.stringify(assistant), { width: 896, height: 1152 }), null);
});

const region = (id, x, y, w, h, extra = {}) => ({ id, kind: 'object', x, y, w, h, text: '', description: '', colors: [], tags: [], ...extra });

test('editor boxes go to the 0-1000 grid back to front and come back', () => {
  const items = regionsToGrid([region('front', 0.1, 0.2, 0.3, 0.4, { kind: 'text', text: ' HI ', description: 'bold' }), region('back', 0, 0, 1, 1)]);
  assert.deepEqual(items, [{ label: 'object', caption: '', bbox: [0, 0, 1000, 1000] }, { label: 'text', caption: 'bold', bbox: [100, 200, 400, 600], text: 'HI' }]);
  const rect = gridRect([400, 600, 100, 200]);
  assert.deepEqual(Object.values(rect).map((v) => Math.round(v * 1000)), [100, 200, 300, 400]);
  assert.ok(gridRect([500, 500, 500, 500]).w > 0);
  assert.equal(overlap(region('a', 0, 0, 0.5, 0.5), region('b', 0.5, 0.5, 0.5, 0.5)), 0);
  assert.equal(overlap(region('a', 0, 0, 0.5, 0.5), region('b', 0, 0, 0.5, 0.5)), 1);
});

test('locked boxes survive an AI rewrite; matching boxes keep their colours', () => {
  const lock = region('lock', 0.1, 0.1, 0.4, 0.4, { locked: true });
  const far = region('far', 0.6, 0.6, 0.3, 0.3, { locked: true });
  const next = [region('n1', 0.12, 0.1, 0.4, 0.4), region('n2', 0, 0.6, 0.3, 0.3)];
  assert.deepEqual(keepLocked([lock, far, region('free', 0, 0, 1, 1)], next).map((r) => r.id), ['far', 'lock', 'n2']);
  const painted = carryColours([region('old', 0.1, 0.1, 0.4, 0.4, { colors: ['#ff0000'] })], next);
  assert.deepEqual(painted.map((r) => r.colors), [['#ff0000'], []]);
});

test('OCR words merge into lines in reading order', () => {
  const words = [{ label: 'BEARER', bbox: [530, 76, 701, 112] }, { label: 'THE', bbox: [468, 48, 532, 72] }, { label: 'LANTERN', bbox: [294, 73, 520, 113] }, { label: '', bbox: [0, 0, 5, 5] }];
  const lines = ocrLines(words, { width: 896, height: 1152 });
  assert.deepEqual(lines.map((line) => line.text), ['THE', 'LANTERN BEARER']);
  assert.deepEqual(lines[1].bbox, [294, 73, 701, 113]);
});

test('Copy as Ideogram 4 writes front-first [ymin, xmin, ymax, xmax] elements', () => {
  const doc = toIdeogram({ caption: ' A shop. ', meta: ['poster', 'flat'], palette: ['#ff8800', 'warm'], regions: [
    region('t', 0.1, 0.05, 0.8, 0.1, { kind: 'text', text: 'OPEN', description: 'red serif', colors: ['#cc0000'] }),
    region('c', 0.2, 0.3, 0.3, 0.6, { kind: 'character', description: 'a clerk' })] });
  assert.deepEqual(doc, { high_level_description: 'A shop.',
    style_description: { aesthetics: 'poster, flat', lighting: '', medium: '', art_style: '', color_palette: ['#FF8800'] },
    compositional_deconstruction: { background: '', elements: [
      { type: 'text', bbox: [50, 100, 150, 900], text: 'OPEN', desc: 'red serif', color_palette: ['#CC0000'] },
      { type: 'obj', bbox: [300, 200, 900, 500], desc: 'a clerk' }] } });
  assert.equal(foreignKind(doc), 'ideogram');
  assert.equal(toIdeogram({ caption: '', meta: [], palette: [], regions: [] }).style_description, undefined);
});

test('the reference is drawn for the assistant the way the board shows it', () => {
  const size = { width: 896, height: 1152 }, out = { width: 896, height: 1152 }, square = { width: 1000, height: 1000 };
  assert.deepEqual(fitRect(square, size, 'cover', out), { x: -128, y: 0, w: 1152, h: 1152 });
  assert.deepEqual(fitRect(square, size, 'contain', out), { x: 0, y: 128, w: 896, h: 896 });
  assert.deepEqual(fitRect(square, size, 'fill', out), { x: 0, y: 0, w: 896, h: 1152 });
  assert.deepEqual(fitRect(square, size, 'actual', { width: 448, height: 576 }), { x: -26, y: 38, w: 500, h: 500 });
});

test('a pasted clipboard image becomes a named reference file of the same type', async () => {
  const png = pastedFile(new Blob([new Uint8Array([1, 2, 3])], { type: 'image/png' }));
  assert.equal(png.name, 'Pasted image.png');
  assert.equal(png.type, 'image/png');
  assert.deepEqual([...new Uint8Array(await png.arrayBuffer())], [1, 2, 3]);
  assert.equal(pastedFile(new Blob([], { type: 'image/jpeg' })).name, 'Pasted image.jpg');
  assert.equal(pastedFile(new Blob([])).type, 'image/png');
});
