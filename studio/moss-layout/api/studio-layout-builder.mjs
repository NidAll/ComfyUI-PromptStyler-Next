// MOSS layout builder routes (2026-11-18). The builder in the composer has no serializer of its own:
// every compile and import goes to the MOSS Image Layout Prompt Builder node's same-origin routes in
// ComfyUI (ComfyUI-Ming-Image-Prompt-Builder, moss.py), so Studio and ComfyUI write the same prompt.
// Nothing is queued, saved or added to ComfyUI history.
import { comfyUrl } from '../server/comfy.js';
import { mountLayoutAssistRoutes } from './studio-layout-assist.mjs';

const OPERATIONS = new Set(['serialize', 'import']);
const FIELDS = {
  serialize: ['width', 'height', 'summary_caption', 'meta', 'canvas', 'palette', 'layers_data', 'output_format'],
  import: ['prompt', 'width', 'height']
};
const LIMIT = 400_000;

/** Only the fields the node reads, with the types it expects; import_json is never forwarded. */
export function layoutRequest(operation, body) {
  if (!OPERATIONS.has(operation)) throw Object.assign(new Error('Unknown layout operation.'), { status: 404 });
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw new Error('The request must be a JSON object.');
  const out = {};
  for (const key of FIELDS[operation]) {
    if (!(key in body)) continue;
    const value = body[key];
    if (key === 'width' || key === 'height') {
      if (!Number.isInteger(value)) throw new Error(`${key} must be an integer.`);
    } else if (typeof value !== 'string') throw new Error(`${key} must be a string.`);
    out[key] = value;
  }
  if (JSON.stringify(out).length > LIMIT) throw new Error('This layout is too large.');
  return out;
}

export function mountLayoutRoutes(app, { base = () => comfyUrl, fetcher = fetch, assist = true } = {}) {
  // AI routes first: '/api/moss-layout-ai' must not fall into '/api/moss-layout/:operation'.
  if (assist) mountLayoutAssistRoutes(app);
  app.post('/api/moss-layout/:operation', async (req, res) => {
    res.set('Cache-Control', 'no-store');
    let payload;
    try { payload = layoutRequest(req.params.operation, req.body); }
    catch (error) { res.status(error.status || 400).json({ error: error.message }); return; }
    try {
      const response = await fetcher(`${base()}/moss_prompt_builder/${req.params.operation}`, {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(15_000)
      });
      if (response.status === 404 || response.status === 405) {
        res.status(503).json({ error: 'Restart ComfyUI to load the MOSS layout builder node.', restart: true });
        return;
      }
      const body = await response.json().catch(() => ({ error: 'ComfyUI sent an unreadable layout answer.' }));
      res.status(response.ok ? 200 : response.status >= 500 ? 502 : 400).json(body);
    } catch (error) {
      res.status(503).json({ error: error.name === 'TimeoutError' ? 'ComfyUI is busy; try the layout again in a moment.' : 'ComfyUI is not reachable, so the layout cannot be checked.' });
    }
  });
}
