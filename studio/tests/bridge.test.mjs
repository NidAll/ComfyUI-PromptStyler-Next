import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import test from 'node:test';
import { createPromptStylerBridge } from '../bridge.mjs';
import { PromptStylerClient, styleGenerationBody } from '../client.mjs';

async function listen(handler) {
  const server = createServer(handler);
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  return { server, origin: `http://127.0.0.1:${server.address().port}`, close: () => new Promise((resolve) => { server.closeAllConnections(); server.close(resolve); }) };
}

async function fixture(fetchImpl) {
  const handler = createPromptStylerBridge({ fetchImpl });
  return listen((req, res) => handler(req, res));
}

const jsonResponse = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

test('bridge forwards only documented route and payload to a fixed loopback sidecar', async () => {
  const calls = [];
  const app = await fixture(async (url, options) => { calls.push([url, options]); return jsonResponse({ items: [] }); });
  try {
    const response = await fetch(`${app.origin}/styles?q=noir&tag=film`);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { items: [] });
    assert.equal(calls[0][0], 'http://127.0.0.1:8791/api/v1/styles?q=noir&tag=film');
    assert.equal(calls[0][1].redirect, 'error');
    assert.equal(calls[0][1].headers.Cookie, undefined);
  } finally { await app.close(); }
});

test('bridge and browser client compose through one shared service contract', async () => {
  let captured;
  const app = await fixture(async (_url, options) => { captured = JSON.parse(options.body); return jsonResponse({ positive: 'A cat. Ink on paper.', negative: '', fingerprint: 'abc' }); });
  try {
    const client = new PromptStylerClient({ baseUrl: app.origin });
    const generation = { prompt: 'A cat', negative: 'blur', seed: 42, width: 1024 };
    const result = await styleGenerationBody(client, generation, { model: 'flux', styles: [{ id: 'illustration.ink', intensity: 0.7 }] });
    assert.equal(captured.prompt, 'A cat'); assert.equal(captured.negative, 'blur');
    assert.deepEqual(result.body, { ...generation, prompt: 'A cat. Ink on paper.', negative: '' });
    assert.equal(generation.prompt, 'A cat');
  } finally { await app.close(); }
});

test('sidecar domain errors retain machine-readable diagnostics', async () => {
  const app = await fixture(async () => jsonResponse({ error: { code: 'unknown_style', message: 'Choose a catalog entry.', path: 'styles.0.id' } }, 400));
  try {
    const client = new PromptStylerClient({ baseUrl: app.origin });
    await assert.rejects(() => client.compose({ prompt: 'x' }), (error) => error.code === 'unknown_style' && error.path === 'styles.0.id' && error.status === 400);
  } finally { await app.close(); }
});

test('bridge rejects cross-origin calls and arbitrary routes without forwarding', async () => {
  let calls = 0;
  const app = await fixture(async () => { calls += 1; return jsonResponse({}); });
  try {
    assert.equal((await fetch(`${app.origin}/compose`, { method: 'POST', headers: { Origin: 'https://evil.example', 'Content-Type': 'application/json' }, body: '{}' })).status, 403);
    assert.equal((await fetch(`${app.origin}/styles`, { headers: { 'Sec-Fetch-Site': 'cross-site' } })).status, 403);
    for (const route of ['/packs', '/../../file', '/styles/foo/bar', '/compose']) assert.equal((await fetch(app.origin + route)).status, 404);
    assert.equal(calls, 0);
  } finally { await app.close(); }
});

test('body limits and JSON media type are enforced before forwarding', async () => {
  let calls = 0;
  const app = await fixture(async () => { calls += 1; return jsonResponse({}); });
  try {
    assert.equal((await fetch(`${app.origin}/compose`, { method: 'POST', body: '{}' })).status, 415);
    assert.equal((await fetch(`${app.origin}/compose`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: 'x'.repeat(131073) })).status, 413);
    assert.equal(calls, 0);
  } finally { await app.close(); }
});

test('invalid upstreams and transport options cannot create an open proxy', () => {
  for (const upstream of ['https://example.com', 'http://example.com', 'http://127.0.0.1:80/path', 'http://user:pass@127.0.0.1:80', 'file:///tmp/file', 'http://127.0.0.1:80/?x=1']) assert.throws(() => createPromptStylerBridge({ upstream }), TypeError);
  for (const timeoutMs of [0, NaN, 40000]) assert.throws(() => createPromptStylerBridge({ timeoutMs }), TypeError);
});

test('sidecar unavailable produces bounded generic error', async () => {
  const app = await fixture(async () => { throw new Error('private filesystem details'); });
  try {
    const response = await fetch(`${app.origin}/health`);
    assert.equal(response.status, 502);
    assert.equal((await response.json()).error.code, 'sidecar_unavailable');
  } finally { await app.close(); }
});

test('timeout covers upstream response and returns 504', async () => {
  const handler = createPromptStylerBridge({ timeoutMs: 25, fetchImpl: async (_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true })) });
  const app = await listen(handler);
  try {
    const response = await fetch(`${app.origin}/health`);
    assert.equal(response.status, 504); assert.equal((await response.json()).error.code, 'sidecar_timeout');
  } finally { await app.close(); }
});

test('malformed and oversized upstream responses become safe errors', async () => {
  for (const value of ['not json', 'x'.repeat(2 * 1024 * 1024 + 1)]) {
    const app = await fixture(async () => new Response(value));
    try { assert.equal((await fetch(`${app.origin}/health`)).status, 502); }
    finally { await app.close(); }
  }
});


test('parsed bodies fail with an actionable mount-order error', async () => {
  let calls = 0;
  const handler = createPromptStylerBridge({ fetchImpl: async () => { calls += 1; return jsonResponse({}); } });
  const app = await listen((req, res) => { req.body = { prompt: 'already parsed' }; return handler(req, res); });
  try {
    const response = await fetch(`${app.origin}/compose`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    assert.equal(response.status, 500); assert.equal((await response.json()).error.code, 'bridge_mount_order'); assert.equal(calls, 0);
  } finally { await app.close(); }
});

test('browser fetch is invoked without binding the client as receiver', async () => {
  const client = new PromptStylerClient({ fetchImpl: function () { assert.equal(this, undefined); return Promise.resolve(jsonResponse({ status: 'ok' })); } });
  assert.equal((await client.health()).status, 'ok');
});
