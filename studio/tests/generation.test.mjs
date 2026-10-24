import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import test from 'node:test';
import { injectPromptStyler } from '../graph.mjs';
import { studioModelProfile } from '../model-profile.mjs';
import { createManagedPromptStyler } from '../server.mjs';

const recipe = { schema_version: 1, model: 'anima-turbo', styles: [{ id: 'cinema.noir', intensity: 0.75 }], conflict_policy: 'last_wins', locked_axes: [] };

test('native generated caption is linked into one shared-engine node', () => {
  const graph = { '4': { class_type: 'CLIPTextEncode', inputs: { text: ['18', 0], clip: ['1', 0] } }, '18': { class_type: 'Captioner', inputs: {} } };
  const original = structuredClone(graph);
  injectPromptStyler(graph, { promptStyler: { node: '4', input: 'text' } }, { promptStyler: recipe });
  assert.deepEqual(graph.promptstyler_next.inputs.prompt, ['18', 0]);
  assert.deepEqual(graph['4'].inputs.text, ['promptstyler_next', 0]);
  assert.deepEqual(graph['4'].inputs.clip, original['4'].inputs.clip);
  assert.equal(graph.promptstyler_next.class_type, 'PSNextCompose');
  assert.equal(JSON.parse(graph.promptstyler_next.inputs.recipe).model, 'anima-turbo');
});

test('text workflows style their final mapped text and route native negatives', () => {
  const graph = { p: { inputs: { text: 'Existing workflow prefix. User text' } }, n: { inputs: { text: 'blur' } }, sampler: { inputs: { steps: 4, cfg: 1, seed: 55 } } };
  const controls = { prompt: { node: 'p', input: 'text' }, negative: { node: 'n', input: 'text' } };
  injectPromptStyler(graph, { controls }, { promptStyler: recipe, negative: 'blur' });
  assert.equal(graph.promptstyler_next.inputs.prompt, 'Existing workflow prefix. User text');
  assert.deepEqual(graph.n.inputs.text, ['promptstyler_next', 1]);
  assert.deepEqual(graph.sampler.inputs, { steps: 4, cfg: 1, seed: 55 });
});

test('disabled recipes are exact graph identities; missing mappings fail visibly', () => {
  const graph = { p: { inputs: { text: 'Bird' } } };
  assert.deepEqual(injectPromptStyler(structuredClone(graph), {}, {}), graph);
  assert.throws(() => injectPromptStyler(graph, {}, { promptStyler: recipe }), /no PromptStyler text target/);
});

test('host metadata chooses distilled, edit, and unknown profiles explicitly', () => {
  assert.equal(studioModelProfile({ family: 'anima', defaults: { cfg: 1 } }), 'anima-turbo');
  assert.equal(studioModelProfile({ family: 'moss_image', defaults: { cfg: 1 } }), 'moss-image-dmd');
  assert.equal(studioModelProfile({ family: 'fibo2', capabilities: { imageToImage: true } }), 'fibo-edit');
  assert.equal(studioModelProfile({ family: 'unknown' }), 'generic');
});

test('owned service starts lazily once for concurrent requests and closes its socket', async () => {
  const managed = createManagedPromptStyler({ python: process.env.PROMPTSTYLER_PYTHON || 'python3' });
  const app = createServer(managed.middleware);
  app.listen(0, '127.0.0.1'); await once(app, 'listening');
  try {
    const origin = `http://127.0.0.1:${app.address().port}`;
    const results = await Promise.all(Array.from({ length: 5 }, () => fetch(origin + '/health').then((response) => response.json())));
    assert.ok(results.every((result) => result.status === 'ok'));
    const composed = await managed.compose({ ...recipe, prompt: 'A heron' });
    assert.ok(composed.positive.startsWith('A heron'));
    await managed.close();
    await assert.rejects(() => managed.compose({ prompt: 'x' }), /stopping/);
  } finally {
    await managed.close(); app.closeAllConnections(); await new Promise((resolve) => app.close(resolve));
  }
});

test('missing interpreter returns an actionable service error without taking down the host', async () => {
  const managed = createManagedPromptStyler({ python: '/not-a-real-interpreter' });
  const app = createServer(managed.middleware);
  app.listen(0, '127.0.0.1'); await once(app, 'listening');
  try {
    const response = await fetch(`http://127.0.0.1:${app.address().port}/health`);
    assert.equal(response.status, 503);
    assert.equal((await response.json()).error.code, 'styler_unavailable');
  } finally { await managed.close(); app.closeAllConnections(); await new Promise((resolve) => app.close(resolve)); }
});
