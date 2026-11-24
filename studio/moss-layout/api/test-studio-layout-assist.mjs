import test from 'node:test';
import assert from 'node:assert/strict';
import { validateAssist, assistGraph, parseGrounding, createLayoutAssist, cacheKey, STEPS } from './studio-layout-assist.mjs';

const PNG = 'data:image/png;base64,' + Buffer.from('fake png bytes').toString('base64');
const models = { lfm3: 'lfm3-vl-2b-heretic-int8-convrot.safetensors', wevisone: 'wevisone_vl_2b_int8_convrot.safetensors' };
const layout = { caption: 'A knight.', items: [{ label: 'knight', caption: '', bbox: [268, 148, 687, 964] }] };

test('validation explains missing pieces in plain words', () => {
  assert.throws(() => validateAssist({ task: 'image', width: 896, height: 1152 }), /reference image/);
  assert.throws(() => validateAssist({ task: 'text', width: 896, height: 1152 }), /Describe the picture/);
  assert.throws(() => validateAssist({ task: 'describe', width: 896, height: 1152, layout: { items: [] } }), /Draw a box/);
  assert.throws(() => validateAssist({ task: 'describe', width: 896, height: 1152, layout: { items: [{ bbox: [5, 5, 5, 9] }] } }), /Box 1/);
  assert.throws(() => validateAssist({ task: 'nope', width: 896, height: 1152 }), /Unknown/);
  const args = validateAssist({ task: 'image', width: 896, height: 1152, image: PNG, labels: 'dog, cat\nhammer' });
  assert.deepEqual(args.labels, ['dog', 'cat', 'hammer']);
  assert.equal(args.findText, true);
});

test('image graph chains LFM3 objects -> WeVisOne -> LFM3 descriptions in one prompt', () => {
  const args = validateAssist({ task: 'image', width: 896, height: 1152, image: PNG });
  const graph = assistGraph(args, models, 'ref.png');
  assert.deepEqual(graph.detect.inputs.query, ['list', 1]);
  assert.equal(graph.list.inputs.task, 'list_objects');
  assert.deepEqual(graph.describe.inputs.objects, ['detect', 1]);
  assert.deepEqual(graph.describe.inputs.words, ['ocr', 1]);
  assert.deepEqual(graph.ocr.inputs.query, ['list', 1], 'OCR waits for the LFM3 list, so both WeVisOne nodes run back to back');
  assert.deepEqual(graph.preview.inputs, { base_prompt: ['describe', 0], inspection: ['describe', 2] });
  const labelled = assistGraph(validateAssist({ task: 'image', width: 896, height: 1152, image: PNG, labels: 'dog', findText: false }), models, 'ref.png');
  assert.equal(labelled.list, undefined);
  assert.equal(labelled.ocr, undefined);
  assert.equal(labelled.detect.inputs.query, 'dog');
  const noDetector = assistGraph(args, { ...models, wevisone: '' }, 'ref.png');
  assert.equal(noDetector.describe.inputs.task, 'image_layout');
});

test('text, edit, describe and snap graphs', () => {
  const text = assistGraph(validateAssist({ task: 'text', width: 1024, height: 1024, request: 'a fox' }), models);
  assert.equal(text.assist.inputs.task, 'text_layout');
  assert.equal(JSON.parse(text.assist.inputs.layout).width, 1024);
  const edit = assistGraph(validateAssist({ task: 'edit', width: 1024, height: 1024, request: 'bigger', layout }), models);
  assert.equal(JSON.parse(edit.assist.inputs.layout).items[0].label, 'knight');
  const describe = assistGraph(validateAssist({ task: 'describe', width: 1024, height: 1024, layout }), models);
  assert.equal(describe.img, undefined);
  assert.equal(describe.describe.inputs.request, 'A knight.');
  const snap = assistGraph(validateAssist({ task: 'snap', width: 1024, height: 1024, image: PNG, query: 'the lantern' }), models, 'ref.png');
  assert.equal(snap.detect.inputs.task, 'referring');
  assert.equal(snap.load, undefined);
});

test('WeVisOne answers become xyxy boxes', () => {
  const raw = '<ref>tree</ref><box><0><0><71><641>,<58><106><212><743></box>, <ref>THE</ref><box><468><48><532><72></box>';
  assert.deepEqual(parseGrounding(raw), [
    { label: 'tree', bbox: [0, 0, 71, 641] }, { label: 'tree', bbox: [58, 106, 212, 743] }, { label: 'THE', bbox: [468, 48, 532, 72] }]);
  assert.deepEqual(parseGrounding('None'), []);
});

function harness(answers) {
  const jobMap = new Map(); const queued = [];
  const start = createLayoutAssist({
    jobMap, terminal: (id, value) => jobMap.set(id, { ...jobMap.get(id), ...value }), uuid: (() => { let n = 0; return () => `job${++n}`; })(),
    request: async (path, options) => { queued.push(JSON.parse(options.body).prompt); return { prompt_id: 'p1' }; },
    tracker: () => ({ check: async () => answers.shift() }), delay: async () => {}, upload: async () => 'ref.png',
    models: async () => models, watch: () => null, cancel: async () => {}
  });
  return { start, jobMap, queued };
}
const settle = () => new Promise((resolve) => setTimeout(resolve, 5));

test('a finished job returns the layout and the same request is answered from cache', async () => {
  const done = { state: 'done', entry: { status: { status_str: 'success' }, outputs: { preview: { text: ['{"caption":"A fox.","items":[]}'], inspection: ['{"tokens_per_second":61.2,"generated_tokens":80,"engine":"graph"}'] } } } };
  const { start, jobMap, queued } = harness([{ state: 'waiting' }, done]);
  const body = { task: 'text', width: 1024, height: 1024, request: 'a fox' };
  const first = start(body);
  await settle();
  const job = jobMap.get(first.jobId);
  assert.equal(job.status, 'done');
  assert.equal(job.result.layout.caption, 'A fox.');
  assert.equal(job.result.stats.tokensPerSecond, 61.2);
  const again = start(body);
  assert.equal(again.cached, true);
  assert.equal(jobMap.get(again.jobId).result.cached, true);
  assert.equal(queued.length, 1);
});

test('a node error reaches the user; fresh runs skip the cache and sample', async () => {
  const failed = { state: 'done', entry: { status: { status_str: 'error', messages: [['execution_error', { exception_message: 'Draw or detect at least one box to describe' }]] } } };
  const { start, jobMap, queued } = harness([failed]);
  const { jobId } = start({ task: 'text', width: 1024, height: 1024, request: 'a fox', fresh: true });
  await settle();
  assert.equal(jobMap.get(jobId).status, 'error');
  assert.match(jobMap.get(jobId).error, /at least one box/);
  assert.equal(queued[0].assist.inputs.temperature, 0.5);
});

test('cache keys ignore freshness but not the image or settings', () => {
  const a = validateAssist({ task: 'image', width: 896, height: 1152, image: PNG });
  const b = validateAssist({ task: 'image', width: 896, height: 1152, image: PNG, findText: false });
  assert.notEqual(cacheKey(a), cacheKey(b));
  assert.equal(cacheKey(a), cacheKey({ ...a, fresh: true }));
  assert.ok(STEPS.image.length === 4);
});
