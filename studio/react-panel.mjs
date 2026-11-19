import { PromptStylerClient } from './client.mjs';
import { studioModelProfile } from './model-profile.mjs';

const client = new PromptStylerClient({ baseUrl: '/api/promptstyler/v1' });
const selections = new Map();
const listeners = new Set();
let revision = 0;
const subscribe = (listener) => { listeners.add(listener); return () => listeners.delete(listener); };
const snapshot = () => revision;
const legacyKeyOf = (profile) => profile?.id || profile?.profileId || 'unknown';
// One look per model family, so every workflow of that family keeps the same style.
const keyOf = (profile) => profile?.family ? `family:${String(profile.family).toLowerCase().replaceAll('_', '-')}` : legacyKeyOf(profile);
const empty = () => ({ enabled: true, styles: [], model: '', conflict_policy: 'last_wins', locked_axes: [], mix: false, prompt_conflicts: 'replace' });
// Strength names map to the engine's detail tiers (0 / 0.4 / 0.75).
export const STRENGTHS = [{ label: 'Subtle', value: 0.25 }, { label: 'Balanced', value: 0.5 }, { label: 'Strong', value: 1 }];
export const strengthOf = (intensity) => intensity < 0.4 ? STRENGTHS[0] : intensity < 0.75 ? STRENGTHS[1] : STRENGTHS[2];
// Looks start complete, colors at their full grade, effects at their identity only.
export const DEFAULT_STRENGTH = { style: 1, grade: 0.5, modifier: 0.25 };
// Without "Mix looks freely": one look, one color and at most two effects.
export const MAX_EFFECTS = 2;
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
    prompt_conflicts: value.prompt_conflicts === 'keep' ? 'keep' : 'replace',
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
  if (!selections.has(key)) {
    const saved = readLibrary().selections;
    selections.set(key, normalizeStyleSelection(saved[key] ?? saved[legacyKeyOf(profile)]));
  }
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
    locked_axes: state.locked_axes, ...(state.prompt_conflicts ? { prompt_conflicts: state.prompt_conflicts } : {}),
    ...(state.model ? { model: state.model } : {}) };
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
    // Image Clone captions name a medium; the selected style always replaces it.
    prompt_conflicts: profile?.capabilities?.promptFromImage ? 'replace' : config.prompt_conflicts,
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
    || (recipe.prompt_conflicts !== undefined && !['replace', 'keep'].includes(recipe.prompt_conflicts))
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

const recentPacks = new Set(['next.computational-surfaces', 'next.weather', 'next.textile', 'next.garden-art', 'next.jewelry', 'next.lettering']);
const counts = { style: 'looks', grade: 'color grades', modifier: 'effects', saved: 'favorites' };
const titles = { style: 'Looks', grade: 'Color', modifier: 'Effects', saved: 'Favorites', presets: 'Presets' };
const labelOf = (value) => value.replaceAll('-', ' ').replaceAll('/', ' / ').replace(/\b\w/g, (letter) => letter.toUpperCase());
const featured = ['cinema.noir', 'anime.cel', 'cinema.anamorphic', 'anime.watercolor', 'computational.flow-engraving'];
const hueOf = (style) => [...(style.category || '')].reduce((sum, letter) => sum + letter.charCodeAt(0), 0) % 360;

// One authored icon family: 24px grid, 1.75 stroke, round joins.
const iconPaths = {
  styles: ['M12 3.5l1.8 4.4 4.7 1.6-4.7 1.6L12 15.5l-1.8-4.4L5.5 9.5l4.7-1.6z', 'M18.5 14.5l.8 1.9 1.9.8-1.9.8-.8 1.9-.8-1.9-1.9-.8 1.9-.8z'],
  close: ['M6.5 6.5l11 11', 'M17.5 6.5l-11 11'],
  search: ['M10.5 17.5a7 7 0 1 0 0-14 7 7 0 0 0 0 14z', 'M20 20l-4.5-4.5'],
  star: ['M12 3.8l2.5 5.1 5.6.8-4 4 .9 5.6L12 16.6l-5 2.7.9-5.6-4-4 5.6-.8z'],
  check: ['M5 12.5l4.5 4.5L19 7.5'],
  look: ['M4.5 5.5h15v13h-15z', 'M4.5 15l4.5-4.5 4 4 2.5-2.5 4 4'],
  grade: ['M12 3.8c3.3 4.1 5.6 7.1 5.6 10a5.6 5.6 0 0 1-11.2 0c0-2.9 2.3-5.9 5.6-10z', 'M12 19.4V9'],
  modifier: ['M5 19l10-10', 'M14 4.5v2', 'M19.5 10h-2', 'M17.8 6.2l1.4-1.4', 'M13.5 7.5l3 3'],
  up: ['M12 18.5v-13', 'M6.5 11L12 5.5l5.5 5.5'],
  down: ['M12 5.5v13', 'M6.5 13l5.5 5.5 5.5-5.5'],
  preset: ['M7 4.5h10v15l-5-3.5-5 3.5z'],
  chevron: ['M8 10l4 4 4-4'],
};

/** React is supplied by the embedding host; no second runtime or styling engine. */
export function createPromptStylerPanel(React) {
  const h = React.createElement;
  const icon = (name, props = {}) => h('svg', { viewBox: '0 0 24 24', width: 16, height: 16, fill: 'none', stroke: 'currentColor', strokeWidth: 1.75,
    strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true, focusable: 'false', className: `psn-icon psn-icon-${name}`, ...props },
  iconPaths[name].map((d, index) => h('path', { key: index, d })));
  const button = (label, onClick, props = {}) => h('button', { type: 'button', onClick, ...props }, label);
  const toggle = (label, checked, onChange, className = '') => h('label', { className: `psn-switch ${className}`.trim() },
    h('input', { type: 'checkbox', role: 'switch', checked, onChange: (event) => onChange(event.target.checked) }),
    h('span', { className: 'psn-switch-track', 'aria-hidden': true }), h('span', { className: 'psn-switch-label' }, label));
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
      setNotice(persistLibrary(next) ? `Saved “${name}” to Presets.` : 'Browser storage is full. This preset lasts until you close the page.');
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
      const kindOfLayer = (layer) => layer.kind || styles.find((item) => item.id === layer.id)?.kind;
      let layers = !config.mix && style.kind !== 'modifier'
        ? config.styles.filter((layer) => kindOfLayer(layer) !== style.kind)
        : config.styles;
      if (!config.mix && style.kind === 'modifier') {
        const effects = layers.filter((layer) => kindOfLayer(layer) === 'modifier');
        if (effects.length >= MAX_EFFECTS) {
          layers = layers.filter((layer) => layer.id !== effects[0].id);
          setNotice(`Replaced ${effects[0].name || effects[0].id}: up to ${MAX_EFFECTS} effects keep the look readable. Turn on Mix looks freely to stack more.`);
        }
      }
      if (layers.length >= 16) return;
      update(profile, { enabled: true, styles: [...layers, { id: style.id, name: style.name, kind: style.kind, intensity: DEFAULT_STRENGTH[style.kind] ?? 0.5 }] });
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
    const kindOf = (layer) => layer.kind || styles.find((item) => item.id === layer.id)?.kind || 'style';
    const kindIcon = (kind) => kind === 'grade' ? 'grade' : kind === 'modifier' ? 'modifier' : 'look';
    const chip = (layer) => button([h('span', { key: 'name' }, layer.name || layer.id), icon('close', { key: 'x' })], () => remove(layer.id),
      { key: layer.id, className: 'psn-chip', 'aria-label': `Remove ${layer.name || layer.id}` });
    const meta = tab === 'presets' ? `${visiblePresets.length} ${visiblePresets.length === 1 ? 'preset' : 'presets'}`
      : loading ? 'Loading styles…' : `${visible.length.toLocaleString()} ${visible.length === 1 ? counts[tab].replace(/s$/, '') : counts[tab]}`;
    const action = (style) => selected(style.id) ? 'Selected' : config.mix || style.kind === 'modifier' ? 'Add' : style.kind === 'grade' ? 'Use color' : 'Use look';
    const empty = (title, body, label, onClick, name = 'styles') => h('div', { className: 'psn-empty' },
      h('span', { className: 'psn-empty-mark', 'aria-hidden': true }, icon(name, { width: 22, height: 22 })), h('h3', null, title), h('p', null, body), label && button(label, onClick, { className: 'psn-secondary' }));
    const card = (style) => h('article', { key: style.id, className: `psn-card${selected(style.id) ? ' is-selected' : ''}` },
      button([
        h('span', { key: 'swatch', className: `psn-swatch psn-swatch-${style.kind}`, style: { '--psn-hue': hueOf(style) }, 'aria-hidden': true }, icon(selected(style.id) ? 'check' : kindIcon(style.kind))),
        h('span', { key: 'text', className: 'psn-card-text' },
          h('strong', null, style.name),
          h('span', { className: 'psn-description' }, style.description),
          h('span', { className: 'psn-card-meta' }, h('span', { className: 'psn-card-category' }, labelOf(style.category.split('/')[0])), h('span', { className: 'psn-card-action' }, action(style)))),
      ], () => choose(style), { className: 'psn-card-pick', 'aria-label': `Select ${style.name}`, 'aria-pressed': selected(style.id), disabled: count >= 16 && !selected(style.id) && (config.mix || style.kind === 'modifier') }),
      button(icon('star', { fill: favorites.has(style.id) ? 'currentColor' : 'none' }), () => favorite(style.id), { className: 'psn-save', 'aria-label': `${favorites.has(style.id) ? 'Remove' : 'Add'} ${style.name} ${favorites.has(style.id) ? 'from' : 'to'} favorites`, 'aria-pressed': favorites.has(style.id) }));
    const results = tab === 'presets'
      ? (!visiblePresets.length ? empty(presets.length ? 'No matching presets' : 'No presets yet', presets.length ? 'Try another name.' : 'Build a look, then save it under Your look to reuse it in one click.', presets.length ? '' : 'Browse looks', () => { setTab('style'); setQuery(''); }, 'preset')
        : h('div', { className: 'psn-presets' }, visiblePresets.map((preset) => h('article', { key: preset.id, className: 'psn-preset' },
          h('span', { className: 'psn-preset-mark', 'aria-hidden': true }, icon('preset')),
          h('div', { className: 'psn-preset-text' }, h('h3', null, preset.name), h('p', { className: 'psn-muted' }, preset.selection.styles.map((layer) => layer.name).join(' · '))),
          button('Apply', () => usePreset(preset), { className: 'psn-secondary', 'aria-label': `Apply preset ${preset.name}` }),
          button(icon('close'), () => removePreset(preset.id), { className: 'psn-icon-button', 'aria-label': `Delete preset ${preset.name}` })))))
      : loading ? h('div', { className: 'psn-grid', role: 'status', 'aria-label': 'Loading styles' }, Array.from({ length: 9 }, (_, index) => h('div', { key: index, className: 'psn-card psn-skeleton', 'aria-hidden': true })))
        : !visible.length ? (tab === 'saved' && !favorites.size
          ? empty('No favorites yet', 'Star any style to keep it here.', 'Browse looks', () => { resetFilters(); setTab('style'); }, 'star')
          : empty('No styles match', 'Try other words or another collection.', 'Reset filters', resetFilters, 'search'))
          : h('div', { className: 'psn-grid' }, visible.slice(0, shown).map(card));
    return h('section', { className: 'psn-panel', 'aria-label': 'Image styles' },
      h('div', { className: 'psn-launcher' },
        button([icon('styles', { key: 'icon' }), h('span', { key: 'text' }, 'Styles'), count > 0 && h('span', { key: 'count', className: `psn-count${config.enabled ? '' : ' is-paused'}` }, count)],
          () => setOpen(true), { className: 'psn-browse', 'aria-haspopup': 'dialog', 'aria-label': count ? `Styles, ${count} selected${config.enabled ? '' : ', paused'}` : 'Choose styles' }),
        count > 0 && toggle('Apply', config.enabled, (checked) => update(profile, { enabled: checked }), 'psn-launcher-switch')),
      count > 0 && h('div', { className: `psn-chips${config.enabled ? '' : ' psn-paused'}`, 'aria-label': 'Selected styles' }, config.styles.map(chip)),
      h('dialog', { ref: dialog, className: 'psn-dialog', 'aria-labelledby': `${controlId}-title`, onClose: () => setOpen(false), onCancel: () => setOpen(false), onClick: (event) => { if (event.target === dialog.current) setOpen(false); } },
        h('div', { className: 'psn-shell' },
          h('header', { className: 'psn-header' },
            h('div', { className: 'psn-heading' },
              h('h2', { id: `${controlId}-title` }, 'Styles'),
              h('p', { className: 'psn-muted' }, `Pick a look, then finish it with color and effects${activeProfile ? `. Tuned for ${activeProfile.name}` : ''}.`)),
            button(icon('close', { width: 20, height: 20 }), () => setOpen(false), { className: 'psn-icon-button psn-close', 'aria-label': 'Close styles' })),
          h('div', { className: 'psn-workspace' },
            h('div', { className: 'psn-library' },
              h('div', { className: 'psn-tools' },
                h('div', { className: 'psn-tabs', role: 'group', 'aria-label': 'Style type' }, Object.entries(titles).map(([value, label]) => button(label, () => { setTab(value); setCategory(''); }, { key: value, 'aria-pressed': tab === value }))),
                h('div', { className: 'psn-toolbar' },
                  h('label', { className: 'psn-search' }, icon('search'), h('span', { className: 'psn-sr' }, 'Search styles'),
                    h('input', { type: 'search', value: query, placeholder: tab === 'presets' ? 'Search presets' : 'Search looks, moods, materials', onChange: (event) => setQuery(event.target.value) })),
                  tab !== 'presets' && h('select', { 'aria-label': 'Collection', value: category, onChange: (event) => setCategory(event.target.value) }, h('option', { value: '' }, 'All collections'), ...categories.map((value) => h('option', { key: value, value }, labelOf(value)))),
                  tab !== 'presets' && h('select', { 'aria-label': 'Sort', value: sort, onChange: (event) => setSort(event.target.value) }, h('option', { value: 'featured' }, 'Featured'), h('option', { value: 'name' }, 'Name A–Z'), h('option', { value: 'favorites' }, 'Favorites first')),
                  tab !== 'presets' && button('New', () => setLatest(!latest), { 'aria-pressed': latest, className: 'psn-new', title: 'Show new additions only' })),
                h('div', { className: 'psn-library-meta' }, h('span', { role: 'status' }, meta), h('span', null, tab === 'presets' ? 'Stored in this browser' : 'Swatches identify styles; they are not previews'))),
              error && h('div', { role: 'alert', className: 'psn-error' }, h('p', null, `The style library did not load: ${error}`), button('Try again', () => { catalogs.delete(model); setReload(reload + 1); }, { className: 'psn-secondary' })),
              h('div', { className: 'psn-results', 'aria-busy': loading }, results,
                tab !== 'presets' && !loading && visible.length > shown && button(`Show ${Math.min(24, visible.length - shown)} more · ${visible.length - shown} left`, () => setShown(shown + 24), { className: 'psn-more psn-secondary' }))),
            h('aside', { className: `psn-selection${expanded ? ' is-expanded' : ''}`, 'aria-label': 'Your look' },
              h('div', { className: 'psn-selection-heading' },
                h('h3', null, 'Your look'),
                button([h('span', { key: 't' }, count ? `Your look · ${count} selected` : 'Your look'), icon('chevron', { key: 'c' })], () => setExpanded(!expanded), { className: 'psn-selection-toggle', 'aria-expanded': expanded }),
                count > 0 && button('Clear all', () => update(profile, { styles: [] }), { className: 'psn-link' })),
              count > 0 && toggle('Apply when generating', config.enabled, (checked) => update(profile, { enabled: checked }), 'psn-apply'),
              !count && empty('Start with a look', 'Then add a color grade and effects to finish it.', '', null, 'look'),
              count > 0 && h('ol', { className: 'psn-layers' }, config.styles.map((layer, index) => h('li', { key: layer.id },
                h('div', { className: 'psn-layer-title' }, h('span', { className: 'psn-layer-kind', 'aria-hidden': true }, icon(kindIcon(kindOf(layer)))), h('strong', null, layer.name || layer.id),
                  button(icon('close'), () => remove(layer.id), { className: 'psn-icon-button', 'aria-label': `Remove ${layer.name || layer.id}` })),
                h('div', { className: 'psn-strength', role: 'group', 'aria-label': `Strength for ${layer.name || layer.id}` },
                  STRENGTHS.map((option) => button(option.label, () => changeLayer(index, { intensity: option.value }),
                    { key: option.label, 'aria-pressed': strengthOf(layer.intensity) === option })))))),
              count >= 16 && h('p', { role: 'status', className: 'psn-notice' }, 'Your look has 16 layers. Remove one to add another.'),
              count > 0 && button(busy ? 'Preparing preview…' : profile?.capabilities?.promptFromImage ? 'Preview style directions' : 'Preview styled prompt', preview, { disabled: busy || !config.enabled, className: 'psn-preview-button psn-secondary' }),
              result && h('section', { className: 'psn-preview', 'aria-label': 'Styled prompt preview' }, h('h3', null, 'Prompt preview'), pending && h('p', { role: 'status', className: 'psn-notice' }, 'Your selection or prompt changed. Preview again to refresh.'), h('pre', null, result.composition.positive), ...result.composition.warnings.map((warning) => h('p', { key: warning.code, className: 'psn-muted' }, warning.message))),
              count > 0 && h('form', { className: 'psn-save-preset', onSubmit: savePreset },
                h('label', { className: 'psn-field' }, h('span', null, 'Save as preset'), h('input', { type: 'text', maxLength: 60, value: presetName, placeholder: 'Preset name', onChange: (event) => setPresetName(event.target.value) })),
                h('button', { type: 'submit', disabled: !presetName.trim(), className: 'psn-secondary', 'aria-label': 'Save preset' }, 'Save')),
              notice && h('p', { className: 'psn-notice', role: 'status' }, notice),
              h('details', { className: 'psn-advanced' }, h('summary', null, h('span', null, 'Advanced'), icon('chevron')),
                toggle('Mix looks freely', config.mix, (checked) => update(profile, { mix: checked })),
                !profile?.capabilities?.promptFromImage && toggle('Style wins over prompt words', config.prompt_conflicts !== 'keep', (checked) => update(profile, { prompt_conflicts: checked ? 'replace' : 'keep' })),
                h('label', { className: 'psn-field' }, h('span', null, 'Model profile'), h('select', { value: config.model, onChange: (event) => update(profile, { model: event.target.value }) }, h('option', { value: '' }, 'Automatic for this workflow'), ...profiles.map((item) => h('option', { key: item.id, value: item.id }, item.name)))),
                h('label', { className: 'psn-field' }, h('span', null, 'When styles conflict'), h('select', { value: config.conflict_policy, onChange: (event) => update(profile, { conflict_policy: event.target.value }) }, h('option', { value: 'last_wins' }, 'Later style wins'), h('option', { value: 'first_wins' }, 'Earlier style wins'), h('option', { value: 'error' }, 'Report a conflict'))),
                h('fieldset', null, h('legend', null, 'Keep from your prompt'), h('div', { className: 'psn-axes' }, ...['medium', 'lighting', 'palette', 'composition', 'texture', 'mood', 'detail'].map((axis) => h('label', { key: axis, className: 'psn-axis' }, h('input', { type: 'checkbox', checked: config.locked_axes.includes(axis), onChange: (event) => update(profile, { locked_axes: event.target.checked ? [...config.locked_axes, axis] : config.locked_axes.filter((item) => item !== axis) }) }), h('span', null, labelOf(axis)))))),
                count > 1 && h('div', { className: 'psn-order' }, h('h3', null, 'Layer order'), config.styles.map((layer, index) => h('div', { key: layer.id }, h('span', null, layer.name),
                  button(icon('up'), () => move(index, -1), { className: 'psn-icon-button', disabled: index === 0, 'aria-label': `Move up ${layer.name}` }),
                  button(icon('down'), () => move(index, 1), { className: 'psn-icon-button', disabled: index === count - 1, 'aria-label': `Move down ${layer.name}` })))),
                activeProfile && h('p', { className: 'psn-muted' }, activeProfile.guidance),
                result && h('details', { className: 'psn-inspect' }, h('summary', null, 'Inspect styling'), h('pre', null, JSON.stringify({ recipe: result.composition.recipe, fingerprint: result.composition.fingerprint, trace: result.composition.trace }, null, 2)))),
              h('p', { className: 'psn-muted psn-fineprint' }, `${profile?.capabilities?.promptFromImage ? 'Applied after your reference image is described; the selected style replaces any medium the description names.' : config.prompt_conflicts === 'keep' ? 'Applied when you generate; your prompt stays as typed.' : 'Applied when you generate; style words in your prompt that the selection also sets are replaced.'} ${config.mix ? 'Looks layer in order, and later ones take priority.' : `One look and one color at a time, up to ${MAX_EFFECTS} effects.`} Saved in this browser for this model family.`))),
          h('footer', { className: 'psn-footer' }, h('span', { role: 'status' }, count ? `${count} selected · ${config.enabled ? 'Ready to generate' : 'Paused'}` : 'No styles · Your prompt is used as typed'), button('Done', () => setOpen(false), { className: 'psn-done' })))));
  };
}
