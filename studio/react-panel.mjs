import { PromptStylerClient } from './client.mjs';
import { studioModelProfile } from './model-profile.mjs';

const client = new PromptStylerClient({ baseUrl: '/api/promptstyler/v1' });
const selections = new Map();
const listeners = new Set();
let revision = 0;
const subscribe = (listener) => { listeners.add(listener); return () => listeners.delete(listener); };
const snapshot = () => revision;
const keyOf = (profile) => profile?.id || profile?.profileId || 'unknown';
const empty = () => ({ enabled: true, styles: [], model: '', conflict_policy: 'last_wins', locked_axes: [], mix: false });
const storageKey = 'promptstyler-next.studiio.v1';
const catalogs = new Map();
let savedPresets;
let favoriteIds;
const presetsOf = () => savedPresets ??= readLibrary().presets;
const favoritesOf = () => favoriteIds ??= readFavorites();
function changed() { revision += 1; for (const listener of listeners) listener(); }

export function normalizeStyleSelection(value) {
  if (!value || typeof value !== 'object' || !Array.isArray(value.styles)) return empty();
  const ids = new Set();
  return {
    enabled: value.enabled !== false,
    styles: value.styles.filter((layer) => layer && typeof layer.id === 'string' && layer.id.length <= 96
      && /^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$/.test(layer.id)
      && Number.isFinite(layer.intensity) && !ids.has(layer.id) && ids.add(layer.id))
      .slice(0, 16).map(({ id, name, kind, intensity }) => ({ id, name: typeof name === 'string' ? name.slice(0, 160) : id,
        kind: ['style', 'grade', 'modifier'].includes(kind) ? kind : undefined, intensity: Math.min(1, Math.max(0, intensity)) })),
    model: typeof value.model === 'string' ? value.model.slice(0, 128) : '',
    conflict_policy: ['last_wins', 'first_wins', 'error'].includes(value.conflict_policy) ? value.conflict_policy : 'last_wins',
    locked_axes: Array.isArray(value.locked_axes) ? [...new Set(value.locked_axes.filter((axis) => ['medium', 'lighting', 'palette', 'composition', 'texture', 'mood', 'detail'].includes(axis)))] : [],
    mix: value.mix === true,
  };
}
function readLibrary() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || '{}');
    return { selections: saved.selections && typeof saved.selections === 'object' ? saved.selections : {},
      presets: Array.isArray(saved.presets) ? saved.presets.filter((preset) => preset && typeof preset.id === 'string' && typeof preset.name === 'string').slice(0, 40)
        .map((preset) => ({ id: preset.id, name: preset.name.slice(0, 60), selection: normalizeStyleSelection(preset.selection) })) : [] };
  } catch { return { selections: {}, presets: [] }; }
}
function configOf(profile) {
  const key = keyOf(profile);
  if (!selections.has(key)) selections.set(key, normalizeStyleSelection(readLibrary().selections[key]));
  return selections.get(key);
}
function persistLibrary(presets, selectionKey) {
  const saved = readLibrary();
  // Update only the changed workflow so another tab's unrelated selections survive.
  const next = { selections: { ...saved.selections, ...(selectionKey ? { [selectionKey]: selections.get(selectionKey) } : {}) }, presets: presets ?? saved.presets };
  try { localStorage.setItem(storageKey, JSON.stringify(next)); return true; }
  catch { return false; }
}

export function searchStyles(styles, query) {
  const normalize = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
  const words = normalize(query).trim().split(/\s+/).filter(Boolean);
  return styles.filter((style) => {
    const text = normalize([style.name, style.description, style.category, style.pack_id, style.preview?.alt, ...(style.tags || [])].join(' '));
    return words.every((word) => text.includes(word));
  });
}

function loadCatalog(model) {
  if (!catalogs.has(model)) {
    const promise = Promise.all([client.profiles(), (async () => {
      const entries = [];
      for (let offset = 0; ; offset += 100) {
        const page = await client.styles({ model, limit: 100, offset });
        entries.push(...page.items);
        if (page.items.length < 100) return entries;
      }
    })()]);
    catalogs.set(model, promise);
    promise.catch(() => catalogs.delete(model));
  }
  return catalogs.get(model);
}

function update(profile, patch) {
  const key = keyOf(profile);
  selections.set(key, { ...configOf(profile), ...patch });
  persistLibrary(undefined, key);
  changed();
}

/** Snapshot the browser-side state for an explicitly saved creative recipe. */
export function getStudioPromptStylerState(profile) {
  return normalizeStyleSelection(configOf(profile));
}

/** Restore complete browser state only after validating its executable recipe. */
export function restoreStudioPromptStylerState(profile, state) {
  if (state == null) { update(profile, empty()); return; }
  if (typeof state !== 'object' || Array.isArray(state) || !Array.isArray(state.styles)
      || (state.enabled !== undefined && typeof state.enabled !== 'boolean')
      || (state.model !== undefined && (typeof state.model !== 'string' || state.model.length > 128))
      || (state.mix !== undefined && typeof state.mix !== 'boolean')) {
    throw new TypeError('The saved style selection is invalid.');
  }
  const recipe = { schema_version: 1, styles: state.styles, conflict_policy: state.conflict_policy,
    locked_axes: state.locked_axes, ...(state.model ? { model: state.model } : {}) };
  const restored = validateStyleRecipe(profile, recipe);
  update(profile, normalizeStyleSelection({ ...state, styles: restored.styles }));
}

export function studioPromptStylerSelection(profile) {
  const config = configOf(profile);
  if (!config.enabled || !config.styles.length || profile?.kind === 'video') return undefined;
  return {
    schema_version: 1,
    model: config.model || studioModelProfile(profile),
    styles: config.styles.map(({ id, intensity }) => ({ id, intensity })),
    conflict_policy: config.conflict_policy,
    locked_axes: [...config.locked_axes],
  };
}

/** Restore a generation recipe before replay; catalog IDs are validated by the engine. */
function validateStyleRecipe(profile, recipe) {
  if (typeof recipe !== 'object' || Array.isArray(recipe) || (recipe.schema_version !== undefined && recipe.schema_version !== 1)
    || (recipe.styles !== undefined && !Array.isArray(recipe.styles)) || (recipe.styles?.length || 0) > 16) {
    throw new TypeError('Choose a style recipe with at most 16 layers.');
  }
  if ((recipe.model !== undefined && (typeof recipe.model !== 'string' || !recipe.model || recipe.model.length > 128))
    || (recipe.conflict_policy !== undefined && !['last_wins', 'first_wins', 'error'].includes(recipe.conflict_policy))
    || (recipe.locked_axes !== undefined && (!Array.isArray(recipe.locked_axes) || recipe.locked_axes.length > 7
      || new Set(recipe.locked_axes).size !== recipe.locked_axes.length
      || recipe.locked_axes.some((axis) => !['medium', 'lighting', 'palette', 'composition', 'texture', 'mood', 'detail'].includes(axis))))) {
    throw new TypeError('The style recipe has invalid model, conflict or protected-attribute settings.');
  }
  const layers = (recipe.styles || []).map((layer) => layer && ({ ...layer, intensity: layer.intensity === undefined ? 1 : layer.intensity }));
  const ids = new Set();
  for (const layer of layers) {
    if (!layer || typeof layer.id !== 'string' || layer.id.length > 96 || !/^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$/.test(layer.id) || ids.has(layer.id)
      || !Number.isFinite(layer.intensity) || layer.intensity < 0 || layer.intensity > 1) {
      throw new TypeError('Each style needs a unique ID and a strength between 0 and 1.');
    }
    ids.add(layer.id);
  }
  const prior = configOf(profile);
  const restored = normalizeStyleSelection({ ...recipe, styles: layers.map((layer) => ({
    ...prior.styles.find((old) => old.id === layer.id), ...layer,
  })) });
  return { ...restored, mix: recipe.mix === true || restored.styles.filter((layer) => layer.kind === 'style').length > 1 };
}

export function restoreStudioPromptStylerSelection(profile, recipe) {
  if (recipe == null) { update(profile, empty()); return; }
  update(profile, validateStyleRecipe(profile, recipe));
}

function readFavorites() {
  try {
    const value = JSON.parse(localStorage.getItem('promptstyler-next.favorites') || '[]');
    return new Set(Array.isArray(value) ? value.filter((id) => typeof id === 'string').slice(0, 10000) : []);
  } catch { return new Set(); }
}

// Keep multiple Studio tabs on the same local origin in sync.
if (typeof window !== 'undefined') window.addEventListener('storage', (event) => {
  if (event.key === storageKey || event.key === null) {
    selections.clear(); savedPresets = readLibrary().presets; changed();
  }
  if (event.key === 'promptstyler-next.favorites' || event.key === null) {
    favoriteIds = readFavorites(); changed();
  }
});

const recentPacks = new Set(['next.computational-surfaces', 'next.optical-materials', 'next.animation-finishing', 'next.information-hierarchy']);
const counts = { style: 'looks', grade: 'color grades', modifier: 'effects', saved: 'saved styles' };
const titles = { style: 'Looks', grade: 'Color', modifier: 'Effects', saved: 'Saved', presets: 'Presets' };
const labelOf = (value) => value.replaceAll('-', ' ').replaceAll('/', ' / ').replace(/\b\w/g, (letter) => letter.toUpperCase());
const featured = ['cinema.noir', 'anime.cel', 'cinema.anamorphic', 'anime.watercolor', 'computational.flow-engraving'];

/** React is supplied by the embedding host; no second runtime or styling engine. */
export function createPromptStylerPanel(React) {
  const h = React.createElement;
  const button = (label, onClick, props = {}) => h('button', { type: 'button', onClick, ...props }, label);
  const field = (label, input) => h('label', { className: 'psn-field' }, h('span', null, label), input);
  return function PromptStylerPanel({ profile, prompt = '', negative = '', mode = 'image' }) {
    React.useSyncExternalStore(subscribe, snapshot, snapshot);
    const config = configOf(profile);
    const model = config.model || studioModelProfile(profile);
    const [open, setOpen] = React.useState(false);
    const [expanded, setExpanded] = React.useState(false);
    const [query, setQuery] = React.useState('');
    const [category, setCategory] = React.useState('');
    const [tab, setTab] = React.useState('style');
    const [latest, setLatest] = React.useState(false);
    const favorites = favoritesOf();
    const [profiles, setProfiles] = React.useState([]);
    const [styles, setStyles] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState('');
    const [reload, setReload] = React.useState(0);
    const [result, setResult] = React.useState(null);
    const [busy, setBusy] = React.useState(false);
    const [shown, setShown] = React.useState(24);
    const presets = presetsOf();
    const [presetName, setPresetName] = React.useState('');
    const [notice, setNotice] = React.useState('');
    const [sort, setSort] = React.useState('featured');
    const dialog = React.useRef(null);
    const controlId = React.useId();
    const recipe = { ...studioPromptStylerSelection(profile), prompt, negative };
    const identity = JSON.stringify(recipe);
    const pending = result && result.identity !== identity;

    React.useEffect(() => {
      if (open) {
        dialog.current?.showModal();
        if (window.matchMedia('(min-width: 701px)').matches) dialog.current?.querySelector('input[type=search]')?.focus();
      } else dialog.current?.close();
    }, [open]);

    // Load every page of the model-compatible catalog, then filter instantly locally.
    React.useEffect(() => {
      if (!open) return;
      let cancelled = false;
      setLoading(true); setError(''); setStyles([]);
      loadCatalog(model).then(([nextProfiles, entries]) => {
        if (!cancelled) { setProfiles(nextProfiles.items); setStyles(entries); }
      }).catch((failure) => { if (!cancelled) setError(failure.message); })
        .finally(() => { if (!cancelled) setLoading(false); });
      return () => { cancelled = true; };
    }, [open, model, reload]);

    React.useEffect(() => { setShown(24); }, [query, category, tab, latest, model, sort]);

    function savePreset(event) {
      event.preventDefault();
      const name = presetName.trim();
      if (!name || !config.styles.length) return;
      const existing = presets.find((preset) => preset.name.toLocaleLowerCase() === name.toLocaleLowerCase());
      const preset = { id: existing?.id || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`, name, selection: normalizeStyleSelection(config) };
      const next = [preset, ...presets.filter((item) => item.id !== preset.id)].slice(0, 40);
      savedPresets = next; changed(); setPresetName('');
      setNotice(persistLibrary(next) ? `Saved “${name}”. Find it in Presets.` : 'Browser storage is full. This preset is available until you close the page.');
    }
    function removePreset(id) {
      const next = presets.filter((preset) => preset.id !== id);
      savedPresets = next; changed(); persistLibrary(next);
    }
    function usePreset(preset) {
      update(profile, normalizeStyleSelection(preset.selection));
      setExpanded(true); setNotice(`Applied “${preset.name}”.`);
    }
    function favorite(id) {
      const next = new Set(favorites);
      if (next.has(id)) next.delete(id); else next.add(id);
      favoriteIds = next; changed();
      try { localStorage.setItem('promptstyler-next.favorites', JSON.stringify([...next].slice(0, 10000))); }
      catch { /* Favorites remain available for this open panel. */ }
    }
    function remove(id) { update(profile, { styles: config.styles.filter((layer) => layer.id !== id) }); }
    function choose(style) {
      if (config.styles.some((layer) => layer.id === style.id)) { remove(style.id); return; }
      const layers = !config.mix && style.kind !== 'modifier'
        ? config.styles.filter((layer) => (layer.kind || styles.find((item) => item.id === layer.id)?.kind) !== style.kind)
        : config.styles;
      if (layers.length >= 16) return;
      update(profile, { enabled: true, styles: [...layers, { id: style.id, name: style.name, kind: style.kind, intensity: 0.75 }] });
    }
    function changeLayer(index, patch) {
      update(profile, { styles: config.styles.map((layer, position) => position === index ? { ...layer, ...patch } : layer) });
    }
    function move(index, offset) {
      const layers = [...config.styles];
      [layers[index], layers[index + offset]] = [layers[index + offset], layers[index]];
      update(profile, { styles: layers });
    }
    async function preview() {
      setBusy(true); setError('');
      try { const composition = await client.compose(recipe); setResult({ identity, composition }); }
      catch (failure) { setError(failure.message); }
      finally { setBusy(false); }
    }
    function resetFilters() { setQuery(''); setCategory(''); setLatest(false); }

    const candidates = React.useMemo(() => styles.filter((style) => tab === 'saved' ? favorites.has(style.id) : style.kind === tab), [styles, tab, favorites]);
    const categories = React.useMemo(() => [...new Set(candidates.map((style) => style.category.split('/')[0]))].sort(), [candidates]);
    const visible = React.useMemo(() => searchStyles(candidates, query).filter((style) => (!category || style.category.split('/')[0] === category)
      && (!latest || (style.pack_id.startsWith('community.') || recentPacks.has(style.pack_id))))
      .sort((a, b) => {
        const rank = (style) => { const index = featured.indexOf(style.id); return index < 0 ? featured.length : index; };
        return (sort === 'favorites' ? Number(favorites.has(b.id)) - Number(favorites.has(a.id)) : sort === 'featured' ? rank(a) - rank(b) : 0) || a.name.localeCompare(b.name);
      }), [candidates, query, category, latest, sort, favorites]);
    const visiblePresets = presets.filter((preset) => preset.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
    if (mode === 'video' || profile?.kind === 'video') return null;
    const activeProfile = profiles.find((item) => item.id === model);
    const selected = (id) => config.styles.some((layer) => layer.id === id);
    const count = config.styles.length;
    const chip = (layer) => button([layer.name || layer.id, h('span', { key: 'x', 'aria-hidden': true }, '×')], () => remove(layer.id), { key: layer.id, className: 'psn-chip', 'aria-label': `Remove ${layer.name || layer.id}` });
    return h('section', { className: 'psn-panel', 'aria-label': 'Image styles' },
      h('div', { className: 'psn-launcher' },
        button([h('span', { key: 'icon', className: 'psn-spark', 'aria-hidden': true }, '✦'), h('span', { key: 'text' }, 'Styles'), h('span', { key: 'count', className: 'psn-muted' }, count ? `${count} selected` : 'Choose a look'), h('span', { key: 'arrow', 'aria-hidden': true }, '↗')], () => setOpen(true), { className: 'psn-browse', 'aria-haspopup': 'dialog' }),
        count > 0 && h('label', { className: 'psn-check' }, h('input', { type: 'checkbox', checked: config.enabled, onChange: (event) => update(profile, { enabled: event.target.checked }) }), 'Apply')),
      count > 0 && h('div', { className: `psn-chips${config.enabled ? '' : ' psn-paused'}`, 'aria-label': 'Selected styles' }, config.styles.map(chip)),
      h('dialog', { ref: dialog, className: 'psn-dialog', 'aria-labelledby': `${controlId}-title`, onClose: () => setOpen(false), onCancel: () => setOpen(false), onClick: (event) => { if (event.target === dialog.current) setOpen(false); } },
        h('div', { className: 'psn-shell' },
          h('header', { className: 'psn-header' },
            h('div', null, h('p', { className: 'psn-eyebrow' }, 'YOUR CREATIVE DIRECTION'), h('h2', { id: `${controlId}-title` }, 'Find your look'), h('p', { className: 'psn-muted' }, 'Choose a look. Add a little color or texture. Make it yours.')),
            button('×', () => setOpen(false), { className: 'psn-close', 'aria-label': 'Close style browser' })),
          h('div', { className: 'psn-workspace' },
            h('div', { className: 'psn-library' },
              h('div', { className: 'psn-tools' },
                field('Search styles', h('input', { type: 'search', value: query, placeholder: tab === 'presets' ? 'Search your presets…' : 'Search looks, moods, materials…', onChange: (event) => setQuery(event.target.value) })),
                h('div', { className: 'psn-tabs', role: 'group', 'aria-label': 'Style type' }, Object.entries(titles).map(([value, label]) => button(label, () => { setTab(value); setCategory(''); }, { key: value, 'aria-pressed': tab === value }))),
                tab !== 'presets' && h('div', { className: 'psn-filters' },
                  field('Collection', h('select', { value: category, onChange: (event) => setCategory(event.target.value) }, h('option', { value: '' }, 'All collections'), ...categories.map((value) => h('option', { key: value, value }, labelOf(value))))),
                  button('New', () => setLatest(!latest), { 'aria-pressed': latest, className: 'psn-new', title: 'New additions' }),
                  field('Sort', h('select', { value: sort, onChange: (event) => setSort(event.target.value) }, h('option', { value: 'featured' }, 'Featured'), h('option', { value: 'name' }, 'Name A–Z'), h('option', { value: 'favorites' }, 'Favorites first')))),
                h('div', { className: 'psn-library-meta' }, h('span', { role: 'status' }, tab === 'presets' ? `${visiblePresets.length} saved ${visiblePresets.length === 1 ? 'combination' : 'combinations'}` : loading ? 'Loading your library…' : `${visible.length.toLocaleString()} ${visible.length === 1 ? counts[tab].replace(/s$/, '') : counts[tab]}`), h('span', null, tab === 'presets' ? 'Stored on this browser' : 'Abstract style cues'))),
              error && h('div', { role: 'alert', className: 'psn-error' }, h('p', null, error), button('Retry library', () => { catalogs.delete(model); setReload(reload + 1); })),
              h('div', { className: 'psn-results', 'aria-busy': loading },
                tab === 'presets' ? h('div', { className: 'psn-presets' },
                  !visiblePresets.length ? h('div', { className: 'psn-empty' }, h('h3', null, presets.length ? 'No matching presets' : 'A signature look, one click away'), h('p', null, presets.length ? 'Try another name.' : 'Combine a look, color and effects, then save the combination in Your look.'), button('Explore looks', () => { setTab('style'); setQuery(''); })) :
                  visiblePresets.map((preset) => h('article', { key: preset.id, className: 'psn-preset' },
                    h('div', { className: 'psn-preset-mark', 'aria-hidden': true }, '✦'),
                    h('div', null, h('h3', null, preset.name), h('p', { className: 'psn-muted' }, preset.selection.styles.map((layer) => layer.name).join(' · '))),
                    button('Apply', () => usePreset(preset), { 'aria-label': `Apply preset ${preset.name}` }),
                    button('×', () => removePreset(preset.id), { className: 'psn-preset-delete', 'aria-label': `Delete preset ${preset.name}` })))) :
                loading ? h('p', { className: 'psn-empty', role: 'status' }, 'Getting the latest styles…') :
                !visible.length ? h('div', { className: 'psn-empty' }, h('h3', null, tab === 'saved' && !favorites.size ? 'Keep your favorites close' : 'No styles found'), h('p', null, tab === 'saved' && !favorites.size ? 'Tap the star on any style to find it here.' : 'Try a different search or explore another collection.'), button(tab === 'saved' && !favorites.size ? 'Explore looks' : 'Reset filters', () => { resetFilters(); if (tab === 'saved' && !favorites.size) setTab('style'); })) :
                h('div', { className: 'psn-grid' }, visible.slice(0, shown).map((style) => h('article', { key: style.id, className: `psn-card${selected(style.id) ? ' is-selected' : ''}` },
                  button(h('span', { 'aria-hidden': true }, favorites.has(style.id) ? '★' : '☆'), () => favorite(style.id), { className: 'psn-save', 'aria-label': `${favorites.has(style.id) ? 'Unsave' : 'Save'} ${style.name}`, 'aria-pressed': favorites.has(style.id) }),
                  button([
                    h('span', { key: 'cue', className: `psn-cue psn-cue-${style.kind}`, 'aria-hidden': true, style: { '--psn-hue': [...style.category].reduce((n, c) => n + c.charCodeAt(0), 0) % 360 } }, h('span', null, selected(style.id) ? '✓' : style.kind === 'grade' ? '◐' : style.kind === 'modifier' ? '✧' : '◒')),
                    h('span', { key: 'category', className: 'psn-card-category' }, labelOf(style.category.split('/')[0])),
                    h('strong', { key: 'name' }, style.name), h('span', { key: 'description', className: 'psn-description' }, style.description),
                    h('span', { key: 'action', className: 'psn-card-action' }, selected(style.id) ? '✓ Selected' : style.kind !== 'modifier' && !config.mix ? style.kind === 'grade' ? 'Choose color' : 'Choose look' : 'Add to look'),
                  ], () => choose(style), { className: 'psn-card-pick', 'aria-label': `Select ${style.name}`, 'aria-pressed': selected(style.id), disabled: count >= 16 && !selected(style.id) && (config.mix || style.kind === 'modifier') })))),
                tab !== 'presets' && !loading && visible.length > shown && button(`Show more (${visible.length - shown} remaining)`, () => setShown(shown + 24), { className: 'psn-more' }))),
            h('aside', { className: `psn-selection${expanded ? ' is-expanded' : ''}`, 'aria-label': 'Your look' },
              h('div', { className: 'psn-selection-heading' }, h('h3', null, 'Your look'), button(`Your look · ${count} selected ${expanded ? '−' : '+'}`, () => setExpanded(!expanded), { className: 'psn-selection-toggle', 'aria-expanded': expanded }), count > 0 && button('Clear all', () => update(profile, { styles: [] }))),
              h('p', { className: 'psn-muted' }, profile?.capabilities?.promptFromImage ? 'Applied after your reference image is described.' : 'Applied when you generate. Your original prompt stays editable.'),
              !count && h('div', { className: 'psn-empty psn-selection-empty' }, h('span', { 'aria-hidden': true }, '✧'), h('p', null, 'Start with a look'), h('p', { className: 'psn-muted' }, 'Then explore Color and Effects for finishing touches.')),
              count > 0 && h('ol', { className: 'psn-layers' }, config.styles.map((layer, index) => h('li', { key: layer.id },
                h('div', { className: 'psn-layer-title' }, h('strong', null, layer.name || layer.id), button('×', () => remove(layer.id), { 'aria-label': `Remove ${layer.name || layer.id}` })),
                h('label', { className: 'psn-intensity', htmlFor: `${controlId}-${index}` }, 'Strength', h('output', { htmlFor: `${controlId}-${index}` }, `${Math.round(layer.intensity * 100)}%`)),
                h('input', { id: `${controlId}-${index}`, type: 'range', 'aria-label': `Strength for ${layer.name || layer.id}`, min: 0, max: 1, step: 0.05, value: layer.intensity, onChange: (event) => changeLayer(index, { intensity: Number(event.target.value) }) })))),
              count > 0 && h('form', { className: 'psn-save-preset', onSubmit: savePreset },
                field('Save this combination', h('input', { type: 'text', maxLength: 60, value: presetName, placeholder: 'Name your preset…', onChange: (event) => setPresetName(event.target.value) })),
                h('button', { type: 'submit', disabled: !presetName.trim(), 'aria-label': 'Save preset' }, 'Save')),
              notice && h('p', { className: 'psn-notice', role: 'status' }, notice),
              count > 0 && h('label', { className: 'psn-check' }, h('input', { type: 'checkbox', checked: config.enabled, onChange: (event) => update(profile, { enabled: event.target.checked }) }), 'Apply styles'),
              h('p', { className: 'psn-muted' }, config.mix ? 'Looks layer in order. Later directions take priority.' : 'One look, one color, layered effects. Your choices are saved in this browser.'),
              count >= 16 && h('p', { role: 'status' }, 'Your look has 16 layers. Remove one to add another.'),
              count > 0 && button(busy ? 'Preparing preview…' : profile?.capabilities?.promptFromImage ? 'Preview style directions' : 'Preview styled prompt', preview, { disabled: busy || !config.enabled, className: 'psn-preview-button' }),
              result && h('section', { className: 'psn-preview', 'aria-label': 'Styled prompt preview' }, h('h3', null, 'Prompt preview'), pending && h('p', { role: 'status' }, 'Selection or prompt changed. Preview again to refresh.'), h('pre', null, result.composition.positive), ...result.composition.warnings.map((warning) => h('p', { key: warning.code }, warning.message))),
              h('details', { className: 'psn-advanced' }, h('summary', null, 'Advanced controls'),
                h('label', { className: 'psn-check' }, h('input', { type: 'checkbox', checked: config.mix, onChange: (event) => update(profile, { mix: event.target.checked }) }), 'Mix styles freely'),
                field('Model profile', h('select', { value: config.model, onChange: (event) => update(profile, { model: event.target.value }) }, h('option', { value: '' }, 'Automatic for this workflow'), ...profiles.map((item) => h('option', { key: item.id, value: item.id }, item.name)))),
                field('Conflicting directions', h('select', { value: config.conflict_policy, onChange: (event) => update(profile, { conflict_policy: event.target.value }) }, h('option', { value: 'last_wins' }, 'Later style wins'), h('option', { value: 'first_wins' }, 'Earlier style wins'), h('option', { value: 'error' }, 'Report a conflict'))),
                h('fieldset', null, h('legend', null, 'Protect prompt attributes'), ...['medium', 'lighting', 'palette', 'composition', 'texture', 'mood', 'detail'].map((axis) => h('label', { key: axis, className: 'psn-check' }, h('input', { type: 'checkbox', checked: config.locked_axes.includes(axis), onChange: (event) => update(profile, { locked_axes: event.target.checked ? [...config.locked_axes, axis] : config.locked_axes.filter((item) => item !== axis) }) }), labelOf(axis)))),
                count > 1 && h('div', { className: 'psn-order' }, h('h3', null, 'Layer order'), config.styles.map((layer, index) => h('div', { key: layer.id }, h('span', null, layer.name), button('↑', () => move(index, -1), { disabled: index === 0, 'aria-label': `Move up ${layer.name}` }), button('↓', () => move(index, 1), { disabled: index === count - 1, 'aria-label': `Move down ${layer.name}` })))),
                activeProfile && h('p', { className: 'psn-muted' }, activeProfile.guidance),
                result && h('details', null, h('summary', null, 'Inspect styling'), h('pre', null, JSON.stringify({ recipe: result.composition.recipe, fingerprint: result.composition.fingerprint, trace: result.composition.trace }, null, 2)))))),
          h('footer', { className: 'psn-footer' }, h('span', { role: 'status' }, count ? `${count} selected${config.enabled ? ' · Ready to generate' : ' · Paused'}` : 'No style · Use your original prompt'), button('Done', () => setOpen(false), { className: 'psn-done' })))));
  };
}
