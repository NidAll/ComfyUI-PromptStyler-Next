/** Owned local Python sidecar. No engine or prompting algorithms run in Node. */
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { createPromptStylerBridge } from './bridge.mjs';
import { PromptStylerClient } from './client.mjs';

export function createManagedPromptStyler({ python = 'python3', projectRoot = fileURLToPath(new URL('../', import.meta.url)), startupTimeoutMs = 10000 } = {}) {
  let child = null;
  let starting = null;
  let current = null;
  let closed = false;

  async function start() {
    if (closed) throw new Error('PromptStyler is stopping.');
    if (current) return current;
    if (starting) return starting;
    starting = new Promise((resolve, reject) => {
      const owned = spawn(python, ['-u', '-m', 'promptstyler_next.service', '--port', '0'], {
        cwd: projectRoot, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true,
      });
      child = owned;
      let output = '';
      const timer = setTimeout(() => {
        owned.kill('SIGTERM');
        reject(new Error('PromptStyler did not become ready. Check its Python interpreter and installation.'));
      }, startupTimeoutMs);
      const finish = () => clearTimeout(timer);
      owned.stderr.resume();
      owned.stdout.on('data', (chunk) => {
        output = (output + chunk.toString('utf8')).slice(-4096);
        const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
        if (!match || current || child !== owned) return;
        finish();
        current = { client: new PromptStylerClient({ baseUrl: `${match[0]}/api/v1` }), bridge: createPromptStylerBridge({ upstream: match[0] }) };
        resolve(current);
      });
      owned.once('error', () => { finish(); if (child === owned) child = null; reject(new Error('Cannot start PromptStyler. Check its configured Python interpreter.')); });
      owned.once('exit', () => {
        finish();
        if (child === owned) { child = null; current = null; starting = null; }
        reject(new Error('PromptStyler stopped before it became ready.'));
      });
    });
    try { return await starting; }
    catch (error) { starting = null; throw error; }
  }

  const stopOnExit = () => child?.kill('SIGTERM');
  process.once('exit', stopOnExit);

  return {
    stop: stopOnExit,
    async middleware(req, res) {
      try { await (await start()).bridge(req, res); }
      catch {
        if (!res.headersSent) {
          res.statusCode = 503;
          res.setHeader('Content-Type', 'application/json');
          res.setHeader('Cache-Control', 'no-store');
          res.end(JSON.stringify({ error: { code: 'styler_unavailable', message: 'PromptStyler could not start. Check its local installation and try again.', path: '' } }));
        }
      }
    },
    async compose(recipe) { return (await start()).client.compose(recipe); },
    async close() {
      closed = true;
      process.removeListener('exit', stopOnExit);
      const owned = child;
      if (!owned || owned.exitCode !== null || owned.signalCode !== null) return;
      owned.kill('SIGTERM');
      const timer = setTimeout(() => owned.kill('SIGKILL'), 2000);
      try { await once(owned, 'exit'); } finally { clearTimeout(timer); }
    },
  };
}
