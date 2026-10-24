/** Express-compatible transport. All prompt composition remains in Python. */

const MAX_BODY = 128 * 1024;
const MAX_RESPONSE = 2 * 1024 * 1024;
const METHODS = new Map([
  ['GET', /^\/(?:health|catalog|profiles|styles(?:\/[a-z0-9][a-z0-9._-]*)?)$/],
  ['POST', /^\/(?:compose|recommend)$/],
]);

function send(res, status, payload) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.end(JSON.stringify(payload));
}

function failure(code, message) {
  return { error: { code, message, path: '' } };
}

function loopbackUpstream(value) {
  const url = new URL(value);
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(url.hostname)
      || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new TypeError('upstream must be an HTTP loopback origin, such as http://127.0.0.1:8791.');
  }
  return url.origin;
}

async function requestBody(req, limit) {
  if (req.body !== undefined) throw Object.assign(new Error('Mount before body parsing.'), { code: 'bridge_mount_order' });
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += Buffer.byteLength(chunk);
    if (size > limit) throw Object.assign(new Error('Request exceeds the body limit.'), { code: 'body_limit' });
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString('utf8');
}

async function responseBody(response, signal) {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('Empty sidecar response.');
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      signal.throwIfAborted();
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_RESPONSE) throw new Error('Sidecar response exceeds the limit.');
      chunks.push(Buffer.from(value));
    }
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } finally {
    await reader.cancel().catch(() => {});
  }
}

/** Mount after requestGuard with requireSignedIn, before express.json. */
export function createPromptStylerBridge({ upstream = 'http://127.0.0.1:8791', timeoutMs = 5000, maxBodyBytes = MAX_BODY, fetchImpl = globalThis.fetch } = {}) {
  const origin = loopbackUpstream(upstream);
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > 30000) throw new TypeError('timeoutMs must be between 1 and 30000.');
  if (!Number.isSafeInteger(maxBodyBytes) || maxBodyBytes < 1 || maxBodyBytes > MAX_BODY) throw new TypeError('maxBodyBytes must be between 1 and 131072.');
  return async function promptStylerBridge(req, res) {
    const requestOrigin = req.headers.origin;
    const protocol = req.socket?.encrypted ? 'https' : 'http';
    if (!req.headers.host || (requestOrigin && requestOrigin !== `${protocol}://${req.headers.host}`)
        || req.headers['sec-fetch-site'] === 'cross-site') {
      return send(res, 403, failure('forbidden_origin', 'Use PromptStyler through this Studio origin.'));
    }
    let target;
    try { target = new URL(req.url, 'http://bridge.local'); }
    catch { return send(res, 400, failure('invalid_request', 'Use a valid request URL.')); }
    if (!METHODS.get(req.method)?.test(target.pathname) || req.url.length > 4096) {
      return send(res, 404, failure('not_found', 'No PromptStyler endpoint exists at this path.'));
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      let body;
      if (req.method === 'POST') {
        if ((req.headers['content-type'] || '').split(';', 1)[0].trim().toLowerCase() !== 'application/json') {
          return send(res, 415, failure('unsupported_media_type', 'Send application/json.'));
        }
        body = await requestBody(req, maxBodyBytes);
      }
      const response = await fetchImpl(`${origin}/api/v1${target.pathname}${target.search}`, {
        method: req.method, body, signal: controller.signal, redirect: 'error',
        headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
      });
      const payload = await responseBody(response, controller.signal);
      send(res, response.status, payload);
    } catch (error) {
      if (error.code === 'bridge_mount_order') return send(res, 500, failure('bridge_mount_order', 'Mount the guarded PromptStyler bridge before express.json so Python receives the original JSON bytes.'));
      if (error.code === 'body_limit') return send(res, 413, failure('request_too_large', 'JSON requests must be at most 128 KiB.'));
      send(res, controller.signal.aborted ? 504 : 502, failure(controller.signal.aborted ? 'sidecar_timeout' : 'sidecar_unavailable', 'PromptStyler is unavailable. Start its local service and try again.'));
    } finally {
      clearTimeout(timer);
    }
  };
}
