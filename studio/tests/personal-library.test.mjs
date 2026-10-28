import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeStyleSelection, searchStyles, studioPromptStylerSelection, restoreStudioPromptStylerSelection, getStudioPromptStylerState, restoreStudioPromptStylerState } from '../react-panel.mjs';

const layer = (id, intensity = 0.75) => ({ id, name: id, kind: 'style', intensity });

test('stored selections restore only bounded recipe fields and valid unique layers', () => {
  const selection = normalizeStyleSelection({ enabled: false, styles: [null, layer('ink', NaN), layer('ink', 2), layer('ink'), layer('wash', -1)], model: 'flux', conflict_policy: 'surprise', locked_axes: ['palette', 'script', 'palette'], mix: true, prompt: 'Never persist a prompt' });
  assert.equal(selection.enabled, false);
  assert.deepEqual(selection.styles, [layer('ink', 1), layer('wash', 0)]);
  assert.deepEqual(selection.locked_axes, ['palette']);
  assert.equal(selection.conflict_policy, 'last_wins');
  assert.equal(selection.mix, true);
  assert.equal(selection.prompt, undefined);
  assert.equal(normalizeStyleSelection({ styles: Array.from({ length: 30 }, (_, i) => layer(`style-${i}`)) }).styles.length, 16);
  assert.deepEqual(normalizeStyleSelection(null).styles, []);
});

test('search matches separate words in any metadata field and ignores accents', () => {
  const styles = [{ name: 'Cinéma noir', description: 'Etched shadows', category: 'film/monochrome', tags: ['grain', 'night'] }, { name: 'Watercolor', description: 'Soft washes', category: 'painting', tags: [] }];
  assert.deepEqual(searchStyles(styles, 'GRAIN cinema'), [styles[0]]);
  assert.deepEqual(searchStyles(styles, '  night  etched '), [styles[0]]);
  assert.deepEqual(searchStyles(styles, 'night watercolor'), []);
  assert.deepEqual(searchStyles(styles, '   '), styles);
});

test('generation restores workflow selection without prompts and honors paused/video recipes', () => {
  globalThis.localStorage = { getItem: () => JSON.stringify({ selections: { 'saved-workflow': { styles: [layer('cinema.noir')], locked_axes: ['composition'], model: 'moss-image' }, paused: { enabled: false, styles: [layer('cinema.noir')] } } }) };
  assert.deepEqual(studioPromptStylerSelection({ id: 'saved-workflow' }), { schema_version: 1, model: 'moss-image', styles: [{ id: 'cinema.noir', intensity: 0.75 }], conflict_policy: 'last_wins', locked_axes: ['composition'] });
  assert.equal(studioPromptStylerSelection({ id: 'paused' }), undefined);
  assert.equal(studioPromptStylerSelection({ id: 'saved-workflow', kind: 'video' }), undefined);
  globalThis.localStorage = { getItem: () => '{bad' };
  assert.equal(studioPromptStylerSelection({ id: 'broken' }), undefined);
  delete globalThis.localStorage;
});


test('replay restores exact ordered strengths and uses the normal persisted selection path', () => {
  const writes = new Map();
  globalThis.localStorage = { getItem: (key) => writes.get(key) || null, setItem: (key, value) => writes.set(key, value) };
  const profile = { id: 'replayed-workflow' };
  const recipe = { schema_version: 1, model: 'fibo-edit', styles: [{ id: 'cinema.noir', intensity: 0.4 }, { id: 'anime.cel', intensity: 1 }], conflict_policy: 'first_wins', locked_axes: ['composition', 'palette'] };
  restoreStudioPromptStylerSelection(profile, recipe);
  assert.deepEqual(studioPromptStylerSelection(profile), recipe);
  const saved = JSON.parse(writes.get('promptstyler-next.studiio.v1'));
  assert.deepEqual(saved.selections[profile.id].styles.map(({ id, intensity }) => ({ id, intensity })), recipe.styles);
  for (const invalid of [{ styles: Array.from({ length: 17 }, (_, i) => layer(`style-${i}`)) }, { styles: [layer('dup'), layer('dup')] }, { styles: [layer('bad', Infinity)] }, { styles: [layer('bad', -1)] }, { schema_version: 2, styles: [] }, { styles: [layer('../bad')] }, { styles: [], model: 3 }, { styles: [], locked_axes: ['unknown'] }, []]) {
    assert.throws(() => restoreStudioPromptStylerSelection(profile, invalid), TypeError);
    assert.deepEqual(studioPromptStylerSelection(profile), recipe);
  }
  restoreStudioPromptStylerSelection(profile, { styles: [{ id: 'cinema.noir' }] });
  assert.equal(studioPromptStylerSelection(profile).styles[0].intensity, 1);
  restoreStudioPromptStylerSelection(profile);
  assert.equal(studioPromptStylerSelection(profile), undefined);
  delete globalThis.localStorage;
});

test('full saved recipe restores paused state and mixing atomically', () => {
  const writes = new Map();
  globalThis.localStorage = { getItem: (key) => writes.get(key) || null, setItem: (key, value) => writes.set(key, value) };
  const profile = { id: 'complete-state' };
  const state = { enabled: false, mix: true, model: '', conflict_policy: 'first_wins', locked_axes: ['palette'], styles: [layer('cinema.noir', .4), layer('anime.cel', .8)] };
  restoreStudioPromptStylerState(profile, state);
  assert.deepEqual(getStudioPromptStylerState(profile), state);
  assert.equal(studioPromptStylerSelection(profile), undefined);
  for (const invalid of [{ styles: [layer('bad/name')] }, { model: 0 }, { model: false }, { model: 'x'.repeat(129) }]) {
    assert.throws(() => restoreStudioPromptStylerState(profile, { ...state, ...invalid }), TypeError);
  }
  assert.deepEqual(getStudioPromptStylerState(profile), state);
  assert.equal(JSON.parse(writes.get('promptstyler-next.studiio.v1')).selections[profile.id].enabled, false);
  delete globalThis.localStorage;
});

test('updating one workflow does not overwrite changes made in another tab', () => {
  const writes = new Map();
  globalThis.localStorage = { getItem: (key) => writes.get(key) || null, setItem: (key, value) => writes.set(key, value) };
  const a = { id: 'independent-a' }, b = { id: 'independent-b' };
  restoreStudioPromptStylerSelection(a, { styles: [layer('cinema.noir')] });
  restoreStudioPromptStylerSelection(b, { styles: [layer('anime.cel')] });
  const key = 'promptstyler-next.studiio.v1';
  const remote = JSON.parse(writes.get(key));
  remote.selections[b.id].styles[0].intensity = 0.2;
  writes.set(key, JSON.stringify(remote));
  restoreStudioPromptStylerSelection(a, { styles: [layer('cinema.noir', 0.4)] });
  assert.equal(JSON.parse(writes.get(key)).selections[b.id].styles[0].intensity, 0.2);
  delete globalThis.localStorage;
});
