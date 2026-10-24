import { PromptStylerClient } from './client.mjs';

const api = new PromptStylerClient();
const $ = (id) => document.getElementById(id);
const axes = ['medium', 'lighting', 'palette', 'composition', 'texture', 'mood', 'detail'];
const state = { layers: [], styles: [], profiles: [], visible: 12, result: null, revision: 0, search: 0, favorites: new Set() };
try {
  const stored = JSON.parse(localStorage.getItem('promptstyler-next.favorites') || '[]');
  if (Array.isArray(stored)) state.favorites = new Set(stored.filter((id) => typeof id === 'string'));
} catch { /* Storage may be unavailable in private browsing. */ }

function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
}

function message(id, text, error = false) {
  $(id).textContent = text;
  $(id).classList.toggle('error', error);
}

function dirty() {
  state.revision += 1;
  if (state.result) {
    message('stale', 'Recipe changed. Compose again to refresh this result.');
    $('stale').classList.add('is-stale');
  }
  $('copy').disabled = true;
  $('copy-json').disabled = true;
}

function recipe() {
  return { schema_version: 1, prompt: $('prompt').value, negative: $('negative').value, model: $('model').value, styles: state.layers.map(({ id, intensity }) => ({ id, intensity })), conflict_policy: $('conflict').value, locked_axes: axes.filter((axis) => $(`lock-${axis}`).checked) };
}

for (const axis of axes) {
  const label = node('label');
  const checkbox = node('input');
  checkbox.type = 'checkbox'; checkbox.id = `lock-${axis}`; checkbox.addEventListener('change', dirty);
  label.append(checkbox, document.createTextNode(axis)); $('axis-locks').append(label);
}

function updateProfile() {
  const profile = state.profiles.find((entry) => entry.id === $('model').value);
  message('profile-note', profile ? `${profile.format} prompting. ${profile.guidance}` : 'Unknown model: the engine will use its conservative generic profile.');
}

function saveFavorites() {
  try { localStorage.setItem('promptstyler-next.favorites', JSON.stringify([...state.favorites].sort())); }
  catch { message('catalog-status', 'Favorites work in this tab; browser storage is unavailable.'); }
}

function renderStyles() {
  const entries = $('favorites-only').checked ? state.styles.filter((style) => state.favorites.has(style.id)) : state.styles;
  $('styles').replaceChildren();
  $('result-count').textContent = `${entries.length} ${entries.length === 1 ? 'entry' : 'entries'}`;
  $('more').hidden = entries.length <= state.visible;
  if (!entries.length) message('catalog-status', $('favorites-only').checked ? 'No favorites match. Save an entry or reset the filters.' : 'No styles match these filters. Try another term or reset the filters.');
  else message('catalog-status', '');
  for (const style of entries.slice(0, state.visible)) {
    const item = node('li', undefined, 'style-entry');
    const swatchIndex = [...style.id].reduce((value, character) => value + character.charCodeAt(0), 0) % 6;
    const swatch = node('div', undefined, `swatch swatch-${swatchIndex}`); swatch.setAttribute('aria-hidden', 'true');
    swatch.append(node('span'), node('span'), node('span'));
    const title = node('h3', style.name);
    const description = node('p', style.description);
    const meta = node('p', `${style.category.replaceAll('/', ' / ')} (${style.kind})`);
    const actions = node('div', undefined, 'entry-actions');
    const selected = state.layers.some((layer) => layer.id === style.id);
    const add = node('button', selected ? 'Added to recipe' : 'Add to recipe'); add.type = 'button'; add.disabled = selected;
    add.addEventListener('click', () => {
      if (state.layers.some((layer) => layer.id === style.id)) return;
      if (state.layers.length >= 16) return message('compose-status', 'Recipes support up to 16 layers. Remove a layer to add another.', true);
      state.layers.push({ id: style.id, name: style.name, intensity: 0.75 }); dirty(); renderLayers(); renderStyles();
    });
    const favorite = node('button', state.favorites.has(style.id) ? 'Saved' : 'Save'); favorite.type = 'button';
    favorite.setAttribute('aria-label', `${state.favorites.has(style.id) ? 'Unsave' : 'Save'} ${style.name}`); favorite.setAttribute('aria-pressed', String(state.favorites.has(style.id)));
    favorite.addEventListener('click', () => {
      if (state.favorites.has(style.id)) state.favorites.delete(style.id); else state.favorites.add(style.id);
      saveFavorites(); renderStyles();
    });
    actions.append(add, favorite);
    const details = node('details'); details.append(node('summary', 'Style directions'));
    details.append(node('p', (style.tags || []).join(', ')));
    const directions = node('p');
    details.addEventListener('toggle', async () => {
      if (!details.open || directions.textContent) return;
      directions.textContent = 'Loading style details…';
      try {
        const complete = await api.style(style.id);
        directions.textContent = (complete.clauses || []).map((clause) => `${clause.axis}: ${clause.text}`).join('\n') || complete.description;
      } catch (error) { directions.textContent = error.message; }
    });
    details.append(directions);
    item.append(swatch, title, description, meta, actions, details); $('styles').append(item);
  }
}

function renderLayers() {
  $('layers').replaceChildren(); $('recipe-empty').hidden = state.layers.length > 0;
  $('layer-count').textContent = `${state.layers.length} ${state.layers.length === 1 ? 'layer' : 'layers'}`;
  state.layers.forEach((layer, index) => {
    const item = node('li', undefined, 'layer');
    const heading = node('div', undefined, 'layer-name'); heading.append(node('h3', `${index + 1}. ${layer.name || layer.id}`));
    const label = node('label', undefined, 'intensity-label'); label.htmlFor = `intensity-${index}`;
    const output = node('output', `${Math.round(layer.intensity * 100)}%`); output.htmlFor = `intensity-${index}`;
    label.append(document.createTextNode('Intensity'), output);
    const range = node('input'); range.type = 'range'; range.id = `intensity-${index}`; range.min = '0'; range.max = '1'; range.step = '0.05'; range.value = String(layer.intensity);
    range.addEventListener('input', () => { layer.intensity = Number(range.value); output.textContent = `${Math.round(layer.intensity * 100)}%`; dirty(); });
    const controls = node('div', undefined, 'layer-controls');
    for (const [name, offset] of [['Move up', -1], ['Move down', 1]]) {
      const button = node('button', name); button.type = 'button'; button.disabled = index + offset < 0 || index + offset >= state.layers.length; button.setAttribute('aria-label', `${name}: ${layer.name || layer.id}`);
      button.addEventListener('click', () => { [state.layers[index], state.layers[index + offset]] = [state.layers[index + offset], state.layers[index]]; dirty(); renderLayers(); }); controls.append(button);
    }
    const remove = node('button', 'Remove'); remove.type = 'button'; remove.setAttribute('aria-label', `Remove ${layer.name || layer.id}`); remove.addEventListener('click', () => { state.layers.splice(index, 1); dirty(); renderLayers(); renderStyles(); }); controls.append(remove);
    item.append(heading, label, range, controls); $('layers').append(item);
  });
}

function syncFilterUrl() {
  const url = new URL(location.href);
  for (const [name, id] of [['q', 'search'], ['category', 'category'], ['kind', 'kind'], ['model', 'model']]) {
    if ($(id).value) url.searchParams.set(name, $(id).value); else url.searchParams.delete(name);
  }
  if ($('favorites-only').checked) url.searchParams.set('favorites', '1'); else url.searchParams.delete('favorites');
  history.replaceState(null, '', url);
}

async function loadStyles() {
  const sequence = ++state.search; state.visible = 12;
  message('catalog-status', 'Loading styles…'); $('styles').setAttribute('aria-busy', 'true'); syncFilterUrl();
  try {
    const entries = [];
    for (let offset = 0; ; offset += 100) {
      const result = await api.styles({ q: $('search').value, category: $('category').value, kind: $('kind').value, model: $('model').value, limit: 100, offset });
      if (sequence !== state.search) return;
      entries.push(...result.items);
      if (result.items.length < 100) break;
    }
    state.styles = entries; renderStyles();
  } catch (error) {
    if (sequence !== state.search) return;
    state.styles = []; $('styles').replaceChildren(); message('catalog-status', `${error.message} Check the local service, then reset filters to retry.`, true);
  } finally { if (sequence === state.search) $('styles').removeAttribute('aria-busy'); }
}

async function compose() {
  const revision = state.revision;
  $('compose').disabled = true; message('compose-status', 'Composing…');
  try {
    const result = await api.compose(recipe()); state.result = result;
    $('positive').textContent = result.positive; $('negative-output').textContent = result.negative; $('negative-result').hidden = !result.negative;
    $('trace').textContent = JSON.stringify({ profile: result.profile, fingerprint: result.fingerprint, catalog_fingerprint: result.catalog_fingerprint, structured: result.structured, trace: result.trace }, null, 2);
    $('warnings').replaceChildren(...result.warnings.map((warning) => node('p', `${warning.code}: ${warning.message}`, 'helper')));
    if (revision === state.revision) {
      message('stale', 'This result matches the current recipe.'); $('stale').classList.remove('is-stale'); $('copy').disabled = false; $('copy-json').disabled = false;
    } else { message('stale', 'Recipe changed while composing. Compose again to refresh this result.'); $('stale').classList.add('is-stale'); }
    message('compose-status', '');
  } catch (error) { message('compose-status', error.message, true); }
  finally { $('compose').disabled = false; }
}

$('compose').addEventListener('click', compose);
for (const id of ['prompt', 'negative']) $(id).addEventListener('input', dirty);
$('conflict').addEventListener('change', dirty);
$('model').addEventListener('change', () => { dirty(); updateProfile(); loadStyles(); });
$('filters').addEventListener('submit', (event) => { event.preventDefault(); loadStyles(); });
let searchTimer;
$('search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadStyles, 180); });
for (const id of ['category', 'kind']) $(id).addEventListener('change', loadStyles);
$('favorites-only').addEventListener('change', () => { syncFilterUrl(); renderStyles(); });
$('more').addEventListener('click', () => { state.visible += 12; renderStyles(); });
$('reset-filters').addEventListener('click', () => { $('search').value = ''; $('category').value = ''; $('kind').value = ''; $('favorites-only').checked = false; loadStyles(); });
$('recommend').addEventListener('click', async () => {
  $('recommend').disabled = true; const sequence = ++state.search; message('catalog-status', 'Matching prompt words to style metadata…');
  try {
    const result = await api.recommend({ prompt: $('prompt').value, model: $('model').value, limit: 12 });
    if (sequence !== state.search) return;
    state.styles = result.items; state.visible = 12; renderStyles();
    message('catalog-status', 'Suggestions use metadata matches, not an image-quality prediction.');
  } catch (error) { if (sequence === state.search) message('catalog-status', error.message, true); }
  finally { $('recommend').disabled = false; }
});
for (const [id, value] of [['copy', () => state.result?.positive], ['copy-json', () => JSON.stringify(state.result, null, 2)]]) {
  $(id).addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(value()); message('compose-status', id === 'copy' ? 'Prompt copied.' : 'Result JSON copied.'); }
    catch { message('compose-status', 'Clipboard unavailable. Select and copy the output text instead.', true); }
  });
}
$('export').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(recipe(), null, 2) + '\n'], { type: 'application/json' }));
  const anchor = node('a'); anchor.href = url; anchor.download = 'promptstyler-recipe.json'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('import').addEventListener('change', async () => {
  const file = $('import').files?.[0]; if (!file) return;
  try {
    if (file.size > 128 * 1024) throw new Error('Recipe files must be at most 128 KiB.');
    const verified = await api.composeJson(await file.text()); const request = verified.recipe;
    $('prompt').value = request.prompt; $('negative').value = request.negative || '';
    if (![...$('model').options].some((option) => option.value === request.model)) { const option = node('option', request.model); option.value = request.model; $('model').append(option); }
    $('model').value = request.model; $('conflict').value = request.conflict_policy;
    for (const axis of axes) $(`lock-${axis}`).checked = request.locked_axes.includes(axis);
    state.layers = await Promise.all(request.styles.map(async (layer) => ({ ...layer, name: (await api.style(layer.id)).name })));
    dirty(); renderLayers(); updateProfile(); await loadStyles(); await compose();
  } catch (error) { message('compose-status', `Recipe was not imported: ${error.message}`, true); }
  finally { $('import').value = ''; }
});

async function start() {
  try {
    const [catalog, profiles] = await Promise.all([api.catalog(), api.profiles()]); state.profiles = profiles.items;
    $('model').replaceChildren(...profiles.items.map((profile) => { const option = node('option', profile.name); option.value = profile.id; return option; }));
    $('model').value = 'generic';
    for (const category of catalog.categories) { const option = node('option', category.replaceAll('/', ' / ')); option.value = category; $('category').append(option); }
    const query = new URLSearchParams(location.search);
    for (const [key, id] of [['q', 'search'], ['category', 'category'], ['kind', 'kind'], ['model', 'model']]) if (query.has(key)) $(id).value = query.get(key);
    if (!$('model').value) $('model').value = 'generic';
    $('favorites-only').checked = query.get('favorites') === '1';
    message('connection', 'Local engine ready'); $('fingerprint').textContent = `Catalog ${catalog.catalog_fingerprint.slice(0, 12)}`;
    updateProfile(); await loadStyles();
  } catch (error) {
    message('connection', 'Local engine unavailable', true); message('catalog-status', `${error.message} Start the service and reload this page.`, true);
  }
}
renderLayers(); start();
