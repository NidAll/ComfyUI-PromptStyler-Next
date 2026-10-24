/** Transport-only browser client; no prompt formatting is implemented in JS. */
export class PromptStylerClient {
  constructor({ baseUrl = '/api/v1', fetchImpl = globalThis.fetch, timeoutMs = 5000 } = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.fetch = (...args) => fetchImpl(...args);
    this.timeoutMs = timeoutMs;
  }

  async request(path, { method = 'GET', body, rawBody } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetch(`${this.baseUrl}${path}`, {
        method, signal: controller.signal, credentials: 'same-origin',
        headers: body === undefined && rawBody === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: rawBody === undefined ? (body === undefined ? undefined : JSON.stringify(body)) : rawBody,
      });
      const value = await response.json();
      if (!response.ok) {
        const error = new Error(value.error?.message || `PromptStyler returned HTTP ${response.status}.`);
        error.code = value.error?.code || 'http_error';
        error.path = value.error?.path || '';
        error.status = response.status;
        throw error;
      }
      return value;
    } finally {
      clearTimeout(timer);
    }
  }

  async styles(filters = {}) {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value === undefined || value === null || value === '') continue;
      for (const item of Array.isArray(value) ? value : [value]) query.append(key, String(item));
    }
    return this.request(`/styles${query.size ? `?${query}` : ''}`);
  }
  style(id) { return this.request(`/styles/${encodeURIComponent(id)}`); }
  profiles() { return this.request('/profiles'); }
  catalog() { return this.request('/catalog'); }
  health() { return this.request('/health'); }
  compose(recipe) { return this.request('/compose', { method: 'POST', body: recipe }); }
  composeJson(rawText) {
    if (typeof rawText !== 'string') throw new TypeError('composeJson requires raw JSON text.');
    return this.request('/compose', { method: 'POST', rawBody: rawText });
  }
  recommend(request) { return this.request('/recommend', { method: 'POST', body: request }); }
}

/** Apply once to a fresh HEISS generation body; preserve metadata separately. */
export async function styleGenerationBody(client, body, recipe) {
  const composition = await client.compose({ ...recipe, prompt: body.prompt || '', negative: body.negative || '' });
  return { body: { ...body, prompt: composition.positive, negative: composition.negative }, composition };
}
