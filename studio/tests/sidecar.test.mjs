/** End-to-end Python engine -> loopback service -> Node bridge -> public client. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { createPromptStylerBridge } from '../bridge.mjs';
import { PromptStylerClient } from '../client.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));

test('real Python catalog, composition, and errors survive the HEISS bridge', async () => {
  const python = spawn(process.env.PROMPTSTYLER_PYTHON || 'python3', ['-m', 'promptstyler_next.service', '--port', '0'], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = '';
  python.stderr.on('data', (value) => { stderr += value; });
  let app;
  try {
    const upstream = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Python sidecar did not start.')), 10000);
      let output = '';
      python.stdout.on('data', (chunk) => {
        output += chunk;
        const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
        if (match) { clearTimeout(timer); resolve(match[0]); }
      });
      python.once('error', (error) => { clearTimeout(timer); reject(error); });
      python.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Python exited ${code}: ${stderr}`)); });
    });
    const handler = createPromptStylerBridge({ upstream });
    app = createServer((req, res) => handler(req, res)); app.listen(0, '127.0.0.1'); await once(app, 'listening');
    const client = new PromptStylerClient({ baseUrl: `http://127.0.0.1:${app.address().port}` });
    const catalog = await client.catalog(); assert.ok(catalog.total > 0);
    const styles = await client.styles({ limit: 1 }); assert.equal(styles.items.length, 1);
    const profiles = await client.profiles(); assert.ok(profiles.items.some((profile) => profile.id === 'anima'));
    const recipe = { prompt: 'A red fox in winter', model: 'flux', styles: [{ id: styles.items[0].id, intensity: 0.75 }] };
    const composition = await client.compose(recipe);
    const direct = await fetch(`${upstream}/api/v1/compose`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(recipe) }).then((response) => response.json());
    assert.deepEqual(composition, direct); assert.equal(composition.catalog_fingerprint, catalog.catalog_fingerprint);
    await assert.rejects(() => client.composeJson('{"prompt":"one","prompt":"two"}'), (error) => error.status === 400);
    assert.deepEqual(await client.composeJson(JSON.stringify(recipe)), composition);
    await assert.rejects(() => client.compose({ prompt: 'a fox', styles: [{ id: 'missing.style', intensity: 1 }] }), (error) => error.code === 'unknown_style');
  } finally {
    if (app) await new Promise((resolve) => { app.closeAllConnections(); app.close(resolve); });
    python.kill('SIGTERM');
    if (python.exitCode === null) await once(python, 'exit');
  }
});
