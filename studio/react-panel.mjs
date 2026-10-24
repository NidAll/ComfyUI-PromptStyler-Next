import { PromptStylerClient } from './client.mjs';
import { studioModelProfile } from './model-profile.mjs';

const client = new PromptStylerClient({ baseUrl: '/api/promptstyler/v1' });
const selections = new Map();
const listeners = new Set();
let revision = 0;
const subscribe = (listener) => { listeners.add(listener); return () => listeners.delete(listener); };
const snapshot = () => revision;
const keyOf = (profile) => profile?.id || profile?.profileId || 'unknown';
const empty = () => ({ enabled: true, styles: [], model: '', conflict_policy: 'last_wins', locked_axes: [] });
const configOf = (profile) => selections.get(keyOf(profile)) || empty();

function update(profile, patch) {
  selections.set(keyOf(profile), { ...configOf(profile), ...patch });
  revision += 1;
  for (const listener of listeners) listener();
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

function readFavorites() {
  try {
    const value = JSON.parse(localStorage.getItem('promptstyler-next.favorites') || '[]');
    return new Set(Array.isArray(value) ? value.filter((id) => typeof id === 'string').slice(0, 256) : []);
  } catch { return new Set(); }
}

/** React is supplied by the embedding host; no second runtime or styling engine. */
export function createPromptStylerPanel(React) {
  const h = React.createElement;
  return function PromptStylerPanel({ profile, prompt = '', negative = '', mode = 'image' }) {
    React.useSyncExternalStore(subscribe, snapshot, snapshot);
    const config = configOf(profile);
    const model = config.model || studioModelProfile(profile);
    const [open, setOpen] = React.useState(false);
    const [query, setQuery] = React.useState('');
    const [category, setCategory] = React.useState('');
    const [kind, setKind] = React.useState('');
    const [favoriteOnly, setFavoriteOnly] = React.useState(false);
    const [favorites, setFavorites] = React.useState(readFavorites);
    const [catalog, setCatalog] = React.useState(null);
    const [profiles, setProfiles] = React.useState([]);
    const [styles, setStyles] = React.useState([]);
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState('');
    const [result, setResult] = React.useState(null);
    const [busy, setBusy] = React.useState(false);
    const [shown, setShown] = React.useState(9);
    const controlId = React.useId();
    const recipe = { ...studioPromptStylerSelection(profile), prompt, negative };
    const identity = JSON.stringify(recipe);
    const pending = result && result.identity !== identity;

    React.useEffect(() => {
      if (!open) return;
      let cancelled = false;
      Promise.all([client.catalog(), client.profiles()]).then(([nextCatalog, nextProfiles]) => {
        if (!cancelled) { setCatalog(nextCatalog); setProfiles(nextProfiles.items); }
      }).catch((failure) => { if (!cancelled) setError(failure.message); });
      return () => { cancelled = true; };
    }, [open]);

    React.useEffect(() => {
      if (!open) return;
      let cancelled = false;
      setLoading(true);
      const timer = setTimeout(async () => {
        setLoading(true); setError(''); setShown(9);
        try {
          const entries = [];
          for (let offset = 0; ; offset += 100) {
            const page = await client.styles({ q: query, model, category, kind, limit: 100, offset });
            if (cancelled) return;
            entries.push(...page.items);
            if (page.items.length < 100) break;
          }
          setStyles(entries);
        } catch (failure) { if (!cancelled) setError(failure.message); }
        finally { if (!cancelled) setLoading(false); }
      }, 180);
      return () => { cancelled = true; clearTimeout(timer); };
    }, [open, query, model, category, kind]);

    function favorite(id) {
      const next = new Set(favorites);
      if (next.has(id)) next.delete(id); else next.add(id);
      setFavorites(next);
      try { localStorage.setItem('promptstyler-next.favorites', JSON.stringify([...next].slice(0, 256))); }
      catch { /* Favorites remain available for this open panel. */ }
    }
    function add(style) {
      if (config.styles.some((layer) => layer.id === style.id) || config.styles.length >= 16) return;
      update(profile, { styles: [...config.styles, { id: style.id, name: style.name, intensity: 0.75 }] });
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
      try {
        const composition = await client.compose(recipe);
        setResult({ identity, composition });
      } catch (failure) { setError(failure.message); }
      finally { setBusy(false); }
    }

    if (mode === 'video' || profile?.kind === 'video') return null;
    const visible = favoriteOnly ? styles.filter((style) => favorites.has(style.id)) : styles;
    const activeProfile = profiles.find((item) => item.id === model);
    const field = (label, input) => h('label', { className: 'psn-field' }, h('span', null, label), input);
    const button = (label, onClick, props = {}) => h('button', { type: 'button', onClick, ...props }, label);
    return h('details', { className: 'psn-panel', onToggle: (event) => setOpen(event.currentTarget.open) },
      h('summary', null, h('span', null, 'Styles'), h('span', { className: 'psn-muted' }, config.enabled && config.styles.length ? `${config.styles.length} selected` : 'PromptStyler Next')),
      open && h('div', { className: 'psn-content' },
        h('label', { className: 'psn-check' }, h('input', { type: 'checkbox', checked: config.enabled, onChange: (event) => update(profile, { enabled: event.target.checked }) }), 'Use styles on Generate'),
        h('p', { className: 'psn-muted' }, profile?.capabilities?.promptFromImage ? 'Styles follow the caption created from your reference image.' : 'Your prompt stays editable. Styling is applied once when you generate.'),
        field('Search styles', h('input', { type: 'search', value: query, placeholder: 'Ink, cinema, watercolor…', onChange: (event) => setQuery(event.target.value) })),
        h('div', { className: 'psn-filters' },
          field('Category', h('select', { value: category, onChange: (event) => setCategory(event.target.value) }, h('option', { value: '' }, 'All categories'), ...(catalog?.categories || []).map((value) => h('option', { key: value, value }, value.replaceAll('/', ' / '))))),
          field('Type', h('select', { value: kind, onChange: (event) => setKind(event.target.value) }, h('option', { value: '' }, 'All types'), ...['style', 'grade', 'modifier'].map((value) => h('option', { key: value, value }, value))))),
        h('label', { className: 'psn-check' }, h('input', { type: 'checkbox', checked: favoriteOnly, onChange: (event) => setFavoriteOnly(event.target.checked) }), 'Favorites'),
        error && h('p', { role: 'alert', className: 'psn-error' }, error),
        h('div', { className: 'psn-catalog', 'aria-busy': loading },
          loading ? h('p', { role: 'status' }, 'Loading styles…') : !visible.length ? h('p', { className: 'psn-muted' }, 'No matching styles. Try another search or category.') :
            visible.slice(0, shown).map((style) => h('article', { key: style.id, className: 'psn-style' },
              h('div', null, h('strong', null, style.name), h('small', null, style.category.replaceAll('/', ' / '))),
              h('p', null, style.description),
              h('div', { className: 'psn-actions' },
                button(config.styles.some((layer) => layer.id === style.id) ? 'Added' : 'Add style', () => add(style), { disabled: config.styles.length >= 16 || config.styles.some((layer) => layer.id === style.id) }),
                button(favorites.has(style.id) ? 'Saved' : 'Save', () => favorite(style.id), { 'aria-label': `${favorites.has(style.id) ? 'Unsave' : 'Save'} ${style.name}`, 'aria-pressed': favorites.has(style.id) }))))),
        !loading && visible.length > shown && button('Show more styles', () => setShown(shown + 9)),
        config.styles.length > 0 && h('div', { className: 'psn-recipe' },
          h('h3', null, 'Style recipe'),
          h('ol', null, config.styles.map((layer, index) => h('li', { key: layer.id },
            h('strong', null, layer.name || layer.id),
            h('label', { className: 'psn-intensity', htmlFor: `${controlId}-${index}` }, 'Intensity', h('output', { htmlFor: `${controlId}-${index}` }, `${Math.round(layer.intensity * 100)}%`)),
            h('input', { id: `${controlId}-${index}`, type: 'range', min: 0, max: 1, step: 0.05, value: layer.intensity, onChange: (event) => changeLayer(index, { intensity: Number(event.target.value) }) }),
            h('div', { className: 'psn-actions' }, button('Move up', () => move(index, -1), { disabled: index === 0, 'aria-label': `Move up ${layer.name}` }), button('Move down', () => move(index, 1), { disabled: index === config.styles.length - 1, 'aria-label': `Move down ${layer.name}` }), button('Remove', () => update(profile, { styles: config.styles.filter((_, position) => position !== index) }), { 'aria-label': `Remove ${layer.name}` }))))),
          h('div', { className: 'psn-actions' }, button(busy ? 'Previewing…' : profile?.capabilities?.promptFromImage ? 'Preview style directions' : 'Preview styled prompt', preview, { disabled: busy || !config.enabled }), button('Clear styles', () => update(profile, { styles: [] })))),
        h('details', { className: 'psn-advanced' }, h('summary', null, 'Advanced styling'),
          field('Model profile', h('select', { value: config.model, onChange: (event) => update(profile, { model: event.target.value }) }, h('option', { value: '' }, `Automatic (${studioModelProfile(profile)})`), ...profiles.map((item) => h('option', { key: item.id, value: item.id }, item.name)))),
          field('Conflicting directions', h('select', { value: config.conflict_policy, onChange: (event) => update(profile, { conflict_policy: event.target.value }) }, h('option', { value: 'last_wins' }, 'Later style wins'), h('option', { value: 'first_wins' }, 'Earlier style wins'), h('option', { value: 'error' }, 'Ask me to resolve'))),
          h('fieldset', null, h('legend', null, 'Protect prompt attributes'), ...['medium', 'lighting', 'palette', 'composition', 'texture', 'mood', 'detail'].map((axis) => h('label', { key: axis, className: 'psn-check' }, h('input', { type: 'checkbox', checked: config.locked_axes.includes(axis), onChange: (event) => update(profile, { locked_axes: event.target.checked ? [...config.locked_axes, axis] : config.locked_axes.filter((item) => item !== axis) }) }), axis))),
          activeProfile && h('p', { className: 'psn-muted' }, activeProfile.guidance)),
        result && h('section', { className: 'psn-preview', 'aria-label': 'Styled prompt preview' },
          h('h3', null, 'Prompt preview'),
          pending && h('p', { role: 'status', className: 'psn-muted' }, 'Recipe or prompt changed. Preview again to refresh.'),
          h('pre', null, result.composition.positive),
          ...result.composition.warnings.map((warning) => h('p', { key: warning.code, className: 'psn-muted' }, warning.message)),
          h('details', null, h('summary', null, 'Inspect styling'), h('pre', null, JSON.stringify({ recipe: result.composition.recipe, fingerprint: result.composition.fingerprint, trace: result.composition.trace }, null, 2))))));
  };
}
