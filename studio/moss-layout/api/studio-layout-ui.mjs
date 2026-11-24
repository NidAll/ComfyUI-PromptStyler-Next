/** MOSS layout builder for the Studio composer (2026-11-18; tools added 2026-11-24).
 *
 * A full-screen editor for MOSS-Image Layout prompts: a summary (caption, meta, canvas, palette) and
 * boxes labelled object, character or text, drawn on a canvas with the generation's exact width and
 * height (read from the composer's saved draft). It has no serializer of its own: every change is
 * compiled by the MOSS Image Layout Prompt Builder node through /api/moss-layout/*, which writes the
 * official one-line prompt ({summary, items, bbox_coord_space: "abs_centralized", bbox_format: "yxyx"}).
 * "Use layout" puts that prompt in the composer; reopening imports it back for editing.
 *
 * 2026-11-24: placement presets, meta suggestions, a reference image to trace (file, drop or paste;
 * never sent with the prompt), editor-only box locks, Shift/Ctrl resize, golden-ratio guides, zoom and
 * pan, a box menu, alignment, layout import (JSON or a PNG that carries one) and .json export.
 * Layouts that reach past the canvas are scaled down uniformly on import instead of being clipped.
 *
 * 2026-11-24 (AI): an AI menu runs /api/moss-layout-ai (studio-layout-assist.mjs): LFM3-VL writes and edits
 * layouts and describes boxes, WeVisOne-VL finds objects and lettering in the reference. The reference is
 * sent as the canvas shows it (same crop or letterbox), so its boxes land where the user sees them.
 * Results replace the layout on the Undo stack; locked boxes are kept. Ideogram 4 caption JSON imports
 * (the MOSS node converts it) and exports ("Copy as Ideogram 4").
 */
const AUTOSAVE = 'heiss.mossLayout.v1';
const SIZES = 'heiss.mossLayout.sizes.v1';
const KINDS = [['object', 'Object', 'O'], ['character', 'Character', 'C'], ['text', 'Text', 'T']];
const CANVASES = [['single', 'Single'], ['multi_panel', 'Panels'], ['collage', 'Collage']];
const SNAP_PX = 7;
const CJK = /[ᄀ-ᇿ⺀-鿿가-힯豈-﫿＀-￯]/;
const HEX = /^#[0-9a-f]{6}$/i;
const MAX_SIDE = 16384;
const PHI = 0.6180339887;
const GUIDES = [['off', 'No guides'], ['thirds', 'Rule of thirds'], ['golden', 'Golden ratio'], ['both', 'Thirds and golden ratio']];
const GUIDE_LINES = { off: [], thirds: [1 / 3, 2 / 3], golden: [1 - PHI, PHI], both: [1 / 3, 2 / 3, 1 - PHI, PHI] };
const ZOOM_STEPS = [1, 1.5, 2, 3, 4, 6, 8];
const FITS = [['cover', 'Fill'], ['contain', 'Fit'], ['fill', 'Stretch'], ['actual', '1:1']];

/** Common MOSS-Image summary.meta genres, offered while typing in Meta. */
const META_SUGGESTIONS = [
  ['Design and print', ['poster', 'minimal graphic design', 'editorial layout', 'magazine cover', 'book cover', 'album art', 'vintage travel poster', 'typographic poster']],
  ['Commercial', ['product campaign', 'studio photography', 'advertisement', 'e-commerce banner', 'packaging mockup', 'social media post']],
  ['Information and UI', ['infographic', 'knowledge graphic', 'diagram', 'ui mockup', 'slide deck', 'map']],
  ['Illustration and comics', ['illustration', 'anime illustration', 'comic', 'four panels', 'manga', "children's book illustration", 'flat vector art', 'concept art']],
  ['Photography and film', ['cinematic still', 'portrait photography', 'street photography', 'macro photography', 'landscape photography', 'fashion editorial']]
];

/** One-box placements: [id, label, columns, rows, [column, row]]; "centre" is half the canvas area. */
const PLACE_ONE = [
  ['fill', 'Fill', 1, 1, [0, 0]], ['centre', 'Centre', 0, 0, null],
  ['top-left', 'Top left', 2, 2, [0, 0]], ['top-right', 'Top right', 2, 2, [1, 0]],
  ['bottom-left', 'Bottom left', 2, 2, [0, 1]], ['bottom-right', 'Bottom right', 2, 2, [1, 1]],
  ['left', 'Left half', 2, 1, [0, 0]], ['right', 'Right half', 2, 1, [1, 0]],
  ['top', 'Top half', 1, 2, [0, 0]], ['bottom', 'Bottom half', 1, 2, [0, 1]]
];
const PLACE_SPLIT = [['2c', '2 columns', 2, 1], ['2r', '2 rows', 1, 2], ['3c', '3 columns', 3, 1], ['3r', '3 rows', 1, 3],
  ['2x2', '2 × 2 grid', 2, 2], ['4c', '4 columns', 4, 1], ['4r', '4 rows', 1, 4], ['3x3', '3 × 3 grid', 3, 3]];

const STARTERS = [
  { id: 'poster', name: 'Poster', hint: 'Title, hero illustration, footer line', canvas: 'single', meta: ['poster'],
    caption: 'A minimalist travel poster on a warm cream background, with a flat layered illustration, generous margins and confident modern typography.',
    items: [
      ['text', 0.12, 0.08, 0.76, 0.13, 'Large dark-blue uppercase title, centered, wide letter spacing, no backing panel.', 'EXPLORE'],
      ['object', 0.18, 0.27, 0.64, 0.56, 'A flat illustration of blue mountains with layered ridges, a pale sun and a winding trail.'],
      ['text', 0.28, 0.88, 0.44, 0.05, 'Small dark-blue sans-serif line, evenly spaced.', 'Summer trails 2026']
    ] },
  { id: 'product', name: 'Product hero', hint: 'Product left, headline and copy right', canvas: 'single', meta: ['product campaign', 'studio photography'],
    caption: 'A calm studio campaign photograph for a handmade ceramic cup, ivory backdrop, soft side light and restrained dark-green typography.',
    items: [
      ['object', 0.08, 0.2, 0.44, 0.66, 'An ivory ceramic cup with a rounded handle, fine speckled glaze and a soft contact shadow, at a three-quarter angle.'],
      ['text', 0.58, 0.28, 0.34, 0.14, 'Large dark-green serif headline in crisp, moderately heavy lettering.', 'Slow mornings'],
      ['text', 0.58, 0.48, 0.32, 0.1, 'Smaller dark-green supporting copy on two lines, comfortably legible.', 'Hand-thrown stoneware\nmade to be used daily']
    ] },
  { id: 'portrait', name: 'Character', hint: 'A figure in a setting, with a nameplate', canvas: 'single', meta: ['illustration'],
    caption: 'A cinematic fantasy illustration at dusk, painterly brushwork, warm rim light against a cool misty forest.',
    items: [
      ['object', 0, 0, 1, 1, 'A misty pine forest at dusk with shafts of amber light and drifting fog.'],
      ['character', 0.26, 0.14, 0.48, 0.82, 'A young knight in weathered silver armour holding a lantern, calm expression, full body, three-quarter view.'],
      ['text', 0.3, 0.06, 0.4, 0.06, 'Elegant engraved gold serif lettering.', 'THE LANTERN BEARER']
    ] },
  { id: 'panels', name: 'Four panels', hint: 'A 2 × 2 comic page', canvas: 'multi_panel', meta: ['comic', 'four panels'],
    caption: 'A four-panel comic page in clean ink lines and flat pastel colors about a cat discovering a cardboard box.',
    items: [
      ['object', 0.03, 0.03, 0.455, 0.455, 'Panel one: an orange cat stares at a large empty cardboard box in a sunny living room.'],
      ['object', 0.515, 0.03, 0.455, 0.455, 'Panel two: the cat cautiously sniffs the edge of the box, tail raised.'],
      ['object', 0.03, 0.515, 0.455, 0.455, 'Panel three: the cat leaps into the box mid-air, paws stretched forward.'],
      ['object', 0.515, 0.515, 0.455, 0.455, 'Panel four: only the cat\'s ears and eyes peek out of the box, looking delighted.']
    ] }
];

const uid = () => `layer_${Math.random().toString(36).slice(2, 10)}`;
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const plain = (state) => JSON.parse(JSON.stringify(state));
const splitList = (text) => String(text || '').split(/[,\n]/).map((item) => item.trim()).filter(Boolean);
const gcd = (a, b) => (b ? gcd(b, a % b) : a);
const pad2 = (value) => String(value).padStart(2, '0');

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key === 'style') Object.assign(node.style, value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) if (child != null && child !== false) node.append(child);
  return node;
}

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

const ICONS = {
  layout: 'M4 4h16v16H4zM4 10h16M10 10v10',
  close: 'M6 6l12 12M18 6L6 18',
  undo: 'M9 7H4V2M4 7c2-2.8 5-4.5 8.5-4.5A8.5 8.5 0 1 1 4.3 14',
  redo: 'M15 7h5V2M20 7c-2-2.8-5-4.5-8.5-4.5A8.5 8.5 0 1 0 19.7 14',
  grid: 'M9 3v18M15 3v18M3 9h18M3 15h18',
  magnet: 'M6 3v8a6 6 0 0 0 12 0V3M6 7h4M14 7h4',
  copy: 'M9 9h11v11H9zM5 15H4V4h11v1',
  save: 'M12 4v11M7 10l5 5 5-5M5 20h14',
  open: 'M14 3H6v18h12V7zM14 3v4h4M12 17v-7M9 13l3-3 3 3',
  image: 'M4 5h16v14H4zM4 16l5-5 4 4 2.5-2.5L20 17M15.5 9.5h.01',
  front: 'M12 19V5M5 12l7-7 7 7',
  back: 'M12 5v14M5 12l7 7 7-7',
  dup: 'M8 8h12v12H8zM4 16V4h12',
  trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13',
  check: 'M5 12l5 5 9-10',
  lock: 'M7 11V8a5 5 0 0 1 10 0v3M5 11h14v10H5z',
  unlock: 'M7 11V8a5 5 0 0 1 9.6-1.9M5 11h14v10H5z',
  place: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  plus: 'M12 5v14M5 12h14',
  minus: 'M5 12h14',
  chevron: 'M7 10l5 5 5-5',
  'align-left': 'M4 3v18M8 7h11v4H8zM8 13h6v4H8z',
  'align-centre': 'M12 3v18M6 7h12v4H6zM8 13h8v4H8z',
  'align-right': 'M20 3v18M5 7h11v4H5zM10 13h6v4h-6z',
  'align-top': 'M3 4h18M7 8h4v11H7zM13 8h4v6h-4z',
  'align-middle': 'M3 12h18M7 6h4v12H7zM13 8h4v8h-4z',
  'align-bottom': 'M3 20h18M7 5h4v11H7zM13 10h4v6h-4z',
  spark: 'M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.4z',
  share: 'M4 13v7h16v-7M12 3v12M7 8l5-5 5 5',
  stop: 'M7 7h10v10H7z',
  text: 'M5 6V4h14v2M12 4v16M9 20h6',
  target: 'M12 3v4M12 17v4M3 12h4M17 12h4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z',
  pen: 'M4 20l4-1 11-11-3-3L5 16zM14 6l3 3'
};

function icon(name) {
  const svg = svgEl('svg', { viewBox: '0 0 24 24', class: 'slb-icon', 'aria-hidden': 'true' });
  const filled = name === 'spark';
  svg.append(svgEl('path', { d: ICONS[name], fill: filled ? 'currentColor' : 'none', stroke: filled ? 'none' : 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
  return svg;
}

async function call(operation, body) {
  const response = await fetch(`/api/moss-layout/${operation}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(data.error || `Layout check failed (${response.status}).`), { restart: !!data.restart, offline: response.status === 503 });
  return data;
}

/** {items, label counts} when the text is a compiled or draft MOSS layout; null otherwise. */
export function layoutInfo(text) {
  if (typeof text !== 'string' || !text.trim().startsWith('{')) return null;
  try {
    const value = JSON.parse(text);
    if (!value || !Array.isArray(value.items) || !value.summary || !value.bbox_coord_space) return null;
    return { items: value.items.length, text: value.items.filter((item) => item?.label === 'text').length };
  } catch { return null; }
}

/** The first MOSS layout inside a value: a layout string, or JSON that holds one (a ComfyUI graph, a project file). */
export function findLayout(value, depth = 0) {
  if (value == null || depth > 8) return null;
  if (typeof value === 'string') {
    const text = value.trim();
    if (!text.startsWith('{')) return null;
    if (layoutInfo(text)) return text;
    try { return findLayout(JSON.parse(text), depth + 1); } catch { return null; }
  }
  if (typeof value !== 'object') return null;
  if (!Array.isArray(value) && Array.isArray(value.items) && value.summary && value.bbox_coord_space) return JSON.stringify(value);
  if (foreignKind(value)) return JSON.stringify(value);
  for (const child of Object.values(value)) {
    const hit = findLayout(child, depth + 1);
    if (hit) return hit;
  }
  return null;
}

/**
 * A compiled layout carries no size, so its centred pixel boxes are read on the current canvas. When a box
 * reaches past that canvas (a layout made at another size), return the smallest same-shaped canvas that
 * holds every box, in multiples of 16, so the import scales it down uniformly instead of clipping it.
 */
export function inferSourceSize(text, size) {
  let doc;
  try { doc = JSON.parse(text); } catch { return null; }
  if (!doc || !Array.isArray(doc.items) || !doc.items.length || foreignKind(doc)) return null;
  if ((doc.bbox_coord_space ?? 'abs_centralized') !== 'abs_centralized' || (doc.bbox_format ?? 'yxyx') !== 'yxyx') return null;
  let reachX = 0, reachY = 0;
  for (const item of doc.items) {
    const box = item?.bbox;
    if (!Array.isArray(box) || box.length !== 4 || !box.every(Number.isFinite)) return null;
    reachY = Math.max(reachY, Math.abs(box[0]), Math.abs(box[2]));
    reachX = Math.max(reachX, Math.abs(box[1]), Math.abs(box[3]));
  }
  const { width, height } = size;
  if (reachX <= width / 2 + 1 && reachY <= height / 2 + 1) return null;
  const scale = Math.max((2 * reachX) / width, (2 * reachY) / height);
  const up = (value) => clamp(Math.ceil(value / 16) * 16, 16, MAX_SIDE);
  return { width: up(width * scale), height: up(height * scale) };
}

/**
 * Some editors add their own keys to a compiled layout (BBox Studio: top-level width/height, item color,
 * locked, aspect_locked). Use the size and locks, and drop the rest so the import stays warning-free.
 * Drafts (abs + xyxy) carry width/height by design and are left alone.
 */
export function normalizeLayout(text) {
  let doc;
  try { doc = JSON.parse(text); } catch { return { text, size: null, locks: [] }; }
  if (!doc || typeof doc !== 'object' || doc.bbox_coord_space !== 'abs_centralized' || !Array.isArray(doc.items)) return { text, size: null, locks: [] };
  const extras = ['color', 'locked', 'aspect_locked'];
  const up = (value) => clamp(Math.ceil(value / 16) * 16, 16, MAX_SIDE);
  const size = Number.isFinite(doc.width) && Number.isFinite(doc.height) && doc.width >= 16 && doc.height >= 16 ? { width: up(doc.width), height: up(doc.height) } : null;
  const locks = doc.items.map((item) => item?.locked === true);
  const extra = 'width' in doc || 'height' in doc || doc.items.some((item) => item && typeof item === 'object' && extras.some((key) => key in item));
  if (!extra) return { text, size, locks };
  const { width, height, ...clean } = doc;
  clean.items = doc.items.map((item) => {
    if (!item || typeof item !== 'object') return item;
    const copy = { ...item };
    for (const key of extras) delete copy[key];
    return copy;
  });
  return { text: JSON.stringify(clean), size, locks };
}

/** Grid cells as editor fractions, with gutters (fractions of width and height) around and between them. */
export function gridRects(columns, rows, cells, gapX = 0, gapY = 0) {
  const cellW = (1 - gapX * (columns + 1)) / columns, cellH = (1 - gapY * (rows + 1)) / rows;
  return cells.map(([column, row]) => ({ x: gapX + column * (cellW + gapX), y: gapY + row * (cellH + gapY), w: cellW, h: cellH }));
}

// ---------- AI assistant and Ideogram helpers (2026-11-24) ----------
const GRID = 1000;
// 896 px: WeVisOne finds the same boxes as at 1152 px a little faster, and LFM3 reads images at 512 px anyway.
const AI_SIDE = 896;
const onGrid = (value) => Math.round(clamp(value, 0, 1) * GRID);

/** 'ideogram' for an Ideogram 4 caption, 'assistant' for a Layout Assist answer (xyxy on 0-1000); the MOSS node converts both. */
export function foreignKind(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const scene = value.compositional_deconstruction;
  if (scene && typeof scene === 'object' && !Array.isArray(scene) && (scene.elements == null || Array.isArray(scene.elements))) return 'ideogram';
  if (value.grid === 'xyxy-1000' && Array.isArray(value.items)) return 'assistant';
  return null;
}
const foreignText = (text) => { try { return foreignKind(JSON.parse(text)); } catch { return null; } };

/** Editor regions (front first, fractions) -> assistant items (back first, [x1, y1, x2, y2] on 0-1000). */
export function regionsToGrid(regions) {
  return regions.slice().reverse().map((region) => ({ label: region.kind, caption: String(region.description || '').trim(),
    bbox: [onGrid(region.x), onGrid(region.y), onGrid(region.x + region.w), onGrid(region.y + region.h)],
    ...(region.kind === 'text' && String(region.text || '').trim() ? { text: region.text.trim() } : {}) }));
}

/** [x1, y1, x2, y2] on 0-1000 -> an editor rectangle (fractions), at least one grid step wide. */
export function gridRect(bbox) {
  const [x1, y1, x2, y2] = bbox.map((value) => clamp(Number(value) / GRID, 0, 1));
  return { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.max(Math.abs(x2 - x1), 1 / GRID), h: Math.max(Math.abs(y2 - y1), 1 / GRID) };
}

/** Intersection over union of two editor rectangles. */
export function overlap(a, b) {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x), h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  if (w <= 0 || h <= 0) return 0;
  const inter = w * h;
  return inter / (a.w * a.h + b.w * b.h - inter);
}

/** Locked boxes survive an AI rewrite: each takes the place of the new box it overlaps most (IoU at least 0.5), or goes in front. */
export function keepLocked(previous, next) {
  const out = next.slice(), front = [];
  for (const lock of previous.filter((region) => region.locked)) {
    let best = -1, score = 0.5;
    out.forEach((region, index) => { if (region.locked) return; const value = overlap(lock, region); if (value >= score) { best = index; score = value; } });
    if (best >= 0) out[best] = lock; else front.push(lock);
  }
  return [...front, ...out];
}

/** An edited box that still sits where an old one was keeps that box's colours when the answer gave none. */
export function carryColours(previous, next) {
  return next.map((region) => {
    if (region.colors?.length) return region;
    const match = previous.find((old) => old.colors?.length && old.kind === region.kind && overlap(old, region) >= 0.6);
    return match ? { ...region, colors: [...match.colors] } : region;
  });
}

/** OCR word boxes ({label, bbox} on 0-1000) -> one text line each, top to bottom, merged in canvas pixels. */
export function ocrLines(words, { width, height }, limit = 6) {
  const items = (words || []).map(({ label, bbox }) => ({ text: String(label || '').trim(),
    x1: (bbox[0] * width) / GRID, y1: (bbox[1] * height) / GRID, x2: (bbox[2] * width) / GRID, y2: (bbox[3] * height) / GRID }))
    .filter((item) => item.text && item.x2 > item.x1 && item.y2 > item.y1)
    .sort((a, b) => a.x1 - b.x1);
  const lines = [];
  for (const item of items) {
    const cy = (item.y1 + item.y2) / 2, h = item.y2 - item.y1;
    const line = lines.find((row) => {
      const rh = row.y2 - row.y1, gap = item.x1 - row.x2;
      return Math.abs(cy - (row.y1 + row.y2) / 2) < 0.5 * Math.max(h, rh) && gap > -0.5 * h && gap < 1.5 * Math.max(h, rh);
    });
    if (line) { line.words.push(item.text); line.x2 = Math.max(line.x2, item.x2); line.y1 = Math.min(line.y1, item.y1); line.y2 = Math.max(line.y2, item.y2); }
    else lines.push({ ...item, words: [item.text] });
  }
  lines.sort((a, b) => a.y1 - b.y1 || a.x1 - b.x1);
  return lines.slice(0, limit).map((line) => ({ text: line.words.join(' '),
    bbox: [Math.round((line.x1 / width) * GRID), Math.round((line.y1 / height) * GRID), Math.round((line.x2 / width) * GRID), Math.round((line.y2 / height) * GRID)] }));
}

/** The builder's state as an Ideogram 4 caption: elements front first, bbox [ymin, xmin, ymax, xmax] on 0-1000. Characters become objects. */
export function toIdeogram(state) {
  const hexes = (list) => (list || []).filter((value) => HEX.test(value)).map((value) => value.toUpperCase()).slice(0, 5);
  const doc = { high_level_description: String(state.caption || '').trim() };
  const palette = hexes(state.palette);
  if (state.meta?.length || palette.length) doc.style_description = { aesthetics: state.meta.join(', '), lighting: '', medium: '', art_style: '', ...(palette.length ? { color_palette: palette } : {}) };
  doc.compositional_deconstruction = { background: '', elements: state.regions.map((region) => {
    const text = region.kind === 'text' && String(region.text || '').trim() ? region.text : '';
    const element = { type: text ? 'text' : 'obj', bbox: [onGrid(region.y), onGrid(region.x), onGrid(region.y + region.h), onGrid(region.x + region.w)] };
    if (text) element.text = text;
    element.desc = String(region.description || '').trim();
    const colours = hexes(region.colors);
    if (colours.length) element.color_palette = colours;
    return element;
  }) };
  return doc;
}

/** Where the reference lands on an `out`-sized copy of the canvas, matching the board's object-fit (1:1 = image pixels on canvas pixels). */
/** A clipboard image as a named file ("Pasted image.png"); browsers call every pasted image "image.png". */
export function pastedFile(blob) {
  const type = blob.type || 'image/png';
  return new File([blob], `Pasted image.${type.split('/')[1]?.replace('jpeg', 'jpg') || 'png'}`, { type });
}

export function fitRect(image, size, fit, out) {
  if (fit === 'fill') return { x: 0, y: 0, w: out.width, h: out.height };
  const k = fit === 'actual' ? out.width / size.width
    : fit === 'contain' ? Math.min(out.width / image.width, out.height / image.height) : Math.max(out.width / image.width, out.height / image.height);
  const w = image.width * k, h = image.height * k;
  return { x: (out.width - w) / 2, y: (out.height - h) / 2, w, h };
}

const allCells = (columns, rows) => Array.from({ length: columns * rows }, (_, index) => [index % columns, Math.floor(index / columns)]);

async function inflate(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** Text values of a PNG's tEXt, zTXt and iTXt chunks (ComfyUI stores its graph there; BBox Studio its layout). */
export async function pngTexts(buffer) {
  const bytes = new Uint8Array(buffer);
  const signature = [137, 80, 78, 71, 13, 10, 26, 10];
  if (bytes.length < 8 || signature.some((value, index) => bytes[index] !== value)) return [];
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const utf8 = new TextDecoder();
  const texts = [];
  for (let pos = 8; pos + 12 <= bytes.length;) {
    const length = view.getUint32(pos);
    const type = String.fromCharCode(...bytes.subarray(pos + 4, pos + 8));
    const data = bytes.subarray(pos + 8, Math.min(bytes.length, pos + 8 + length));
    pos += 12 + length;
    try {
      const zero = data.indexOf(0);
      if (type === 'tEXt' && zero >= 0) texts.push(utf8.decode(data.subarray(zero + 1)));
      else if (type === 'zTXt' && zero >= 0) texts.push(utf8.decode(await inflate(data.subarray(zero + 2))));
      else if (type === 'iTXt' && zero >= 0) {
        const compressed = data[zero + 1] === 1;
        let at = data.indexOf(0, zero + 3); at = data.indexOf(0, at + 1);
        if (at < 0) continue;
        const body = data.subarray(at + 1);
        texts.push(utf8.decode(compressed ? await inflate(body) : body));
      } else if (type === 'IEND') break;
    } catch { /* an unreadable chunk is skipped */ }
  }
  return texts;
}

/** The composer's current generation size, from the draft it saves 300 ms after every change. */
export function studioSize() {
  try {
    const draft = JSON.parse(localStorage.getItem('heiss-ui-draft') || '{}');
    const width = Number(draft.width), height = Number(draft.height);
    if (Number.isInteger(width) && Number.isInteger(height) && width > 0 && height > 0) return { width, height };
  } catch { /* fall through */ }
  return { width: 1024, height: 1024 };
}

function readStore(key, fallback) { try { return JSON.parse(localStorage.getItem(key) || '') ?? fallback; } catch { return fallback; } }
function writeStore(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* per-device convenience */ } }
const fingerprint = (text) => { let h = 2166136261; for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619); return (h >>> 0).toString(36) + text.length; };
/** The size each applied layout was made for, so a later size change rescales it instead of clipping. */
function rememberSize(prompt, size) {
  const sizes = readStore(SIZES, {}) || {};
  sizes[fingerprint(prompt)] = [size.width, size.height, Date.now()];
  const entries = Object.entries(sizes).sort((a, b) => b[1][2] - a[1][2]).slice(0, 40);
  writeStore(SIZES, Object.fromEntries(entries));
}
const knownSize = (prompt) => { const hit = (readStore(SIZES, {}) || {})[fingerprint(prompt)]; return hit ? { width: hit[0], height: hit[1] } : null; };

/** The reference image lives for the page session (an object URL), so reopening the builder keeps it. */
let sessionReference = null;

/** The stylesheet, loaded once; the builder waits for it (up to 1.5 s) so it never flashes unstyled. */
function ensureStyles() {
  let link = document.querySelector('link[data-studio-layout]');
  if (!link) {
    link = el('link', { rel: 'stylesheet', href: '/studio-assets/studio-layout-ui.css', 'data-studio-layout': true });
    link.ready = new Promise((resolve) => { link.addEventListener('load', resolve, { once: true }); link.addEventListener('error', resolve, { once: true }); setTimeout(resolve, 1500); });
    document.head.append(link);
  }
  return link.ready || Promise.resolve();
}

/** Open the builder. Resolves nothing; calls onApply(prompt) when the user chooses Use layout. */
export function openLayoutBuilder({ prompt = '', onApply, onClose } = {}) {
  const size = studioSize();
  const builder = new LayoutBuilder({ prompt, size, onApply, onClose });
  void ensureStyles().then(() => { if (!builder.cancelled) builder.open(); });
  return () => { builder.cancelled = true; if (builder.root?.isConnected) builder.close(true); else builder.onClose?.(); };
}

class LayoutBuilder {
  constructor({ prompt, size, onApply, onClose }) {
    this.initialPrompt = prompt;
    this.size = size;
    this.onApply = onApply;
    this.onClose = onClose;
    this.state = { caption: '', meta: [], canvas: 'single', palette: [], regions: [] };
    this.selected = null;
    this.tool = 'object';
    const legacyGrid = readStore('heiss.mossLayout.grid', true) !== false;
    this.guideMode = GUIDE_LINES[readStore('heiss.mossLayout.guides', '')] ? readStore('heiss.mossLayout.guides', '') : legacyGrid ? 'thirds' : 'off';
    this.snap = readStore('heiss.mossLayout.snap', true) !== false;
    this.gutters = readStore('heiss.mossLayout.gutters', true) !== false;
    this.refView = { opacity: 0.45, fit: 'cover', ...(readStore('heiss.mossLayout.ref', {}) || {}) };
    this.reference = sessionReference;
    this.zoom = 1;
    this.history = []; this.future = [];
    this.result = null; this.error = null; this.revision = 0;
    this.boxes = new Map();
    this.ai = null; this.aiLast = null; this.aiModels = null; this.aiRequest = ''; this.born = null;
    this.aiLabels = readStore('heiss.mossLayout.aiLabels', '') || ''; this.aiFindText = readStore('heiss.mossLayout.aiText', true) !== false;
    this.events = new AbortController();
    this.returnFocus = document.activeElement;
  }

  listen(target, type, handler, options = {}) { target.addEventListener(type, handler, { ...options, signal: this.events.signal }); }

  // ---------- lifecycle ----------
  async open() {
    this.build();
    document.body.append(this.root);
    // Everything behind the builder is inert while it is open, so Tab and screen readers stay inside.
    this.inerted = [...document.body.children].filter((node) => node !== this.root && !node.inert);
    for (const node of this.inerted) node.inert = true;
    document.documentElement.classList.add('slb-open');
    requestAnimationFrame(() => this.root.classList.add('is-in'));
    this.layoutStage();
    this.notice(`Canvas ${this.size.width} × ${this.size.height}, your Studio size. Draw boxes for what must sit in a place; describe the rest in the summary.`);
    await this.load();
    this.commit(true);
    this.renderAll();
    this.captionInput.focus({ preventScroll: true });
  }

  async load() {
    const text = this.initialPrompt || '';
    const info = layoutInfo(text) || (foreignText(text) ? { foreign: true } : null);
    if (info) {
      try {
        const { imported, note } = await this.readLayout(text);
        this.fromImport(imported);
        if (note) this.notice(note);
        return;
      } catch (error) { this.fail(error); }
    }
    this.state.caption = text.trim().startsWith('{') ? '' : text;
    const saved = readStore(AUTOSAVE, null);
    if (saved?.state?.regions?.length && !info) this.offerRestore(saved);
  }

  /** Import a layout through the node, scaled from its remembered or inferred size to this canvas. */
  async readLayout(original) {
    const { width, height } = this.size;
    if (foreignText(original)) {
      // Ideogram 4 and assistant layouts are on a 0-1000 grid: the node places them on this canvas.
      const imported = await call('import', { prompt: original, width, height });
      const warnings = (imported.warnings || []).filter((warning) => !/^Converted from/.test(warning));
      const source = (imported.warnings || []).find((warning) => /^Converted from/.test(warning));
      return { imported, note: [source, warnings[0], warnings.length > 1 ? `(and ${warnings.length - 1} more)` : ''].filter(Boolean).join(' ') };
    }
    const { text, size: stated, locks } = normalizeLayout(original);
    const remembered = knownSize(original) || stated;
    const inferred = remembered ? null : inferSourceSize(text, this.size);
    const from = remembered || inferred || this.size;
    const imported = await call('import', { prompt: text, width: from.width, height: from.height });
    // The node lists items back to front and returns regions front first.
    const regions = imported.regions || [];
    if (locks.some(Boolean) && locks.length === regions.length) regions.forEach((region, index) => { if (locks[locks.length - 1 - index]) region.locked = true; });
    const warnings = imported.warnings || [];
    let note = '';
    if (inferred) note = `This layout reaches past ${width} × ${height}, so it was scaled to ${Math.round((100 * width) / imported.width)}% to fit, keeping its proportions.`;
    else if (imported.width !== width || imported.height !== height) note = `This layout was made for ${imported.width} × ${imported.height}; its boxes were scaled to ${width} × ${height}.`;
    else if (warnings.length) note = warnings.length > 1 ? `${warnings[0]} (and ${warnings.length - 1} more)` : warnings[0];
    return { imported, note };
  }

  fromImport(imported) {
    this.state = { caption: imported.summary_caption || '', meta: splitList(imported.meta), canvas: imported.canvas || 'single',
      palette: splitList(imported.palette), regions: (imported.regions || []).map((region) => ({ ...region, id: region.id || uid(), tags: region.tags || [], colors: region.colors || [] })) };
  }

  close(silent = false) {
    if (this.closed) return;
    this.closed = true;
    clearTimeout(this.compileTimer);
    if (this.ai) this.cancelAi(true);
    this.closePopover();
    this.events.abort();
    document.documentElement.classList.remove('slb-open');
    for (const node of this.inerted || []) node.inert = false;
    this.root.classList.remove('is-in');
    this.root.classList.add('is-out');
    setTimeout(() => this.root.remove(), 220);
    if (!silent) this.returnFocus?.focus?.({ preventScroll: true });
    this.onClose?.();
  }

  requestClose() {
    if (this.dirty() && !this.confirmingClose) {
      this.confirmingClose = true;
      this.notice('Close without using this layout? Press Esc or Close again to discard; it stays saved on this device.', 'warning');
      setTimeout(() => { this.confirmingClose = false; }, 4000);
      return;
    }
    this.close();
  }

  dirty() { return this.history.length > 1; }

  // ---------- state & history ----------
  commit(initial = false) {
    const snap = JSON.stringify(this.state);
    if (this.history[this.history.length - 1] === snap) return;
    this.history.push(snap); if (this.history.length > 120) this.history.shift();
    if (!initial) { this.future = []; writeStore(AUTOSAVE, { state: this.state, size: this.size, at: Date.now() }); }
    this.updateHistoryButtons();
    this.scheduleCompile();
  }

  softCommit() { clearTimeout(this.softTimer); this.softTimer = setTimeout(() => this.commit(), 500); this.scheduleCompile(); }

  undo() {
    if (this.history.length < 2) return;
    this.future.push(this.history.pop());
    this.restoreSnap(this.history[this.history.length - 1]);
  }

  redo() {
    if (!this.future.length) return;
    const snap = this.future.pop(); this.history.push(snap); this.restoreSnap(snap);
  }

  restoreSnap(snap) {
    this.state = JSON.parse(snap);
    if (!this.region(this.selected)) this.selected = null;
    this.renderAll(); this.updateHistoryButtons(); this.scheduleCompile();
  }

  region(id) { return this.state.regions.find((item) => item.id === id); }

  // ---------- compile ----------
  scheduleCompile() { clearTimeout(this.compileTimer); this.compileTimer = setTimeout(() => this.compile(), 220); this.setStatus('checking'); }

  /** Locks are editor-only: only the node's fields are sent. */
  payload(format = 'compact') {
    return { width: this.size.width, height: this.size.height, summary_caption: this.state.caption, meta: this.state.meta.join(', '),
      canvas: this.state.canvas, palette: this.state.palette.join(', '), output_format: format,
      layers_data: JSON.stringify({ version: 1, order: 'front_to_back', regions: this.state.regions.map(({ id, x, y, w, h, kind, text, description, colors, tags }) => ({ id, x, y, w, h, kind, text, description, relation: '', colors, tags })) }) };
  }

  async compile() {
    const revision = ++this.revision;
    try {
      const result = await call('serialize', this.payload());
      if (revision !== this.revision || this.closed) return;
      this.result = result; this.error = null;
    } catch (error) {
      if (revision !== this.revision || this.closed) return;
      this.result = null; this.error = error;
    }
    this.renderOutput();
  }

  // ---------- building the DOM ----------
  build() {
    this.referenceInput = el('input', { type: 'file', accept: 'image/*', hidden: true, tabindex: '-1' });
    this.importInput = el('input', { type: 'file', accept: '.json,.txt,.bbox,application/json,text/plain,image/png', hidden: true, tabindex: '-1' });
    this.listen(this.referenceInput, 'change', () => { const file = this.referenceInput.files?.[0]; this.referenceInput.value = ''; if (file) void this.handleFiles([file]); });
    this.listen(this.importInput, 'change', () => { const file = this.importInput.files?.[0]; this.importInput.value = ''; if (file) void this.handleFiles([file], { importOnly: true }); });

    const header = el('header', { class: 'slb-head' },
      el('div', { class: 'slb-title' }, icon('layout'), el('div', {}, el('strong', { text: 'Layout' }), this.sizeLabel = el('span', { class: 'slb-sub' }))),
      el('div', { class: 'slb-starters', role: 'group', 'aria-label': 'Start from' },
        el('span', { class: 'slb-starters-label', text: 'Start from' }),
        STARTERS.map((starter) => el('button', { type: 'button', class: 'slb-chip', title: starter.hint, onclick: () => this.applyStarter(starter) }, starter.name))),
      el('div', { class: 'slb-head-actions' },
        this.undoButton = this.iconButton('undo', 'Undo (Ctrl+Z)', () => this.undo()),
        this.redoButton = this.iconButton('redo', 'Redo (Ctrl+Shift+Z)', () => this.redo()),
        el('span', { class: 'slb-divider is-optional', 'aria-hidden': 'true' }),
        this.gridButton = this.iconButton('grid', 'Guides: thirds or golden ratio', () => this.openGuides(), 'is-optional'),
        this.snapButton = this.iconButton('magnet', 'Snap to edges, centres, guides and other boxes (hold Alt to move freely)', () => { this.snap = !this.snap; writeStore('heiss.mossLayout.snap', this.snap); this.renderToggles(); }, 'is-optional'),
        this.referenceButton = this.iconButton('image', 'Reference image to trace (drop or paste one too)', () => this.openReference()),
        this.importButton = this.iconButton('open', 'Import a layout (.json, Ideogram 4 JSON, or a PNG that carries one)', () => this.openImport()),
        this.aiButton = el('button', { type: 'button', class: 'slb-btn is-ai', title: 'AI assistant: a layout and prompt from an image or an idea, box captions, snapping, lettering (I)', onclick: () => this.openAi() },
          el('span', { class: 'slb-ai-glyph', 'aria-hidden': 'true' }, icon('spark')), el('span', { text: 'AI' })),
        el('span', { class: 'slb-divider', 'aria-hidden': 'true' }),
        el('button', { type: 'button', class: 'slb-btn', onclick: () => this.requestClose() }, 'Close'),
        this.applyButton = el('button', { type: 'button', class: 'slb-btn is-primary', onclick: () => this.apply() }, icon('check'), 'Use layout')));
    for (const button of [this.gridButton, this.referenceButton, this.importButton, this.aiButton]) { button.setAttribute('aria-haspopup', 'menu'); button.setAttribute('aria-expanded', 'false'); }

    // Summary (left)
    this.captionInput = el('textarea', { class: 'slb-input slb-caption', rows: 5, placeholder: 'The whole image in a few sentences: subject, setting, medium, style, light, mood…', 'aria-label': 'Summary caption', spellcheck: 'true' });
    this.listen(this.captionInput, 'input', () => { this.state.caption = this.captionInput.value; this.softCommit(); });
    this.metaChips = el('div', { class: 'slb-chips-input' });
    this.metaSuggest = el('div', { class: 'slb-suggest', id: 'slb-meta-suggest', role: 'listbox', 'aria-label': 'Suggested meta tags', hidden: true });
    this.metaInput = el('input', { class: 'slb-chip-entry', placeholder: 'poster, editorial…', 'aria-label': 'Add meta tag', role: 'combobox', 'aria-autocomplete': 'list', 'aria-controls': 'slb-meta-suggest', 'aria-expanded': 'false', autocomplete: 'off' });
    this.listen(this.metaInput, 'keydown', (event) => { if (!this.suggestKey(event)) this.chipKey(event, this.metaInput, this.state.meta, () => this.renderMeta()); });
    this.listen(this.metaInput, 'focus', () => this.renderSuggest());
    this.listen(this.metaInput, 'input', () => this.renderSuggest());
    this.listen(this.metaInput, 'blur', () => { this.hideSuggest(); this.chipFlush(this.metaInput, this.state.meta, () => this.renderMeta()); });
    this.canvasSeg = el('div', { class: 'slb-seg', role: 'radiogroup', 'aria-label': 'Canvas' });
    this.summaryPalette = el('div', { class: 'slb-palette' });
    this.layerList = el('ol', { class: 'slb-layers', 'aria-label': 'Boxes, front to back' });
    this.layerCount = el('span', { class: 'slb-h-note' });
    const summary = el('aside', { class: 'slb-panel slb-summary', 'aria-label': 'Summary' },
      el('section', { class: 'slb-card' },
        el('h3', { class: 'slb-h', text: 'Summary' }),
        this.captionInput,
        el('label', { class: 'slb-label', text: 'Meta' }), el('div', { class: 'slb-chipbox', onclick: () => this.metaInput.focus() }, this.metaChips, this.metaInput), this.metaSuggest,
        el('label', { class: 'slb-label', text: 'Canvas' }), this.canvasSeg,
        el('label', { class: 'slb-label', text: 'Palette' }), this.summaryPalette),
      el('section', { class: 'slb-card slb-layers-card' },
        el('h3', { class: 'slb-h' }, 'Boxes', this.layerCount),
        this.layerList));

    // Stage (centre)
    this.board = el('div', { class: 'slb-board', tabindex: '0', 'aria-label': 'Layout canvas. Drag on empty space to draw a box; right-click for placement presets.' });
    this.refImage = el('img', { class: 'slb-ref', alt: '', draggable: 'false', hidden: true });
    this.guideLayer = el('div', { class: 'slb-guide-lines', 'aria-hidden': 'true' });
    this.guides = el('div', { class: 'slb-guides', 'aria-hidden': 'true' });
    this.empty = el('div', { class: 'slb-empty' }, el('strong', { text: 'Drag to place something' }),
      el('span', { text: 'or pick a starter above, use Place for quick splits, or drop an image to trace over. Boxes are optional: a summary alone is a plain caption prompt.' }));
    this.aiScan = el('div', { class: 'slb-ai-scan', 'aria-hidden': 'true' }, el('i', { class: 'slb-ai-beam' }));
    this.board.append(this.refImage, this.guideLayer, this.empty, this.guides, this.aiScan);
    this.stage = el('div', { class: 'slb-stage' }, this.board);
    this.dropHint = el('div', { class: 'slb-drop', 'aria-hidden': 'true' }, el('div', {}, icon('image'), el('strong', { text: 'Drop to add' }), el('span', { text: 'An image becomes the reference to trace; a layout .json or a Studio PNG brings its boxes.' })));
    this.placeButton = el('button', { type: 'button', class: 'slb-tool', 'aria-haspopup': 'menu', 'aria-expanded': 'false', title: 'Placement presets: fill, halves, corners, grids (P)', onclick: () => this.openPlace(this.placeButton) }, icon('place'), 'Place', icon('chevron'));
    this.zoomLabel = el('button', { type: 'button', class: 'slb-zoom-label', title: 'Fit the canvas (0)', onclick: () => this.setZoom(1) });
    this.coords = el('span', { class: 'slb-coords', 'aria-hidden': 'true' });
    this.kindGroup = el('div', { class: 'slb-kinds', role: 'radiogroup', 'aria-label': 'Draw' },
      KINDS.map(([kind, label, key]) => el('button', { type: 'button', role: 'radio', class: `slb-tool is-${kind}`, 'data-kind': kind, title: `Draw ${label.toLowerCase()} boxes (${key})`, onclick: () => { this.tool = kind; this.renderToggles(); } },
        el('i', { class: 'slb-dot', 'aria-hidden': 'true' }), label)));
    this.toolbar = el('div', { class: 'slb-tools' },
      this.kindGroup,
      el('span', { class: 'slb-divider', 'aria-hidden': 'true' }),
      this.placeButton,
      el('button', { type: 'button', class: 'slb-tool', title: 'Add a centred box of this kind', onclick: () => this.addCentered() }, icon('plus'), 'Add'),
      el('span', { class: 'slb-divider', 'aria-hidden': 'true' }),
      el('div', { class: 'slb-zoom', role: 'group', 'aria-label': 'Zoom' },
        this.iconButton('minus', 'Zoom out (−)', () => this.zoomStep(-1), 'is-tool'), this.zoomLabel, this.iconButton('plus', 'Zoom in (+)', () => this.zoomStep(1), 'is-tool')),
      this.coords);
    this.aiCard = el('div', { class: 'slb-ai-card', role: 'status', 'aria-live': 'polite', hidden: true });
    const centre = el('main', { class: 'slb-centre' }, this.stage, this.aiCard, this.toolbar, this.dropHint);

    // Inspector (right)
    this.inspector = el('aside', { class: 'slb-panel slb-inspector', 'aria-label': 'Selected box' });
    // Output (bottom of right column)
    this.statusDot = el('i', { class: 'slb-status-dot' });
    this.statusText = el('span', { class: 'slb-status-text' });
    this.output = el('pre', { class: 'slb-output', tabindex: '0', 'aria-label': 'Compiled MOSS prompt' });
    this.warnings = el('ul', { class: 'slb-warnings' });
    this.noticeBar = el('p', { class: 'slb-notice', role: 'status', 'aria-live': 'polite' });
    const out = el('section', { class: 'slb-card slb-out' },
      el('h3', { class: 'slb-h' }, 'Prompt', el('span', { class: 'slb-status' }, this.statusDot, this.statusText),
        this.iconButton('copy', 'Copy prompt', () => this.copy()),
        this.iconButton('share', 'Copy as Ideogram 4 JSON (characters become objects)', () => this.copyIdeogram()),
        this.iconButton('save', 'Save as .json (BBox Studio and other editors open it)', () => this.saveJson())),
      this.output, this.warnings);
    const right = el('div', { class: 'slb-right' }, this.inspector, out);

    this.root = el('div', { class: 'slb', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'MOSS layout builder' },
      el('div', { class: 'slb-shell' }, header, el('div', { class: 'slb-body' }, summary, centre, right), this.noticeBar), this.referenceInput, this.importInput);

    this.listen(this.board, 'pointerdown', (event) => this.pointerDown(event));
    this.listen(this.board, 'pointermove', (event) => this.pointerMove(event));
    this.listen(this.board, 'pointerup', (event) => this.pointerUp(event));
    this.listen(this.board, 'pointercancel', () => this.cancelDrag());
    this.listen(this.board, 'pointerleave', () => this.renderCoords());
    this.listen(this.board, 'dblclick', (event) => { if (event.target.closest('.slb-box')) this.inspector.querySelector('textarea')?.focus(); });
    this.listen(this.board, 'contextmenu', (event) => this.contextMenu(event));
    // Keys typed in the builder stop here; keys aimed at the page behind it are redirected.
    this.listen(this.root, 'keydown', (event) => this.keydown(event));
    this.listen(this.root, 'keyup', (event) => { if (event.key === ' ') this.setSpace(false); });
    this.listen(window, 'blur', () => this.setSpace(false));
    this.listen(window, 'keydown', (event) => { if (!this.root.contains(event.target)) this.keydown(event); }, { capture: true });
    this.listen(this.root, 'pointerdown', (event) => {
      const pop = this.popover;
      if (pop && !pop.el.contains(event.target) && !pop.anchor?.contains(event.target)) this.closePopover();
    }, { capture: true });
    // Pan: middle-drag, or Space + drag, anywhere on the stage.
    this.listen(this.stage, 'pointerdown', (event) => this.panStart(event), { capture: true });
    this.listen(this.stage, 'pointermove', (event) => this.panMove(event));
    this.listen(this.stage, 'pointerup', (event) => this.panEnd(event));
    this.listen(this.stage, 'pointercancel', (event) => this.panEnd(event));
    this.listen(this.stage, 'auxclick', (event) => { if (event.button === 1) event.preventDefault(); });
    this.listen(this.stage, 'pointerdown', (event) => { if (event.target === this.stage) this.select(null); });
    this.listen(this.stage, 'wheel', (event) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      event.preventDefault();
      this.setZoom(this.zoom * Math.exp(-event.deltaY * 0.0018), { x: event.clientX, y: event.clientY });
    }, { passive: false });
    // Files: drop anywhere in the builder; paste images or layouts when not typing in a field.
    this.listen(this.root, 'dragenter', (event) => this.dragFiles(event));
    this.listen(this.root, 'dragover', (event) => this.dragFiles(event));
    this.listen(this.root, 'dragleave', (event) => { if (!event.relatedTarget || !this.root.contains(event.relatedTarget)) this.root.classList.remove('is-dropping'); });
    this.listen(this.root, 'drop', (event) => {
      if (!this.hasFiles(event)) return;
      event.preventDefault();
      this.root.classList.remove('is-dropping');
      void this.handleFiles(event.dataTransfer.files);
    });
    this.listen(this.root, 'paste', (event) => this.paste(event));
    // Clicking the board leaves focus on <body>, outside the builder; a paste there still belongs here.
    this.listen(document, 'paste', (event) => { if (!this.root.contains(event.target)) this.paste(event); });
    this.listen(window, 'resize', () => { this.closePopover(); this.layoutStage(); });
    this.resizer = new ResizeObserver(() => this.layoutStage());
    this.resizer.observe(this.stage);
    this.events.signal.addEventListener('abort', () => this.resizer.disconnect());
  }

  iconButton(name, label, onclick, extra = '') { return el('button', { type: 'button', class: `slb-icon-btn ${extra}`.trim(), title: label, 'aria-label': label, onclick }, icon(name)); }

  layoutStage() {
    if (!this.stage) return;
    const { width, height } = this.size;
    const style = getComputedStyle(this.stage);
    const roomW = this.stage.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const roomH = this.stage.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
    const fit = Math.min((roomW - 4) / width, (roomH - 4) / height);
    if (!(fit > 0)) return;
    this.scale = fit * this.zoom;
    this.board.style.width = `${Math.floor(width * this.scale)}px`;
    this.board.style.height = `${Math.floor(height * this.scale)}px`;
    this.stage.classList.toggle('is-zoomed', this.zoom > 1.001);
    this.renderZoom();
    this.renderBoxes();
  }

  // ---------- rendering ----------
  renderAll() {
    const divisor = gcd(this.size.width, this.size.height) || 1;
    this.sizeLabel.textContent = `MOSS-Image · ${this.size.width} × ${this.size.height} · ${this.size.width / divisor}:${this.size.height / divisor}`;
    if (document.activeElement !== this.captionInput) this.captionInput.value = this.state.caption;
    this.renderMeta(); this.renderCanvasSeg(); this.renderSummaryPalette(); this.renderToggles(); this.renderReference(); this.renderCoords();
    this.renderBoxes(); this.renderLayers(); this.renderInspector(); this.renderOutput();
  }

  renderToggles() {
    this.gridButton.setAttribute('aria-pressed', String(this.guideMode !== 'off'));
    this.snapButton.setAttribute('aria-pressed', String(this.snap));
    const lines = [];
    for (const value of GUIDE_LINES[this.guideMode]) {
      const golden = Math.abs(value - PHI) < 1e-6 || Math.abs(value - (1 - PHI)) < 1e-6;
      lines.push(el('i', { class: `is-x${golden ? ' is-golden' : ''}`, style: { left: `${value * 100}%` } }), el('i', { class: `is-y${golden ? ' is-golden' : ''}`, style: { top: `${value * 100}%` } }));
    }
    this.guideLayer.replaceChildren(...lines);
    for (const button of this.kindGroup.querySelectorAll('[data-kind]')) button.setAttribute('aria-checked', String(button.dataset.kind === this.tool));
    this.board.dataset.tool = this.tool;
    this.root.dataset.tool = this.tool;
  }

  renderZoom() {
    if (!this.zoomLabel || !this.scale) return;
    this.zoomLabel.textContent = `${Math.round(this.scale * 100)}%`;
    this.zoomLabel.setAttribute('aria-label', this.zoom > 1.001 ? `Zoom ${Math.round(this.scale * 100)}%, press to fit` : `Fitted at ${Math.round(this.scale * 100)}%`);
    this.zoomLabel.classList.toggle('is-fit', this.zoom <= 1.001);
  }

  renderCoords(point = null) {
    if (!this.coords) return;
    this.coords.textContent = point ? `${Math.round(point.x * this.size.width)}, ${Math.round(point.y * this.size.height)}` : `${this.size.width} × ${this.size.height}`;
  }

  renderReference() {
    const ref = this.reference;
    this.referenceButton?.setAttribute('aria-pressed', String(!!ref));
    this.refImage.hidden = !ref;
    if (!ref) { this.refImage.removeAttribute('src'); return; }
    if (this.refImage.getAttribute('src') !== ref.url) this.refImage.src = ref.url;
    this.refImage.style.opacity = String(clamp(Number(this.refView.opacity) || 0.45, 0.05, 1));
    const fit = FITS.some(([value]) => value === this.refView.fit) ? this.refView.fit : 'cover';
    // 1:1 shows the image at its own pixel size around the canvas centre, the way MOSS boxes are measured.
    const actual = fit === 'actual', w = (100 * ref.width) / this.size.width, h = (100 * ref.height) / this.size.height;
    Object.assign(this.refImage.style, { objectFit: actual ? 'fill' : fit, width: actual ? `${w}%` : '', height: actual ? `${h}%` : '',
      left: actual ? `${(100 - w) / 2}%` : '', top: actual ? `${(100 - h) / 2}%` : '' });
  }

  updateHistoryButtons() {
    if (!this.undoButton) return;
    this.undoButton.disabled = this.history.length < 2;
    this.redoButton.disabled = !this.future.length;
  }

  renderMeta() {
    this.metaChips.replaceChildren(...this.state.meta.map((tag, index) => el('span', { class: 'slb-tag' }, tag,
      el('button', { type: 'button', 'aria-label': `Remove ${tag}`, onclick: (event) => { event.stopPropagation(); this.state.meta.splice(index, 1); this.renderMeta(); this.commit(); if (document.activeElement === this.metaInput) this.renderSuggest(); } }, '×'))));
  }

  chipKey(event, input, list, render) {
    if (event.key === 'Enter' || event.key === ',') { event.preventDefault(); this.chipFlush(input, list, render); }
    else if (event.key === 'Backspace' && !input.value && list.length) { list.pop(); render(); this.commit(); }
  }

  chipFlush(input, list, render) {
    const added = splitList(input.value).filter((item) => !list.includes(item));
    input.value = '';
    if (!added.length) return;
    list.push(...added); render(); this.commit();
    if (input === this.metaInput && document.activeElement === input) this.renderSuggest();
  }

  // ---------- meta suggestions ----------
  renderSuggest() {
    const query = this.metaInput.value.trim().toLowerCase();
    const chosen = new Set(this.state.meta.map((tag) => tag.toLowerCase()));
    const groups = META_SUGGESTIONS.map(([name, tags]) => [name, tags.filter((tag) => !chosen.has(tag) && (!query || tag.includes(query)))]).filter(([, tags]) => tags.length);
    this.suggestions = groups.flatMap(([, tags]) => tags);
    this.suggestIndex = -1;
    if (!groups.length) { this.hideSuggest(); return; }
    this.metaSuggest.replaceChildren(...groups.map(([name, tags]) => el('div', { class: 'slb-suggest-group', role: 'group', 'aria-label': name },
      el('span', { class: 'slb-suggest-name', text: name }),
      el('div', { class: 'slb-suggest-row' }, tags.map((tag) => {
        const at = query ? tag.indexOf(query) : -1;
        const label = at < 0 ? tag : [tag.slice(0, at), el('mark', { text: tag.slice(at, at + query.length) }), tag.slice(at + query.length)];
        return el('button', { type: 'button', role: 'option', tabindex: '-1', id: `slb-meta-${this.suggestions.indexOf(tag)}`, class: 'slb-suggest-item', 'aria-selected': 'false',
          onpointerdown: (event) => event.preventDefault(), onclick: () => this.pickMeta(tag) }, label);
      })))));
    this.metaSuggest.hidden = false;
    this.metaInput.setAttribute('aria-expanded', 'true');
    this.metaInput.removeAttribute('aria-activedescendant');
  }

  hideSuggest() {
    this.metaSuggest.hidden = true;
    this.metaInput.setAttribute('aria-expanded', 'false');
    this.metaInput.removeAttribute('aria-activedescendant');
    this.suggestIndex = -1;
  }

  /** Arrow keys walk the suggestions, Enter picks the highlighted one, Esc hides them. True when handled. */
  suggestKey(event) {
    if (this.metaSuggest.hidden || !this.suggestions?.length) return false;
    const key = event.key;
    if (key === 'ArrowDown' || key === 'ArrowUp') {
      event.preventDefault();
      const count = this.suggestions.length;
      this.suggestIndex = key === 'ArrowDown' ? (this.suggestIndex + 1) % count : (this.suggestIndex <= 0 ? count - 1 : this.suggestIndex - 1);
      for (const item of this.metaSuggest.querySelectorAll('[role=option]')) item.setAttribute('aria-selected', String(item.id === `slb-meta-${this.suggestIndex}`));
      const active = this.metaSuggest.querySelector(`#slb-meta-${this.suggestIndex}`);
      active?.scrollIntoView({ block: 'nearest' });
      this.metaInput.setAttribute('aria-activedescendant', `slb-meta-${this.suggestIndex}`);
      return true;
    }
    if (key === 'Enter' && this.suggestIndex >= 0) { event.preventDefault(); this.pickMeta(this.suggestions[this.suggestIndex]); return true; }
    if (key === 'Escape') { event.preventDefault(); event.stopPropagation(); this.hideSuggest(); return true; }
    return false;
  }

  pickMeta(tag) {
    if (!this.state.meta.includes(tag)) this.state.meta.push(tag);
    this.metaInput.value = '';
    this.renderMeta(); this.commit();
    this.metaInput.focus({ preventScroll: true });
    this.renderSuggest();
  }

  renderCanvasSeg() {
    this.canvasSeg.replaceChildren(...CANVASES.map(([value, label]) => el('button', { type: 'button', role: 'radio', 'aria-checked': String(this.state.canvas === value),
      onclick: () => { this.state.canvas = value; this.renderCanvasSeg(); this.commit(); } }, label)));
  }

  renderSummaryPalette() { this.renderPalette(this.summaryPalette, this.state.palette); }

  renderPalette(host, list) {
    const swatches = list.map((value, index) => {
      const hex = HEX.test(value);
      const picker = el('input', { type: 'color', value: hex ? value : '#cccccc', 'aria-label': `Color ${index + 1}` });
      this.listen(picker, 'input', () => { list[index] = picker.value.toUpperCase(); label.value = list[index]; this.renderBoxes(); this.softCommit(); });
      const label = el('input', { class: 'slb-swatch-name', value, 'aria-label': `Color ${index + 1} name or hex`, size: Math.max(7, value.length) });
      this.listen(label, 'change', () => {
        const next = label.value.trim();
        if (!next) list.splice(index, 1); else list[index] = HEX.test(next) ? next.toUpperCase() : next;
        this.renderPalette(host, list); this.renderBoxes(); this.commit();
      });
      return el('span', { class: 'slb-swatch', style: { '--swatch': hex ? value : 'transparent' } }, el('span', { class: 'slb-swatch-color' }, picker), label,
        el('button', { type: 'button', class: 'slb-swatch-x', 'aria-label': `Remove color ${index + 1}`, onclick: () => { list.splice(index, 1); this.renderPalette(host, list); this.renderBoxes(); this.commit(); } }, '×'));
    });
    host.replaceChildren(...swatches, el('button', { type: 'button', class: 'slb-add-color', title: 'Add a color (pick, or type a hex or a name such as deep teal)', onclick: () => {
      list.push(list.length ? '#FFFFFF' : '#E8DCC8'); this.renderPalette(host, list); this.commit();
      host.querySelectorAll('.slb-swatch-name')[list.length - 1]?.focus();
    } }, '+'));
  }

  number(region) { return this.state.regions.length - this.state.regions.indexOf(region); }

  renderBoxes() {
    if (!this.board || !this.scale) return;
    const live = new Set();
    // Painter's order: back first. Index 0 of the array is the FRONT.
    this.state.regions.slice().reverse().forEach((region, order) => {
      live.add(region.id);
      let box = this.boxes.get(region.id);
      if (!box) {
        box = el('div', { class: 'slb-box', 'data-id': region.id },
          el('span', { class: 'slb-box-tag' }), el('div', { class: 'slb-box-body' }),
          el('span', { class: 'slb-box-size' }),
          ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'].map((handle) => el('i', { class: `slb-handle is-${handle}`, 'data-handle': handle })));
        const born = this.born?.get(region.id);
        if (born != null) {
          // AI results materialise one after another, back to front.
          box.classList.add('is-born');
          box.style.animationDelay = `${Math.min(born, 14) * 55}ms`;
          setTimeout(() => { box.classList.remove('is-born'); box.style.animationDelay = ''; }, 900 + Math.min(born, 14) * 55);
        } else {
          box.classList.add('is-new');
          setTimeout(() => box.classList.remove('is-new'), 400);
        }
        this.boxes.set(region.id, box);
        this.board.insertBefore(box, this.guides);
      }
      this.paintBox(box, region, order);
    });
    for (const [id, box] of this.boxes) if (!live.has(id)) { box.remove(); this.boxes.delete(id); }
    this.empty.hidden = this.state.regions.length > 0;
  }

  paintBox(box, region, order = null) {
    const motion = ['is-new', 'is-born', 'is-thinking'].filter((name) => box.classList.contains(name)).map((name) => ` ${name}`).join('');
    box.className = `slb-box is-${region.kind}${region.id === this.selected ? ' is-selected' : ''}${region.locked ? ' is-locked' : ''}${motion}`;
    Object.assign(box.style, { left: `${region.x * 100}%`, top: `${region.y * 100}%`, width: `${region.w * 100}%`, height: `${region.h * 100}%` });
    if (order != null) box.style.zIndex = String(10 + order);
    const accent = region.colors.find((value) => HEX.test(value));
    box.style.setProperty('--accent-swatch', accent || 'transparent');
    const kind = KINDS.find(([name]) => name === region.kind)[1];
    box.querySelector('.slb-box-tag').textContent = `${pad2(this.number(region))} · ${kind}`;
    const body = box.querySelector('.slb-box-body');
    const pxW = region.w * this.board.clientWidth, pxH = region.h * this.board.clientHeight;
    if (region.kind === 'text' && region.text.trim()) {
      // Fit the exact lines (no extra wrapping) by measuring them in the preview's own font.
      const lines = region.text.split('\n');
      const widest = Math.max(1, ...lines.map((line) => measure(line, getComputedStyle(body).fontFamily)));
      const fontPx = clamp(Math.min((pxH - 8) / (lines.length * 1.14), (pxW - 10) / (widest / 100)), 6, 260);
      body.className = 'slb-box-body is-text';
      body.style.fontSize = `${fontPx}px`;
      body.style.color = accent || '';
      body.textContent = region.text;
    } else {
      body.className = 'slb-box-body';
      body.style.fontSize = ''; body.style.color = '';
      body.textContent = region.description || (region.kind === 'text' ? 'Exact text…' : `Describe this ${region.kind}…`);
      body.classList.toggle('is-placeholder', !region.description);
    }
    const [x1, y1, x2, y2] = this.pixels(region);
    box.querySelector('.slb-box-size').textContent = `${x2 - x1} × ${y2 - y1}`;
  }

  /** Enclosed top-left pixel edges, as the node exports them. */
  pixels(region) {
    const { width, height } = this.size;
    const x1 = Math.floor(+(region.x * width).toFixed(9)), y1 = Math.floor(+(region.y * height).toFixed(9));
    const x2 = Math.ceil(+((region.x + region.w) * width).toFixed(9)), y2 = Math.ceil(+((region.y + region.h) * height).toFixed(9));
    return [x1, y1, Math.min(width, Math.max(x1 + 1, x2)), Math.min(height, Math.max(y1 + 1, y2))];
  }

  renderLayers() {
    const count = this.state.regions.length;
    this.layerCount.textContent = count ? `${count} · front ↑ back ↓` : '';
    if (!count) {
      this.layerList.replaceChildren(el('li', { class: 'slb-layers-empty', text: 'No boxes yet. Draw on the canvas, or use Place for quick splits.' }));
      return;
    }
    this.layerList.replaceChildren(...this.state.regions.map((region, index) => {
      const label = region.kind === 'text' ? (region.text.split('\n')[0] || 'Exact text') : (region.description || `Untitled ${region.kind}`);
      const number = pad2(this.number(region));
      const lock = el('button', { type: 'button', class: 'slb-layer-lock', 'aria-pressed': String(!!region.locked),
        'aria-label': region.locked ? `Unlock box ${number}` : `Lock box ${number}`, title: region.locked ? 'Unlock (L)' : 'Lock in place (L)',
        onclick: (event) => { event.stopPropagation(); this.toggleLock(region.id); } }, icon(region.locked ? 'lock' : 'unlock'));
      const row = el('li', { class: `slb-layer is-${region.kind}${region.id === this.selected ? ' is-selected' : ''}${region.locked ? ' is-locked' : ''}`, draggable: 'true', tabindex: '0', 'aria-selected': String(region.id === this.selected), title: label },
        el('span', { class: 'slb-layer-num', text: number }), el('i', { class: 'slb-dot', 'aria-hidden': 'true' }),
        el('span', { class: 'slb-layer-label', text: label }), lock);
      this.listen(row, 'click', () => this.select(region.id));
      this.listen(row, 'keydown', (event) => { if (event.target === row && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); this.select(region.id); } });
      this.listen(row, 'dragstart', (event) => { this.dragRow = index; event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', region.id); });
      this.listen(row, 'dragover', (event) => { if (this.dragRow == null) return; event.preventDefault(); row.classList.add('is-drop'); });
      this.listen(row, 'dragleave', () => row.classList.remove('is-drop'));
      this.listen(row, 'dragend', () => { this.dragRow = null; });
      this.listen(row, 'drop', (event) => { if (this.dragRow == null) return; event.preventDefault(); event.stopPropagation(); this.reorder(this.dragRow, index); this.dragRow = null; });
      return row;
    }));
  }

  renderInspector() {
    const region = this.region(this.selected);
    if (!region) {
      const key = (label, text) => el('li', {}, el('kbd', { text: label }), el('span', { text }));
      this.inspector.replaceChildren(el('section', { class: 'slb-card slb-tips' },
        el('h3', { class: 'slb-h', text: 'How it works' }),
        el('p', { text: 'The summary describes the whole picture. Boxes pin specific things in place: objects, characters, and text that must read exactly.' }),
        el('ul', { class: 'slb-keys' },
          key('Drag', 'draw · move · resize'),
          key('Shift', 'keep proportions · square · straight'),
          key('Ctrl', 'draw over boxes · resize from centre'),
          key('Alt', 'drag without snapping'),
          key('O C T', 'object, character, text'),
          key('P', 'placement presets'),
          key('↑↓←→', 'nudge 16 px (Shift ×4)'),
          key('Ctrl D', 'duplicate'),
          key('L', 'lock or unlock'),
          key('Del', 'remove'),
          key('[ ]', 'send back · bring front'),
          key('+ − 0', 'zoom · fit'),
          key('Space', 'drag to pan when zoomed'),
          key('Right-click', 'box menu · presets'),
          key('I', 'AI assistant')),
        el('p', { class: 'slb-tips-foot', text: 'Drop or paste an image to trace over it (AI can read its layout), or a MOSS or Ideogram 4 layout to import it.' })));
      return;
    }
    const locked = !!region.locked;
    const number = pad2(this.number(region));
    const kindSeg = el('div', { class: 'slb-seg is-kinds', role: 'radiogroup', 'aria-label': 'Box type' },
      KINDS.map(([kind, label]) => el('button', { type: 'button', role: 'radio', class: `is-${kind}`, 'aria-checked': String(region.kind === kind),
        onclick: () => this.setKind(region.id, kind) }, el('i', { class: 'slb-dot', 'aria-hidden': 'true' }), label)));
    const field = (label, value, placeholder, rows, onInput, extra = {}) => {
      const input = el('textarea', { class: `slb-input ${extra.class || ''}`, rows, placeholder, 'aria-label': label, spellcheck: extra.spell ?? 'true' });
      input.value = value;
      this.listen(input, 'input', () => { onInput(input.value); this.paintBox(this.boxes.get(region.id), region); this.renderLayers(); this.softCommit(); });
      return [el('label', { class: 'slb-label', text: label }), input];
    };
    const [px1, py1, px2, py2] = this.pixels(region);
    const parts = [el('h3', { class: 'slb-h' }, `Box ${number}`,
      locked ? el('span', { class: 'slb-badge' }, icon('lock'), 'Locked') : null,
      el('span', { class: 'slb-h-note', text: `${px2 - px1} × ${py2 - py1} px` })), kindSeg];
    if (region.kind === 'text') parts.push(...field('Exact text', region.text, 'The words to render, exactly. Line breaks are kept.', 2, (value) => { region.text = value; }, { class: 'slb-exact', spell: 'false' }));
    parts.push(...field(region.kind === 'text' ? 'Look of the text' : 'Caption',
      region.description,
      region.kind === 'text' ? 'Typography, weight, color, surface: e.g. large dark-blue condensed sans-serif' : region.kind === 'character' ? 'Who, pose, clothing, expression, framing…' : 'What it is and how it looks…',
      3, (value) => { region.description = value; }));
    const tagsBox = el('div', { class: 'slb-chips-input' });
    const tagInput = el('input', { class: 'slb-chip-entry', placeholder: 'optional tags', 'aria-label': 'Add tag' });
    const renderTags = () => tagsBox.replaceChildren(...region.tags.map((tag, index) => el('span', { class: 'slb-tag' }, tag,
      el('button', { type: 'button', 'aria-label': `Remove ${tag}`, onclick: (event) => { event.stopPropagation(); region.tags.splice(index, 1); renderTags(); this.commit(); } }, '×'))));
    renderTags();
    this.listen(tagInput, 'keydown', (event) => this.chipKey(event, tagInput, region.tags, renderTags));
    this.listen(tagInput, 'blur', () => this.chipFlush(tagInput, region.tags, renderTags));
    const palette = el('div', { class: 'slb-palette' });
    this.renderPalette(palette, region.colors);
    const geometry = el('div', { class: 'slb-geo' }, ['x', 'y', 'w', 'h'].map((key, index) => {
      const shown = [px1, py1, px2 - px1, py2 - py1][index];
      const input = el('input', { type: 'number', value: shown, step: '16', 'aria-label': `${key.toUpperCase()} in pixels`, disabled: locked });
      this.listen(input, 'change', () => {
        const value = Number(input.value), { width, height } = this.size;
        if (!Number.isFinite(value) || region.locked) return;
        if (key === 'x') region.x = clamp(value / width, 0, 1 - region.w);
        if (key === 'y') region.y = clamp(value / height, 0, 1 - region.h);
        if (key === 'w') region.w = clamp(value / width, 1 / width, 1 - region.x);
        if (key === 'h') region.h = clamp(value / height, 1 / height, 1 - region.y);
        this.renderBoxes(); this.renderInspector(); this.commit();
      });
      return el('label', {}, el('span', { text: key.toUpperCase() }), input);
    }));
    const alignments = [['align-left', 'Align left', 'left'], ['align-centre', 'Centre horizontally', 'centre'], ['align-right', 'Align right', 'right'],
      ['align-top', 'Align top', 'top'], ['align-middle', 'Centre vertically', 'middle'], ['align-bottom', 'Align bottom', 'bottom']];
    const align = el('div', { class: 'slb-align', role: 'group', 'aria-label': 'Align to canvas' }, alignments.map(([name, label, where]) => {
      const button = this.iconButton(name, label, () => this.align(where), 'is-tool');
      button.disabled = locked;
      return button;
    }));
    const remove = this.textButton('trash', 'Remove', () => this.remove(), 'is-danger');
    remove.disabled = locked;
    parts.push(el('label', { class: 'slb-label', text: 'Tags' }), el('div', { class: 'slb-chipbox', onclick: () => tagInput.focus() }, tagsBox, tagInput),
      el('label', { class: 'slb-label', text: 'Palette' }), palette,
      el('label', { class: 'slb-label', text: 'Position (px, from top-left)' }), geometry,
      el('label', { class: 'slb-label', text: 'Align to canvas' }), align,
      el('div', { class: 'slb-actions' },
        this.textButton(locked ? 'unlock' : 'lock', locked ? 'Unlock' : 'Lock', () => this.toggleLock(region.id), locked ? 'is-on' : ''),
        this.textButton('front', 'Front', () => this.move(-1)), this.textButton('back', 'Back', () => this.move(1)),
        this.textButton('dup', 'Duplicate', () => this.duplicate()), remove),
      locked ? el('p', { class: 'slb-note', text: 'Locked boxes stay put: dragging on one draws a new box over it. Locks belong to this editor, not to the prompt.' }) : null);
    this.inspector.replaceChildren(el('section', { class: `slb-card slb-item is-${region.kind}${locked ? ' is-locked' : ''}` }, parts));
  }

  textButton(name, label, onclick, extra = '') { return el('button', { type: 'button', class: `slb-btn is-small ${extra}`, onclick }, icon(name), label); }

  setStatus(kind) {
    if (!this.statusDot) return;
    this.statusDot.dataset.kind = kind;
    this.statusText.textContent = kind === 'checking' ? 'Checking…' : '';
  }

  renderOutput() {
    if (!this.output) return;
    const result = this.result, error = this.error;
    this.warnings.replaceChildren();
    if (error) {
      this.setStatus('error');
      this.statusText.textContent = error.offline ? 'Unavailable' : 'Needs attention';
      this.output.replaceChildren(el('span', { class: 'slb-out-error', text: error.message }));
      this.applyButton.disabled = true;
      this.applyButton.title = error.message;
      return;
    }
    if (!result) return;
    this.setStatus(result.warnings.length ? 'warning' : 'ok');
    const chars = result.prompt.length;
    this.statusText.textContent = result.mode === 'caption' ? `Caption · ${chars} chars` : `${this.state.regions.length} ${this.state.regions.length === 1 ? 'box' : 'boxes'} · ${chars} chars`;
    this.output.replaceChildren(...highlight(result.prompt));
    this.warnings.replaceChildren(...result.warnings.map((text) => el('li', { text })));
    const empty = !result.prompt.trim();
    this.applyButton.disabled = empty;
    this.applyButton.title = empty ? 'Write a summary caption or add a box first.' : 'Put this prompt in the composer. Undo there restores your previous prompt.';
  }

  /** A short message over the canvas; an optional action button ({label, run}) keeps it up longer. */
  notice(text, kind = 'info', action = null) {
    if (!this.noticeBar) return;
    const button = action ? el('button', { type: 'button', class: 'slb-notice-action', onclick: () => { this.noticeBar.classList.remove('is-shown'); action.run(); } }, action.label) : null;
    this.noticeBar.replaceChildren(...[el('span', { text }), button].filter(Boolean));
    this.noticeBar.dataset.kind = kind;
    this.noticeBar.classList.toggle('has-action', !!action);
    this.noticeBar.classList.remove('is-shown'); void this.noticeBar.offsetWidth; this.noticeBar.classList.add('is-shown');
    clearTimeout(this.noticeTimer);
    this.noticeTimer = setTimeout(() => this.noticeBar.classList.remove('is-shown'), action ? 10000 : kind === 'warning' ? 4500 : 6500);
  }

  fail(error) { this.error = error; this.notice(error.message, 'warning'); }

  offerRestore(saved) {
    const restore = el('button', { type: 'button', class: 'slb-chip is-restore', onclick: () => {
      this.state = plain(saved.state); this.selected = null; restore.remove(); this.renderAll(); this.commit();
      this.notice('Restored your last unsaved layout. Undo goes back to a blank canvas.');
    } }, icon('spark'), `Restore last layout (${saved.state.regions.length})`);
    this.root.querySelector('.slb-starters').append(restore);
  }

  // ---------- popovers and menus ----------
  /** One popover at a time, inside the dialog. `at` places it at a point (a context menu) instead of under `anchor`. */
  openPopover(anchor, fill, { at = null, className = '', label = '' } = {}) {
    if (this.popover && anchor && this.popover.anchor === anchor) { this.closePopover(true); return; }
    this.closePopover();
    const pop = el('div', { class: `slb-pop ${className}`.trim(), role: 'menu', 'aria-label': label || null });
    fill(pop);
    this.root.append(pop);
    const rect = at ? { left: at.x, right: at.x, top: at.y, bottom: at.y } : anchor.getBoundingClientRect();
    const width = pop.offsetWidth, height = pop.offsetHeight;
    let top = rect.bottom + 6;
    if (top + height > innerHeight - 8) top = rect.top - height - 6;
    let left = at ? rect.left : rect.left + (rect.right - rect.left) / 2 - width / 2;
    Object.assign(pop.style, { left: `${clamp(left, 8, innerWidth - width - 8)}px`, top: `${clamp(top, 8, innerHeight - height - 8)}px` });
    this.popover = { el: pop, anchor };
    anchor?.setAttribute('aria-expanded', 'true');
    requestAnimationFrame(() => pop.classList.add('is-in'));
    (pop.querySelector('[aria-checked=true]') || pop.querySelector('button:not(:disabled), input'))?.focus({ preventScroll: true });
  }

  closePopover(restoreFocus = false) {
    if (!this.popover) return;
    const { el: pop, anchor } = this.popover;
    this.popover = null;
    anchor?.setAttribute('aria-expanded', 'false');
    pop.remove();
    if (restoreFocus) (anchor || this.board)?.focus?.({ preventScroll: true });
  }

  menuItem(label, run, { iconName = null, dot = null, checked = null, disabled = false, hint = null, danger = false } = {}) {
    return el('button', { type: 'button', role: checked == null ? 'menuitem' : 'menuitemradio', class: `slb-menu-item${danger ? ' is-danger' : ''}`,
      'aria-checked': checked == null ? null : String(checked), disabled, onclick: () => { this.closePopover(true); run(); } },
    dot ? el('i', { class: `slb-dot is-${dot}`, 'aria-hidden': 'true' }) : iconName ? icon(iconName) : el('span', { class: 'slb-icon' }),
    el('span', { class: 'slb-menu-text', text: label }), hint ? el('kbd', { text: hint }) : null);
  }

  menuHead(title, note = '') {
    return el('div', { class: 'slb-pop-head' }, el('strong', { text: title }), note ? el('span', { text: note }) : null);
  }

  openGuides() {
    this.openPopover(this.gridButton, (pop) => pop.append(this.menuHead('Guides', 'Lines to compose against; snapping follows them.'),
      ...GUIDES.map(([mode, label]) => this.menuItem(label, () => { this.guideMode = mode; writeStore('heiss.mossLayout.guides', mode); this.renderToggles(); }, { checked: this.guideMode === mode }))),
    { label: 'Guides' });
  }

  openImport() {
    this.openPopover(this.importButton, (pop) => pop.append(this.menuHead('Import a layout', 'Replaces this layout; Undo brings it back.'),
      this.menuItem('Open a file…', () => this.importInput.click(), { iconName: 'open', hint: '.json · .png' }),
      this.menuItem('Paste from clipboard', () => void this.pasteFromClipboard(), { iconName: 'copy', hint: 'Ctrl V' }),
      el('p', { class: 'slb-pop-foot', text: 'A Studio or ComfyUI PNG brings back the layout it was made with. You can also drop a file anywhere here.' })),
    { label: 'Import a layout' });
  }

  /** The clipboard's image, read on request (a button). null when there is none or the browser refuses. */
  async clipboardImage() {
    if (!navigator.clipboard?.read) return null;
    for (const item of await navigator.clipboard.read()) {
      const type = item.types.find((kind) => kind.startsWith('image/'));
      if (type) return pastedFile(await item.getType(type));
    }
    return null;
  }

  async pasteImage() {
    try {
      const image = await this.clipboardImage();
      if (image) { await this.handleFiles([image]); return; }
      this.notice('The clipboard has no image. Copy one (or take a screenshot), then try again.', 'warning');
    } catch {
      this.notice('This browser keeps the clipboard private here: press Ctrl+V on the builder instead.', 'warning');
    }
  }

  async pasteFromClipboard() {
    try {
      const image = await this.clipboardImage().catch(() => null);
      if (image) { await this.handleFiles([image]); return; }
      const text = await navigator.clipboard.readText();
      if (text) { await this.importText(text, { source: 'the clipboard' }); return; }
      this.notice('The clipboard has no text. Copy a MOSS layout, or paste an image with Ctrl+V.', 'warning');
    } catch {
      this.notice('This browser keeps the clipboard private here: press Ctrl+V on the canvas instead.', 'warning');
    }
  }

  openReference() {
    if (!this.reference) { this.referenceInput.click(); return; }
    const ref = this.reference;
    this.openPopover(this.referenceButton, (pop) => {
      const opacity = el('input', { type: 'range', min: '5', max: '100', step: '5', value: String(Math.round(this.refView.opacity * 100)), 'aria-label': 'Reference opacity' });
      const shown = el('output', { text: `${opacity.value}%` });
      this.listen(opacity, 'input', () => { this.refView.opacity = Number(opacity.value) / 100; shown.textContent = `${opacity.value}%`; writeStore('heiss.mossLayout.ref', this.refView); this.renderReference(); });
      const fits = el('div', { class: 'slb-seg', role: 'radiogroup', 'aria-label': 'How the image covers the canvas' });
      const renderFits = () => fits.replaceChildren(...FITS.map(([value, label]) => el('button', { type: 'button', role: 'radio', 'aria-checked': String(this.refView.fit === value),
        onclick: () => { this.refView.fit = value; writeStore('heiss.mossLayout.ref', this.refView); this.renderReference(); renderFits(); } }, label)));
      renderFits();
      const ratio = (ref.width / ref.height) / (this.size.width / this.size.height);
      pop.append(...[this.menuHead('Reference image', 'Only a tracing guide: it is never sent with the prompt.'),
        el('div', { class: 'slb-ref-card' }, el('img', { src: ref.url, alt: '' }), el('div', {}, el('strong', { text: ref.name }), el('span', { text: `${ref.width} × ${ref.height}` }))),
        Math.abs(ratio - 1) > 0.02 ? el('p', { class: 'slb-pop-warn', text: `A different shape from the ${this.size.width} × ${this.size.height} canvas: Fill crops it, Fit letterboxes it, 1:1 keeps its pixels centred (the way layout boxes are measured).` }) : null,
        el('label', { class: 'slb-pop-row' }, el('span', { text: 'Opacity' }), opacity, shown),
        el('div', { class: 'slb-pop-row' }, el('span', { text: 'Shape' }), fits),
        el('div', { class: 'slb-pop-actions' },
          el('button', { type: 'button', class: 'slb-btn is-small', onclick: () => { this.closePopover(); this.referenceInput.click(); } }, icon('image'), 'Replace…'),
          el('button', { type: 'button', class: 'slb-btn is-small', title: 'Use the image on the clipboard (Ctrl+V works too)', onclick: () => { this.closePopover(true); void this.pasteImage(); } }, icon('copy'), 'Paste'),
          el('button', { type: 'button', class: 'slb-btn is-small is-danger', onclick: () => { this.closePopover(true); this.clearReference(); } }, icon('trash'), 'Remove'))].filter(Boolean));
    }, { className: 'is-wide', label: 'Reference image' });
  }

  openPlace(anchor = this.placeButton, at = null) {
    const selected = this.region(this.selected);
    const target = selected && !selected.locked ? selected : null;
    const kind = KINDS.find(([name]) => name === this.tool)[1].toLowerCase();
    this.openPopover(anchor, (pop) => {
      const oneTiles = el('div', { class: 'slb-tiles' }), splitTiles = el('div', { class: 'slb-tiles' });
      const renderTiles = () => {
        oneTiles.replaceChildren(...PLACE_ONE.map(([id, label, columns, rows, cell]) => this.placeTile(label, this.placementRects(columns, rows, cell ? [cell] : null), () => this.place(this.placementRects(columns, rows, cell ? [cell] : null), !!target, label))));
        splitTiles.replaceChildren(...PLACE_SPLIT.map(([id, label, columns, rows]) => this.placeTile(label, this.placementRects(columns, rows, allCells(columns, rows)), () => this.place(this.placementRects(columns, rows, allCells(columns, rows)), false, label))));
      };
      renderTiles();
      const gutter = el('input', { type: 'checkbox', checked: this.gutters });
      this.listen(gutter, 'change', () => { this.gutters = gutter.checked; writeStore('heiss.mossLayout.gutters', this.gutters); renderTiles(); });
      pop.append(this.menuHead('Place', target ? `Shapes move box ${pad2(this.number(target))}; splits add ${kind} boxes.` : `Adds ${kind} boxes. Pick the kind in the toolbar.`),
        el('p', { class: 'slb-pop-label', text: target ? 'Move the selected box' : 'One box' }), oneTiles,
        el('p', { class: 'slb-pop-label', text: 'Split the canvas' }), splitTiles,
        el('label', { class: 'slb-pop-check' }, gutter, el('span', { text: 'Gutters between and around boxes' })));
    }, { at, className: 'is-place', label: 'Placement presets' });
  }

  /** Editor rectangles for a preset; `cells` null means the centred half-area box. */
  placementRects(columns, rows, cells) {
    const { width, height } = this.size;
    const gap = this.gutters ? Math.max(16, Math.round((Math.min(width, height) * 0.03) / 8) * 8) : 0;
    if (!cells) {
      const side = Math.SQRT1_2;
      return [{ x: (1 - side) / 2, y: (1 - side) / 2, w: side, h: side }];
    }
    return gridRects(columns, rows, cells, gap / width, gap / height);
  }

  placeTile(label, rects, onclick) {
    const { width, height } = this.size;
    const k = 40 / Math.max(width, height), w = width * k, h = height * k;
    const svg = svgEl('svg', { viewBox: `-1 -1 ${w + 2} ${h + 2}`, width: w + 2, height: h + 2, 'aria-hidden': 'true' });
    svg.append(svgEl('rect', { x: 0, y: 0, width: w, height: h, rx: 2, class: 'slb-tile-frame' }));
    for (const rect of rects) svg.append(svgEl('rect', { x: rect.x * w, y: rect.y * h, width: rect.w * w, height: rect.h * h, rx: 1.5, class: 'slb-tile-box' }));
    return el('button', { type: 'button', role: 'menuitem', class: 'slb-tile', title: label, 'aria-label': label, onclick: () => { this.closePopover(true); onclick(); } }, svg, el('span', { text: label }));
  }

  place(rects, moveSelected, label) {
    if (moveSelected) {
      const region = this.region(this.selected);
      if (!region || region.locked) return;
      Object.assign(region, rects[0]);
      this.renderAll(); this.commit();
      this.notice(`Box ${pad2(this.number(region))} → ${label.toLowerCase()}.`);
      return;
    }
    const added = rects.map((rect) => ({ id: uid(), kind: this.tool, ...rect, text: '', description: '', relation: '', colors: [], tags: [] }));
    // Reading order (top-left first) gets the lowest numbers: it goes deepest within the new front block.
    added.reverse();
    this.state.regions.unshift(...added);
    this.selected = added[added.length - 1].id;
    this.renderAll(); this.commit();
    if (added.length > 1) this.notice(`Added ${added.length} ${this.tool} boxes (${label.toLowerCase()}). Describe each one; Undo removes them all.`);
    this.inspector.querySelector('textarea')?.focus({ preventScroll: true });
  }

  contextMenu(event) {
    event.preventDefault();
    const boxEl = event.target.closest('.slb-box');
    const at = { x: event.clientX, y: event.clientY };
    if (!boxEl) { this.openPlace(null, at); return; }
    this.select(boxEl.dataset.id);
    const region = this.region(this.selected);
    if (!region) return;
    this.openPopover(null, (pop) => pop.append(this.menuHead(`Box ${pad2(this.number(region))}`, region.locked ? 'Locked' : ''),
      ...KINDS.map(([kind, label, key]) => this.menuItem(label, () => this.setKind(region.id, kind), { dot: kind, checked: region.kind === kind })),
      el('hr'),
      this.menuItem(region.locked ? 'Unlock' : 'Lock in place', () => this.toggleLock(region.id), { iconName: region.locked ? 'unlock' : 'lock', hint: 'L' }),
      this.menuItem('Duplicate', () => this.duplicate(), { iconName: 'dup', hint: 'Ctrl D' }),
      this.menuItem('Bring to front', () => this.move(-1), { iconName: 'front', hint: ']' }),
      this.menuItem('Send to back', () => this.move(1), { iconName: 'back', hint: '[' }),
      el('hr'),
      this.menuItem('Remove', () => this.remove(), { iconName: 'trash', hint: 'Del', danger: true, disabled: !!region.locked })),
    { at, label: `Box ${pad2(this.number(region))}` });
  }

  /** Arrow keys move between a popover's items. True when handled. */
  popoverKey(event) {
    const pop = this.popover?.el;
    if (!pop || !pop.contains(event.target) || event.target.matches('input[type=range], textarea, input[type=text], input:not([type])')) return false;
    const keys = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1, Home: -Infinity, End: Infinity };
    if (!(event.key in keys)) return false;
    const items = [...pop.querySelectorAll('button:not(:disabled), input')];
    if (!items.length) return false;
    event.preventDefault();
    const at = items.indexOf(event.target), step = keys[event.key];
    const next = step === -Infinity ? 0 : step === Infinity ? items.length - 1 : (at + step + items.length) % items.length;
    items[next].focus({ preventScroll: true });
    return true;
  }

  // ---------- reference image and files ----------
  hasFiles(event) { return [...(event.dataTransfer?.types || [])].includes('Files'); }

  dragFiles(event) {
    if (!this.hasFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
    this.root.classList.add('is-dropping');
  }

  paste(event) {
    const data = event.clipboardData;
    if (!data) return;
    const image = [...data.files].find((file) => file.type.startsWith('image/'));
    if (image) { event.preventDefault(); void this.handleFiles([pastedFile(image)]); return; }
    if (event.target.closest?.('input, textarea, [contenteditable="true"]')) return;
    const text = data.getData('text/plain');
    if (!text) return;
    event.preventDefault();
    if (findLayout(text)) void this.importText(text, { source: 'the clipboard' });
    else this.notice('That is not a MOSS layout. Click a field to paste text into it, or paste an image to trace.', 'warning');
  }

  /** Images become the reference (and offer their layout, when a PNG carries one); text files are imported. */
  async handleFiles(list, { importOnly = false } = {}) {
    const files = [...list];
    const textFile = files.find((file) => /json|text/.test(file.type) || /\.(json|txt|bbox)$/i.test(file.name));
    const image = files.find((file) => file.type.startsWith('image/'));
    if (textFile) { await this.importText(await textFile.text(), { source: textFile.name }); return; }
    if (!image) { if (files.length) this.notice('Drop an image to trace, or a layout .json.', 'warning'); return; }
    let layout = null;
    if (image.type === 'image/png') {
      try { for (const text of await pngTexts(await image.arrayBuffer())) { layout = findLayout(text); if (layout) break; } } catch { layout = null; }
    }
    if (importOnly) {
      if (layout) await this.importText(layout, { source: image.name });
      else this.notice(`${image.name} carries no MOSS layout. Use the Reference button to trace over it instead.`, 'warning');
      return;
    }
    const placed = await this.setReference(image, !layout);
    if (!placed || !layout) return;
    const blank = !this.state.regions.length && !this.state.caption.trim();
    if (blank) await this.importText(layout, { source: image.name, extra: 'The image is the reference underneath.' });
    else this.notice(`${image.name} is the reference now, and it carries a layout.`, 'info', { label: 'Use its layout', run: () => void this.importText(layout, { source: image.name }) });
  }

  async setReference(file, announce = true) {
    const url = URL.createObjectURL(file);
    const probe = new Image();
    probe.src = url;
    try { await probe.decode(); } catch { URL.revokeObjectURL(url); this.notice(`${file.name || 'That image'} could not be read as an image.`, 'warning'); return false; }
    if (sessionReference?.url && sessionReference.url !== url) URL.revokeObjectURL(sessionReference.url);
    sessionReference = this.reference = { url, name: file.name || 'Pasted image', width: probe.naturalWidth, height: probe.naturalHeight };
    this.renderReference();
    if (announce) {
      const ratio = (probe.naturalWidth / probe.naturalHeight) / (this.size.width / this.size.height);
      this.notice(Math.abs(ratio - 1) > 0.02
        ? `Reference ${probe.naturalWidth} × ${probe.naturalHeight} is cropped to the canvas shape (change it under Reference). AI reads it as shown.`
        : 'Reference placed under the boxes. It is never sent with the prompt.', 'info', { label: 'Extract layout + prompt', run: () => void this.extractLayout() });
    }
    return true;
  }

  clearReference() {
    if (sessionReference?.url) URL.revokeObjectURL(sessionReference.url);
    sessionReference = this.reference = null;
    this.renderReference();
    this.notice('Reference image removed.');
  }

  async importText(text, { source = 'the clipboard', extra = '' } = {}) {
    const layout = findLayout(text);
    if (!layout) { this.notice(`No MOSS layout found in ${source}.`, 'warning'); return false; }
    try {
      const { imported, note } = await this.readLayout(layout);
      const had = this.state.regions.length > 0 || !!this.state.caption.trim();
      this.fromImport(imported);
      this.selected = null;
      this.renderAll(); this.commit();
      const count = this.state.regions.length;
      this.notice([note || `Imported ${count} ${count === 1 ? 'box' : 'boxes'} from ${source}.`, extra, had ? 'Undo brings back what you had.' : ''].filter(Boolean).join(' '));
      return true;
    } catch (error) {
      this.notice(error.message, 'warning');
      return false;
    }
  }

  // ---------- AI assistant ----------
  async checkAi(force = false) {
    if (this.aiModels && !force) return this.aiModels;
    try {
      const response = await fetch('/api/moss-layout-ai/status', { cache: 'no-store' });
      this.aiModels = response.ok ? await response.json() : { lfm3: false, wevisone: false, offline: true };
    } catch { this.aiModels = { lfm3: false, wevisone: false, offline: true }; }
    return this.aiModels;
  }

  openAi() {
    if (this.ai) { this.notice('The assistant is working: Esc or Stop cancels it.'); return; }
    const ref = this.reference, selected = this.region(this.selected);
    const target = selected && !selected.locked ? selected : null;
    const empty = this.state.regions.filter((region) => !region.locked && !region.description.trim());
    const n = this.state.regions.length;
    this.openPopover(this.aiButton, (pop) => {
      const models = el('div', { class: 'slb-ai-models' });
      const paint = (found) => models.replaceChildren(...[['LFM3-VL', 'writes', found?.lfm3], ['WeVisOne-VL', 'finds', found?.wevisone]].map(([name, role, ok]) =>
        el('span', { class: `slb-ai-model${ok == null ? '' : ok ? ' is-ok' : ' is-off'}`, title: ok === false ? `${name} is not loaded in ComfyUI.` : `${name} ${role}.` }, el('i'), name)));
      paint(this.aiModels);
      if (!this.aiModels || this.aiModels.offline) void this.checkAi(true).then((found) => { if (models.isConnected) paint(found); });
      const action = (label, iconName, run, { primary = false, disabled = false, title = '' } = {}) =>
        el('button', { type: 'button', class: `slb-btn is-small${primary ? ' is-primary' : ''}`, disabled, title: title || null, onclick: () => { this.closePopover(true); run(); } }, icon(iconName), label);
      // From the reference image
      const look = el('input', { type: 'text', class: 'slb-input is-line', placeholder: 'Only look for… (optional: knight, lantern)', 'aria-label': 'Objects to look for (optional)', autocomplete: 'off' });
      look.value = this.aiLabels;
      this.listen(look, 'input', () => { this.aiLabels = look.value; writeStore('heiss.mossLayout.aiLabels', look.value); });
      const lettering = el('input', { type: 'checkbox', checked: this.aiFindText });
      this.listen(lettering, 'change', () => { this.aiFindText = lettering.checked; writeStore('heiss.mossLayout.aiText', lettering.checked); });
      this.listen(look, 'keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); event.stopPropagation(); this.closePopover(true); void this.extractLayout(); } });
      const fromImage = ref
        ? [el('div', { class: 'slb-ref-card' }, el('img', { src: ref.url, alt: '' }), el('div', {}, el('strong', { text: ref.name }), el('span', { text: 'Read as the canvas shows it' })),
            el('div', { class: 'slb-ref-swap' },
              el('button', { type: 'button', class: 'slb-btn is-small', title: 'Pick another image', onclick: () => { this.closePopover(true); this.referenceInput.click(); } }, icon('image'), 'Replace…'),
              el('button', { type: 'button', class: 'slb-btn is-small', title: 'Use the image on the clipboard (Ctrl+V works too)', onclick: () => { this.closePopover(true); void this.pasteImage(); } }, icon('copy'), 'Paste'))),
          look,
          el('label', { class: 'slb-pop-check' }, lettering, el('span', { text: 'Read lettering into text boxes' })),
          el('div', { class: 'slb-pop-actions is-start' },
            action('Extract layout + prompt', 'spark', () => void this.extractLayout(), { primary: true }),
            action('Lettering', 'text', () => void this.findLettering(), { title: 'Add a text box for each line of lettering in the reference' }),
            action(target ? `Snap ${pad2(this.number(target))}` : 'Snap', 'target', () => void this.snapBox(), { disabled: !target, title: target ? 'Fit the selected box to what it describes in the reference' : 'Select a box to fit it to its object' }))]
        : [el('div', { class: 'slb-pop-actions is-start' }, action('Add an image to read…', 'image', () => this.referenceInput.click(), { primary: true }),
            action('Paste image', 'copy', () => void this.pasteImage(), { title: 'Use the image on the clipboard (Ctrl+V works too)' })),
          el('p', { class: 'slb-pop-foot', text: 'Drop, paste or pick an image: the assistant finds its objects and lettering and writes a layout and prompt for it.' })];
      // From words
      const words = el('textarea', { class: 'slb-input', rows: 3, 'aria-label': 'What to make or change', spellcheck: 'true',
        placeholder: n ? 'Change it: move the title to the top, add a cat on the left…  (or describe a new picture)' : 'Describe the picture: a night-market poster, a big neon title, two friends under umbrellas…' });
      words.value = this.aiRequest || (!n ? this.state.caption : '');
      this.listen(words, 'input', () => { this.aiRequest = words.value; });
      const plan = () => { this.closePopover(true); void this.planLayout(words.value); };
      const edit = () => { this.closePopover(true); void this.editLayout(words.value); };
      this.listen(words, 'keydown', (event) => {
        if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); event.stopPropagation(); n ? edit() : plan(); }
      });
      const fromWords = [words, el('div', { class: 'slb-pop-actions is-start' },
        action('New layout', 'layout', () => void this.planLayout(words.value), { primary: !n, title: 'Plan a whole new layout from the words (Ctrl+Enter when the canvas is empty)' }),
        action(n ? 'Change this layout' : 'Change layout', 'pen', () => void this.editLayout(words.value), { primary: !!n, disabled: !n, title: n ? 'Apply the instruction to these boxes (Ctrl+Enter); locked boxes stay' : 'Draw or import a layout first' }))];
      // Captions
      const describe = el('div', { class: 'slb-pop-actions is-start' },
        action(empty.length ? `Describe ${empty.length} empty ${empty.length === 1 ? 'box' : 'boxes'}` : 'Every box is described', 'spark', () => void this.describeBoxes(empty), { disabled: !empty.length }),
        action(target ? `Rewrite ${pad2(this.number(target))}` : 'Rewrite box', 'pen', () => void this.describeBoxes([target], true), { disabled: !target, title: target ? 'Write a new caption for the selected box' : 'Select a box first' }));
      pop.append(...[el('div', { class: 'slb-pop-head is-ai' }, el('strong', {}, icon('spark'), 'AI assistant'), models),
        el('p', { class: 'slb-pop-label', text: 'From the reference image' }), ...fromImage,
        el('hr'), el('p', { class: 'slb-pop-label', text: 'From words' }), ...fromWords,
        el('hr'), el('p', { class: 'slb-pop-label', text: `Captions${ref ? ' (it looks at the reference too)' : ''}` }), describe,
        this.aiLast ? el('div', { class: 'slb-pop-actions is-start' }, action('Another take', 'redo', () => void this.again(), { title: 'Run the last request again with a little more freedom' })) : null,
        el('p', { class: 'slb-pop-foot', text: 'Runs on this computer. Every result is one Undo away; locked boxes are kept. Same request, same answer, instantly.' })].filter(Boolean));
    }, { className: 'is-ai', label: 'AI assistant' });
  }

  extractLayout(fresh = false) {
    if (!this.reference) { this.referenceInput.click(); return null; }
    return this.runAi('image', { labels: this.aiLabels, findText: this.aiFindText }, { fresh });
  }

  planLayout(request, fresh = false) {
    if (!String(request || '').trim()) { this.notice('Write what the picture should show first.', 'warning'); return null; }
    return this.runAi('text', { request }, { fresh });
  }

  editLayout(request, fresh = false) {
    if (!String(request || '').trim()) { this.notice('Write what to change first.', 'warning'); return null; }
    if (!this.state.regions.length) return this.planLayout(request, fresh);
    return this.runAi('edit', { request, layout: this.aiLayout(this.state.regions) }, { fresh });
  }

  describeBoxes(targets, rewrite = false, fresh = false) {
    const list = targets.filter(Boolean);
    if (!list.length) return null;
    return this.runAi('describe', { layout: this.aiLayout(list), request: this.state.caption }, { fresh, targets: list.map((region) => region.id), rewrite, thinking: list.map((region) => region.id) });
  }

  findLettering(fresh = false) { return this.runAi('ocr', {}, { fresh }); }

  snapBox(fresh = false) {
    const region = this.region(this.selected);
    if (!region || region.locked) return null;
    const query = region.description.trim() || region.text.trim() || region.tags[0] || '';
    if (!query) { this.notice('Give the box a caption first, so the assistant knows what to look for.', 'warning'); return null; }
    return this.runAi('snap', { query: query.slice(0, 300) }, { fresh, targets: [region.id], thinking: [region.id] });
  }

  again() {
    const last = this.aiLast;
    if (!last) return null;
    if (last.task === 'describe') {
      const list = last.targets.map((id) => this.region(id)).filter(Boolean);
      return list.length ? this.describeBoxes(list, true, true) : null;
    }
    if (last.task === 'snap') return this.snapBox(true);
    return this.runAi(last.task, last.task === 'edit' ? { ...last.extra, layout: this.aiLayout(this.state.regions) } : last.extra, { fresh: true });
  }

  aiLayout(regions) { return { caption: this.state.caption, meta: this.state.meta, items: regionsToGrid(regions) }; }

  /** The reference as the canvas shows it (same crop or letterbox), at most AI_SIDE px: what the user sees is what the model reads. */
  async referenceData() {
    const ref = this.reference;
    const fit = FITS.some(([value]) => value === this.refView.fit) ? this.refView.fit : 'cover';
    const key = `${ref.url}|${fit}|${this.size.width}x${this.size.height}`;
    if (this.refData?.key === key) return this.refData.url;
    const image = new Image();
    image.src = ref.url;
    await image.decode();
    const k = Math.min(1, AI_SIDE / Math.max(this.size.width, this.size.height));
    const out = { width: Math.round(this.size.width * k), height: Math.round(this.size.height * k) };
    const canvas = el('canvas', { width: out.width, height: out.height });
    const context = canvas.getContext('2d');
    context.fillStyle = '#000'; context.fillRect(0, 0, out.width, out.height);
    context.imageSmoothingQuality = 'high';
    const rect = fitRect({ width: ref.width, height: ref.height }, this.size, fit, out);
    context.drawImage(image, rect.x, rect.y, rect.w, rect.h);
    this.refData = { key, url: canvas.toDataURL('image/jpeg', 0.92) };
    return this.refData.url;
  }

  async runAi(task, extra, { fresh = false, targets = [], rewrite = false, thinking = [] } = {}) {
    if (this.ai || this.closed) return;
    this.closePopover();
    const body = { task, width: this.size.width, height: this.size.height, fresh, ...extra };
    if (this.reference && (task === 'image' || task === 'snap' || task === 'ocr' || task === 'describe')) {
      try { body.image = await this.referenceData(); } catch { this.notice('The reference image could not be read.', 'warning'); return; }
    }
    const job = this.ai = { task, started: performance.now(), steps: [], step: 0, tokens: 0, stepAt: performance.now(), phase: 'Starting…', id: null, canceled: false, thinking };
    this.renderAi();
    try {
      const response = await fetch('/api/moss-layout-ai', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `The assistant could not start (${response.status}).`);
      job.id = data.jobId;
      let result = null;
      while (!job.canceled) {
        const state = await fetch(`/api/jobs/${encodeURIComponent(job.id)}`, { cache: 'no-store' }).then((reply) => reply.json());
        if (state.progress) this.aiProgress(job, state.progress);
        if (state.status === 'done') { result = state.result; break; }
        if (state.status === 'error') throw Object.assign(new Error(state.error || 'The assistant failed.'), { restart: !!state.restart });
        if (state.status === 'canceled' || state.status === 'missing') { job.canceled = true; break; }
        await new Promise((resolve) => setTimeout(resolve, 150));
      }
      if (job.canceled || this.closed || !result) return;
      job.finished = true;
      this.aiLast = { task, extra, targets };
      await this.applyAi(task, result, { targets, rewrite });
    } catch (error) {
      if (!job.canceled && !this.closed) {
        this.aiModels = null;
        this.notice(error.message, 'warning', error.restart ? null : { label: 'Try again', run: () => void this.runAi(task, extra, { fresh, targets, rewrite, thinking }) });
      }
    } finally {
      if (this.ai === job) { this.ai = null; this.renderAi(); }
    }
  }

  aiProgress(job, progress) {
    if (Array.isArray(progress.steps)) job.steps = progress.steps;
    if (Array.isArray(progress.done)) job.done = progress.done;
    const step = Number(progress.step) || 0;
    if (step !== job.step) { job.step = step; job.stepAt = performance.now(); job.tokens = 0; }
    if (progress.phase) job.phase = progress.phase;
    if (Number.isFinite(progress.tokens) && progress.tokens > job.tokens) job.tokens = progress.tokens;
    this.paintAi(true);
  }

  cancelAi(silent = false) {
    const job = this.ai;
    if (!job) return;
    job.canceled = true;
    if (job.id) void fetch(`/api/jobs/${encodeURIComponent(job.id)}/cancel`, { method: 'POST' }).catch(() => null);
    this.ai = null;
    this.renderAi();
    if (!silent) this.notice('Stopped. Nothing was changed.');
  }

  renderAi() {
    const job = this.ai;
    this.root.classList.toggle('is-ai', !!job);
    this.root.dataset.aiTask = job?.task || '';
    this.aiButton.classList.toggle('is-running', !!job);
    for (const [id, box] of this.boxes) box.classList.toggle('is-thinking', !!job?.thinking?.includes(id));
    clearInterval(this.aiTimer); this.aiTimer = null;
    if (!job) {
      this.aiCard.classList.remove('is-shown');
      clearTimeout(this.aiHide);
      this.aiHide = setTimeout(() => { if (!this.ai) this.aiCard.hidden = true; }, 260);
      return;
    }
    clearTimeout(this.aiHide);
    const titles = { image: 'Reading the image', text: 'Planning a layout', edit: 'Editing the layout', describe: 'Writing captions', snap: 'Snapping the box', ocr: 'Reading lettering' };
    this.aiParts = { steps: el('ol', { class: 'slb-ai-steps' }), time: el('span', { class: 'slb-ai-time' }), meter: el('span', { class: 'slb-ai-meter' }), rendered: '' };
    this.aiCard.replaceChildren(
      el('div', { class: 'slb-ai-orb', 'aria-hidden': 'true' }, el('i'), el('i'), icon('spark')),
      el('div', { class: 'slb-ai-main' },
        el('div', { class: 'slb-ai-top' }, el('strong', { text: titles[job.task] || 'Working' }), this.aiParts.time),
        this.aiParts.steps, this.aiParts.meter),
      el('button', { type: 'button', class: 'slb-btn is-small slb-ai-stop', onclick: () => this.cancelAi(), title: 'Stop (Esc)' }, icon('stop'), 'Stop'));
    this.aiCard.hidden = false;
    requestAnimationFrame(() => { if (this.ai === job) this.aiCard.classList.add('is-shown'); });
    this.aiTimer = setInterval(() => this.paintAi(), 100);
    this.paintAi(true);
  }

  paintAi(full = false) {
    const job = this.ai, parts = this.aiParts;
    if (!job || !parts) return;
    const now = performance.now();
    parts.time.textContent = `${((now - job.started) / 1000).toFixed(1)} s`;
    if (full) {
      const steps = job.steps.length ? job.steps : [job.phase];
      const done = job.done || [];
      const signature = `${steps.join('|')}#${job.step}#${done.join(',')}`;
      if (parts.rendered !== signature) {
        parts.rendered = signature;
        // ComfyUI may run steps out of the listed order, so finished steps come from the server's set.
        parts.steps.replaceChildren(...steps.map((label, index) => {
          const finished = done.includes(index), live = !finished && index === job.step;
          return el('li', { class: finished ? 'is-done' : live ? 'is-live' : '' }, el('i', { 'aria-hidden': 'true' }, finished ? icon('check') : null), el('span', { text: label }));
        }));
      }
    }
    parts.meter.textContent = job.tokens ? `${job.tokens} tokens` : job.id ? 'Thinking…' : 'Sending…';
  }

  async applyAi(task, result, { targets, rewrite }) {
    const took = result.cached ? 'instantly (same request as before)' : `in ${result.seconds} s`;
    const born = (regions) => { this.born = new Map(regions.slice().reverse().map((region, index) => [region.id, index])); };
    const finish = (text) => {
      // renderAll leaves a focused summary alone (typing); an AI result replaces it either way.
      this.captionInput.value = this.state.caption;
      this.selected = this.region(this.selected) ? this.selected : null;
      this.renderAll(); this.commit(); this.born = null;
      this.notice(text, 'info', { label: 'Undo', run: () => this.undo() });
    };
    if (task === 'image' || task === 'text' || task === 'edit') {
      const { imported } = await this.readLayout(JSON.stringify(result.layout));
      const previous = this.state;
      this.fromImport(imported);
      // Fresh ids: the node numbers its boxes layer_1…, which kept locked boxes may already use.
      for (const region of this.state.regions) region.id = uid();
      this.state.canvas = previous.canvas;
      // Your palette carries into a planned or edited layout; an image brings its own look.
      if (!this.state.palette.length && task !== 'image') this.state.palette = previous.palette;
      if (task === 'edit') {
        if (!this.state.caption.trim()) this.state.caption = previous.caption;
        if (!this.state.meta.length) this.state.meta = previous.meta;
        this.state.regions = carryColours(previous.regions, this.state.regions);
      }
      this.state.regions = keepLocked(previous.regions, this.state.regions);
      born(this.state.regions.filter((region) => !region.locked));
      this.selected = null;
      const count = this.state.regions.length, kept = previous.regions.filter((region) => region.locked).length;
      const what = task === 'image' ? 'Read the image' : task === 'text' ? 'Planned the layout' : 'Edited the layout';
      finish(`${what}: ${count} ${count === 1 ? 'box' : 'boxes'} and a summary, ${took}.${kept ? ` ${kept} locked ${kept === 1 ? 'box' : 'boxes'} kept.` : ''}`);
      return;
    }
    if (task === 'describe') {
      // Items come back in the order they were sent: back to front of the targets.
      const items = result.layout?.items || [];
      const order = targets.slice().reverse();
      let filled = 0;
      items.forEach((item, index) => {
        const region = this.region(order[index]), caption = String(item?.caption || '').trim();
        if (!region || region.locked || !caption || (!rewrite && region.description.trim())) return;
        region.description = caption; filled += 1;
      });
      if (!this.state.caption.trim() && result.layout?.caption) this.state.caption = result.layout.caption;
      if (!this.state.meta.length && Array.isArray(result.layout?.meta)) this.state.meta = result.layout.meta.slice(0, 6);
      if (!filled) { this.renderAll(); this.notice('The assistant wrote no captions for those boxes. Try again or add a scene note in the summary.', 'warning'); return; }
      finish(`Wrote ${filled} ${filled === 1 ? 'caption' : 'captions'}, ${took}.`);
      return;
    }
    const boxes = (result.boxes || []).map((found) => ({ ...found, rect: gridRect(found.bbox) }));
    if (task === 'snap') {
      const region = this.region(targets[0]);
      if (!region || region.locked) return;
      if (!boxes.length) { this.notice(`Could not find “${(region.description || region.text).slice(0, 60)}” in the reference.`, 'warning'); return; }
      const best = boxes.reduce((top, found) => (overlap(found.rect, region) > overlap(top.rect, region) ? found : top), boxes[0]);
      Object.assign(region, best.rect);
      finish(`Box ${pad2(this.number(region))} fitted to “${best.label.slice(0, 50)}”, ${took}.`);
      return;
    }
    if (task === 'ocr') {
      const lines = ocrLines(result.boxes || [], this.size);
      if (!lines.length) { this.notice('No lettering found in the reference.', 'warning'); return; }
      const added = [];
      let updated = 0;
      for (const line of lines) {
        const rect = gridRect(line.bbox);
        const existing = this.state.regions.find((region) => region.kind === 'text' && overlap(region, rect) >= 0.3);
        if (existing) { if (!existing.text.trim() && !existing.locked) { existing.text = line.text; updated += 1; } continue; }
        added.push({ id: uid(), kind: 'text', ...rect, text: line.text, description: '', relation: '', colors: [], tags: [] });
      }
      this.state.regions.unshift(...added.reverse());
      born(added);
      finish(`Found ${lines.length} ${lines.length === 1 ? 'line' : 'lines'} of lettering: ${added.length} new text ${added.length === 1 ? 'box' : 'boxes'}${updated ? `, ${updated} filled in` : ''}, ${took}. Describe their look for the best match.`);
    }
  }

  async copyIdeogram() {
    const text = JSON.stringify(toIdeogram(this.state), null, 2);
    try {
      await navigator.clipboard.writeText(text);
      const characters = this.state.regions.filter((region) => region.kind === 'character').length;
      this.notice(`Copied as Ideogram 4 JSON (${this.state.regions.length} elements, front first${characters ? `; ${characters} ${characters === 1 ? 'character is' : 'characters are'} an object there` : ''}).`);
    } catch { this.notice('The browser blocked the clipboard here. Save as .json instead.', 'warning'); }
  }

  // ---------- zoom and pan ----------
  setZoom(value, anchor = null) {
    const next = clamp(value, 1, ZOOM_STEPS[ZOOM_STEPS.length - 1]);
    if (Math.abs(next - this.zoom) < 1e-3 || !this.scale) return;
    const stage = this.stage.getBoundingClientRect(), before = this.board.getBoundingClientRect();
    const point = anchor || { x: stage.left + stage.width / 2, y: stage.top + stage.height / 2 };
    const fx = (point.x - before.left) / before.width, fy = (point.y - before.top) / before.height;
    this.zoom = next;
    this.layoutStage();
    const after = this.board.getBoundingClientRect();
    this.stage.scrollLeft += after.left + fx * after.width - point.x;
    this.stage.scrollTop += after.top + fy * after.height - point.y;
  }

  zoomStep(direction) {
    const next = direction > 0 ? ZOOM_STEPS.find((step) => step > this.zoom + 1e-3) : [...ZOOM_STEPS].reverse().find((step) => step < this.zoom - 1e-3);
    this.setZoom(next ?? (direction > 0 ? ZOOM_STEPS[ZOOM_STEPS.length - 1] : 1));
  }

  setSpace(down) {
    if (this.spaceHeld === down) return;
    this.spaceHeld = down;
    this.root?.classList.toggle('is-space', down);
  }

  panStart(event) {
    if (!(event.button === 1 || (event.button === 0 && this.spaceHeld))) return;
    event.preventDefault(); event.stopPropagation();
    this.pan = { x: event.clientX, y: event.clientY, left: this.stage.scrollLeft, top: this.stage.scrollTop };
    this.stage.setPointerCapture(event.pointerId);
    this.root.classList.add('is-panning');
  }

  panMove(event) {
    if (!this.pan) return;
    this.stage.scrollLeft = this.pan.left - (event.clientX - this.pan.x);
    this.stage.scrollTop = this.pan.top - (event.clientY - this.pan.y);
  }

  panEnd(event) {
    if (!this.pan) return;
    this.pan = null;
    if (this.stage.hasPointerCapture(event.pointerId)) this.stage.releasePointerCapture(event.pointerId);
    this.root.classList.remove('is-panning');
  }

  // ---------- editing ----------
  select(id) {
    this.selected = id;
    for (const [boxId, box] of this.boxes) box.classList.toggle('is-selected', boxId === id);
    this.renderLayers(); this.renderInspector();
  }

  setKind(id, kind) {
    const region = this.region(id);
    if (!region || region.kind === kind) return;
    region.kind = kind;
    this.renderBoxes(); this.renderLayers(); this.renderInspector(); this.commit();
  }

  toggleLock(id = this.selected) {
    const region = this.region(id);
    if (!region) return;
    region.locked = !region.locked;
    if (!region.locked) delete region.locked;
    this.renderBoxes(); this.renderLayers(); this.renderInspector(); this.commit();
    this.notice(region.locked ? `Box ${pad2(this.number(region))} locked: dragging on it draws a new box. Locks stay in this editor, not in the prompt.` : `Box ${pad2(this.number(region))} unlocked.`);
  }

  align(where) {
    const region = this.region(this.selected);
    if (!region || region.locked) return;
    if (where === 'left') region.x = 0;
    else if (where === 'centre') region.x = (1 - region.w) / 2;
    else if (where === 'right') region.x = 1 - region.w;
    else if (where === 'top') region.y = 0;
    else if (where === 'middle') region.y = (1 - region.h) / 2;
    else if (where === 'bottom') region.y = 1 - region.h;
    this.renderBoxes(); this.renderInspector(); this.commit();
  }

  applyStarter(starter) {
    this.state = { caption: this.state.caption.trim() && !this.state.regions.length ? this.state.caption : starter.caption,
      meta: [...starter.meta], canvas: starter.canvas, palette: [],
      regions: starter.items.map(([kind, x, y, w, h, description, text = '']) => ({ id: uid(), kind, x, y, w, h, description, text, relation: '', colors: [], tags: [] })).reverse() };
    this.selected = null;
    this.renderAll(); this.commit();
    this.notice(`${starter.name} starter placed. Rewrite every caption and text for your image; Undo brings back what you had.`);
  }

  addCentered() {
    const { width, height } = this.size;
    const w = this.tool === 'text' ? 0.6 : 0.4, h = this.tool === 'text' ? Math.max(0.08, 96 / height) : 0.4 * width / height;
    const region = { id: uid(), kind: this.tool, x: (1 - w) / 2, y: clamp((1 - h) / 2, 0, 1 - Math.min(h, 1)), w, h: Math.min(h, 1), text: '', description: '', relation: '', colors: [], tags: [] };
    this.state.regions.unshift(region);
    this.selected = region.id;
    this.renderAll(); this.commit();
    this.inspector.querySelector('textarea')?.focus();
  }

  duplicate() {
    const region = this.region(this.selected);
    if (!region) return;
    const copy = { ...plain(region), id: uid(), x: clamp(region.x + 0.03, 0, 1 - region.w), y: clamp(region.y + 0.03, 0, 1 - region.h) };
    delete copy.locked;
    this.state.regions.unshift(copy); this.selected = copy.id;
    this.renderAll(); this.commit();
  }

  remove() {
    const region = this.region(this.selected);
    if (!region) return;
    if (region.locked) { this.notice(`Box ${pad2(this.number(region))} is locked; unlock it (L) to remove it.`, 'warning'); return; }
    this.state.regions = this.state.regions.filter((item) => item.id !== this.selected);
    this.selected = null; this.renderAll(); this.commit();
  }

  reorder(from, to) {
    if (from === to || to < 0 || to >= this.state.regions.length) return;
    const [region] = this.state.regions.splice(from, 1);
    this.state.regions.splice(to, 0, region);
    this.renderAll(); this.commit();
  }

  move(delta) {
    const index = this.state.regions.findIndex((item) => item.id === this.selected);
    if (index >= 0) this.reorder(index, index + delta);
  }

  nudge(dx, dy) {
    const region = this.region(this.selected);
    if (!region) return;
    if (region.locked) { this.notice(`Box ${pad2(this.number(region))} is locked; press L to unlock it.`); return; }
    region.x = clamp(region.x + dx / this.size.width, 0, 1 - region.w);
    region.y = clamp(region.y + dy / this.size.height, 0, 1 - region.h);
    this.paintBox(this.boxes.get(region.id), region);
    this.softCommit();
  }

  keydown(event) {
    if (this.closed) return;
    const typing = event.target.closest?.('input:not([type=checkbox]):not([type=range]), textarea, select, [contenteditable="true"]');
    const mod = event.ctrlKey || event.metaKey, key = event.key.toLowerCase();
    if (key === 'escape') {
      event.preventDefault(); event.stopPropagation();
      if (this.popover) this.closePopover(true);
      else if (this.drag) this.cancelDrag();
      else if (typing) event.target.blur();
      else if (this.ai) this.cancelAi();
      else if (this.selected) this.select(null);
      else this.requestClose();
      return;
    }
    if (mod && key === 'enter') { event.preventDefault(); this.apply(); return; }
    event.stopPropagation();
    if (this.popoverKey(event) || typing) return;
    if (this.popover?.el.contains(event.target)) return;
    if (mod && key === 'z') { event.preventDefault(); event.shiftKey ? this.redo() : this.undo(); return; }
    if (mod && key === 'y') { event.preventDefault(); this.redo(); return; }
    if (mod && key === 'd') { event.preventDefault(); this.duplicate(); return; }
    if (mod && (key === '=' || key === '+')) { event.preventDefault(); this.zoomStep(1); return; }
    if (mod && key === '-') { event.preventDefault(); this.zoomStep(-1); return; }
    if (mod && key === '0') { event.preventDefault(); this.setZoom(1); return; }
    if (mod || event.altKey) return;
    if (key === ' ' && !event.target.closest('button, [role=option], li')) { event.preventDefault(); this.setSpace(true); return; }
    if (key === 'delete' || key === 'backspace') { event.preventDefault(); this.remove(); }
    else if (key === '[') this.move(1);
    else if (key === ']') this.move(-1);
    else if (key === 'o' || key === 'c' || key === 't') { this.tool = { o: 'object', c: 'character', t: 'text' }[key]; this.renderToggles(); }
    else if (key === 'l') this.toggleLock();
    else if (key === 'i') { event.preventDefault(); this.openAi(); }
    else if (key === 'p') { event.preventDefault(); this.openPlace(this.placeButton); }
    else if (key === '=' || key === '+') this.zoomStep(1);
    else if (key === '-' || key === '_') this.zoomStep(-1);
    else if (key === '0') this.setZoom(1);
    else if (key.startsWith('arrow') && this.selected) {
      event.preventDefault();
      const step = event.shiftKey ? 64 : 16;
      this.nudge(key === 'arrowleft' ? -step : key === 'arrowright' ? step : 0, key === 'arrowup' ? -step : key === 'arrowdown' ? step : 0);
    }
  }

  // ---------- pointer ----------
  point(event) {
    const rect = this.board.getBoundingClientRect();
    return { x: clamp((event.clientX - rect.left) / rect.width, 0, 1), y: clamp((event.clientY - rect.top) / rect.height, 0, 1) };
  }

  pointerDown(event) {
    if (event.button !== 0 || this.pan) return;
    this.closePopover();
    const target = event.target;
    const boxEl = target.closest('.slb-box');
    const handle = target.dataset?.handle;
    const point = this.point(event);
    this.board.focus({ preventScroll: true });
    // Ctrl/Cmd-drag draws over existing boxes (a full-canvas background, for example); so does any drag on a locked box.
    const force = (event.ctrlKey || event.metaKey) && !handle;
    let region = boxEl && !force ? this.region(boxEl.dataset.id) : null;
    let through = null;
    if (region?.locked) { through = region.id; region = null; }
    if (region && region.id !== this.selected) this.select(region.id);
    if (!region) {
      region = { id: uid(), kind: this.tool, x: point.x, y: point.y, w: 0, h: 0, text: '', description: '', relation: '', colors: [], tags: [] };
      this.state.regions.unshift(region);
      this.selected = region.id;
      this.renderBoxes();
    }
    event.preventDefault();
    this.board.setPointerCapture(event.pointerId);
    this.drag = { id: region.id, mode: handle || (region.w === 0 ? 'draw' : 'move'), origin: point, start: { ...region }, before: JSON.stringify(this.state), moved: false, through };
    this.root.classList.add('is-dragging');
  }

  pointerMove(event) {
    if (!this.drag) { if (!this.pan && event.pointerType !== 'touch') this.renderCoords(this.point(event)); return; }
    const region = this.region(this.drag.id);
    if (!region) return;
    const { width: W, height: H } = this.size;
    const point = this.point(event), { start, origin, mode } = this.drag;
    let dx = point.x - origin.x, dy = point.y - origin.y;
    if (Math.abs(dx) + Math.abs(dy) > 0.002) this.drag.moved = true;
    this.renderCoords(point);
    const snap = this.snap && !event.altKey;
    const lines = snap ? this.snapLines(region.id) : null;
    const guides = [];
    if (mode === 'move') {
      // Shift keeps the move on one axis.
      if (event.shiftKey) { if (Math.abs(dx * W) >= Math.abs(dy * H)) dy = 0; else dx = 0; }
      let x = clamp(start.x + dx, 0, 1 - start.w), y = clamp(start.y + dy, 0, 1 - start.h);
      if (lines) {
        const sx = !(event.shiftKey && dx === 0) && this.snapAxis([x, x + start.w / 2, x + start.w], lines.x, this.board.clientWidth);
        const sy = !(event.shiftKey && dy === 0) && this.snapAxis([y, y + start.h / 2, y + start.h], lines.y, this.board.clientHeight);
        if (sx) { x = clamp(x + sx.delta, 0, 1 - start.w); guides.push(['x', sx.line]); }
        if (sy) { y = clamp(y + sy.delta, 0, 1 - start.h); guides.push(['y', sy.line]); }
      }
      Object.assign(region, { x, y });
    } else {
      // Draw: the free corner follows the pointer. Resize: only the dragged edges move.
      const minW = 8 / W, minH = 8 / H;
      let left = start.x, top = start.y, right = start.x + start.w, bottom = start.y + start.h;
      const sides = mode === 'draw' ? (point.x >= origin.x ? 'e' : 'w') + (point.y >= origin.y ? 's' : 'n') : mode;
      let ex = mode === 'draw' ? point.x : sides.includes('w') ? start.x + dx : start.x + start.w + dx;
      let ey = mode === 'draw' ? point.y : sides.includes('n') ? start.y + dy : start.y + start.h + dy;
      const movesX = /[we]/.test(sides), movesY = /[ns]/.test(sides);
      if (lines) {
        const sx = movesX && this.snapAxis([ex], lines.x, this.board.clientWidth);
        const sy = movesY && this.snapAxis([ey], lines.y, this.board.clientHeight);
        if (sx) { ex += sx.delta; guides.push(['x', sx.line]); }
        if (sy) { ey += sy.delta; guides.push(['y', sy.line]); }
      }
      // Ctrl/Cmd on a handle resizes about the box centre.
      const centred = mode !== 'draw' && (event.ctrlKey || event.metaKey);
      if (mode === 'draw') {
        left = Math.min(origin.x, ex); right = Math.max(origin.x, ex); top = Math.min(origin.y, ey); bottom = Math.max(origin.y, ey);
      } else if (centred) {
        const cx = start.x + start.w / 2, cy = start.y + start.h / 2;
        if (movesX) { const half = clamp(Math.abs(ex - cx), minW / 2, Math.min(cx, 1 - cx)); left = cx - half; right = cx + half; }
        if (movesY) { const half = clamp(Math.abs(ey - cy), minH / 2, Math.min(cy, 1 - cy)); top = cy - half; bottom = cy + half; }
      } else {
        if (sides.includes('w')) left = clamp(ex, 0, right - minW);
        if (sides.includes('e')) right = clamp(ex, left + minW, 1);
        if (sides.includes('n')) top = clamp(ey, 0, bottom - minH);
        if (sides.includes('s')) bottom = clamp(ey, top + minH, 1);
      }
      // Shift keeps the box's proportions (a square while drawing).
      if (event.shiftKey) {
        const from = mode === 'draw' ? { x: origin.x, y: origin.y, w: 0, h: 0 } : start;
        const ratio = mode === 'draw' ? 1 : (start.w * W) / (start.h * H);
        if (Number.isFinite(ratio) && ratio > 0) ({ left, top, right, bottom } = keepAspect(sides, from, { left, top, right, bottom }, ratio, centred, W, H));
        guides.length = 0;
      }
      Object.assign(region, { x: clamp(left, 0, 1), y: clamp(top, 0, 1), w: clamp(right - left, 0, 1), h: clamp(bottom - top, 0, 1) });
    }
    this.showGuides(guides);
    this.paintBox(this.boxes.get(region.id), region);
  }

  snapLines(id) {
    const guides = GUIDE_LINES[this.guideMode] || [];
    const x = [0, 0.5, 1, ...guides], y = [0, 0.5, 1, ...guides];
    for (const other of this.state.regions) {
      if (other.id === id || !other.w) continue;
      x.push(other.x, other.x + other.w / 2, other.x + other.w);
      y.push(other.y, other.y + other.h / 2, other.y + other.h);
    }
    return { x, y };
  }

  snapAxis(points, lines, pixels) {
    let best = null;
    for (const point of points) for (const line of lines) {
      const distance = (line - point) * pixels;
      if (Math.abs(distance) <= SNAP_PX && (!best || Math.abs(distance) < Math.abs(best.delta * pixels))) best = { delta: line - point, line };
    }
    return best;
  }

  showGuides(guides) {
    this.guides.replaceChildren(...guides.map(([axis, value]) => el('i', { class: `slb-guide is-${axis}`, style: axis === 'x' ? { left: `${value * 100}%` } : { top: `${value * 100}%` } })));
  }

  pointerUp(event) {
    if (!this.drag) return;
    const region = this.region(this.drag.id);
    const { mode, moved, through } = this.drag;
    this.drag = null;
    this.root.classList.remove('is-dragging');
    this.showGuides([]);
    if (this.board.hasPointerCapture(event.pointerId)) this.board.releasePointerCapture(event.pointerId);
    if (mode === 'draw' && region && (region.w * this.size.width < 12 || region.h * this.size.height < 12)) {
      // A click (not a drag) on a locked box selects it.
      this.state.regions = this.state.regions.filter((item) => item.id !== region.id);
      this.selected = through && this.region(through) ? through : null;
      this.renderAll();
      return;
    }
    this.renderAll();
    if (moved || mode === 'draw') this.commit();
    if (mode === 'draw') this.inspector.querySelector('textarea')?.focus({ preventScroll: true });
  }

  cancelDrag() {
    if (!this.drag) return;
    this.state = JSON.parse(this.drag.before);
    this.drag = null;
    this.root.classList.remove('is-dragging');
    this.showGuides([]);
    if (!this.region(this.selected)) this.selected = null;
    this.renderAll();
  }

  // ---------- output ----------
  async copy() {
    const text = this.result?.prompt;
    if (!text) return;
    try { await navigator.clipboard.writeText(text); this.notice('Prompt copied.'); }
    catch {
      const range = document.createRange(); range.selectNodeContents(this.output);
      const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
      this.notice('Clipboard is unavailable here; the prompt is selected, press Ctrl+C.', 'warning');
    }
  }

  /** Download the layout as indented JSON (the same prompt, readable, and importable here or in other MOSS editors). */
  async saveJson() {
    try {
      const result = await call('serialize', this.payload('pretty'));
      if (!result.prompt.trim()) { this.notice('Write a summary caption or add a box first.', 'warning'); return; }
      const layout = result.mode === 'layout';
      const blob = new Blob([`${result.prompt}\n`], { type: layout ? 'application/json' : 'text/plain' });
      const url = URL.createObjectURL(blob);
      const name = `moss-layout-${this.size.width}x${this.size.height}.${layout ? 'json' : 'txt'}`;
      const link = el('a', { href: url, download: name, hidden: true });
      this.root.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      this.notice(`Saved ${name}. Its boxes are for ${this.size.width} × ${this.size.height}.`);
    } catch (error) { this.notice(error.message, 'warning'); }
  }

  async apply() {
    clearTimeout(this.compileTimer); clearTimeout(this.softTimer);
    this.commit();
    const current = studioSize();
    if (current.width !== this.size.width || current.height !== this.size.height) this.size = current;
    try {
      const result = await call('serialize', this.payload());
      if (!result.prompt.trim()) { this.notice('Write a summary caption or add a box first.', 'warning'); return; }
      if (result.mode === 'layout') rememberSize(result.prompt, this.size);
      try { localStorage.removeItem(AUTOSAVE); } catch { /* ignore */ }
      this.onApply?.(result.prompt, { mode: result.mode, items: this.state.regions.length, size: this.size, warnings: result.warnings });
      this.close();
    } catch (error) {
      this.error = error; this.renderOutput(); this.notice(error.message, 'warning');
    }
  }
}

/**
 * Keep `ratio` (width / height in pixels) while resizing: corners follow the larger change, edges set the
 * other side around its centre. The fixed corner, edge or centre stays put, and the box shrinks to fit.
 */
export function keepAspect(sides, start, rect, ratio, centred, W, H) {
  let w = (rect.right - rect.left) * W, h = (rect.bottom - rect.top) * H;
  const horizontal = /[we]/.test(sides), vertical = /[ns]/.test(sides);
  if (horizontal && vertical ? w / Math.max(h, 1e-9) > ratio : horizontal) h = w / ratio; else w = h * ratio;
  const sx = start.x * W, sy = start.y * H, sw = start.w * W, sh = start.h * H;
  const dirX = centred || !horizontal ? 0 : sides.includes('w') ? -1 : 1;
  const dirY = centred || !vertical ? 0 : sides.includes('n') ? -1 : 1;
  const ax = dirX === 1 ? sx : dirX === -1 ? sx + sw : sx + sw / 2;
  const ay = dirY === 1 ? sy : dirY === -1 ? sy + sh : sy + sh / 2;
  const roomX = dirX === 1 ? W - ax : dirX === -1 ? ax : 2 * Math.min(ax, W - ax);
  const roomY = dirY === 1 ? H - ay : dirY === -1 ? ay : 2 * Math.min(ay, H - ay);
  const k = Math.min(1, roomX / Math.max(w, 1e-9), roomY / Math.max(h, 1e-9));
  w *= k; h *= k;
  const left = dirX === 1 ? ax : dirX === -1 ? ax - w : ax - w / 2;
  const top = dirY === 1 ? ay : dirY === -1 ? ay - h : ay - h / 2;
  return { left: left / W, top: top / H, right: (left + w) / W, bottom: (top + h) / H };
}

let measurer;
/** Width of one line at 100 px in the text preview's weight (falls back to an estimate without canvas). */
function measure(line, family) {
  measurer ??= document.createElement('canvas').getContext('2d');
  if (!measurer) return Array.from(line).reduce((sum, char) => sum + (CJK.test(char) ? 100 : 62), 0);
  measurer.font = `750 100px ${family || 'sans-serif'}`;
  return measurer.measureText(line).width * 1.02;
}

/** Light JSON colouring for the compiled one-line prompt. */
function highlight(text) {
  if (!text.trim().startsWith('{')) return [el('span', { class: 'slb-j-str', text })];
  const parts = [];
  const pattern = /("(?:[^"\\]|\\.)*")(\s*:)?|(-?\d+(?:\.\d+)?)|([{}[\],])/g;
  let last = 0, match;
  while ((match = pattern.exec(text))) {
    if (match.index > last) parts.push(document.createTextNode(text.slice(last, match.index)));
    if (match[1]) {
      parts.push(el('span', { class: match[2] ? 'slb-j-key' : 'slb-j-str', text: match[1] }));
      if (match[2]) parts.push(document.createTextNode(match[2]));
    } else if (match[3]) parts.push(el('span', { class: 'slb-j-num', text: match[3] }));
    else {
      parts.push(el('span', { class: 'slb-j-punct', text: match[4] }));
      // Break the one-line prompt at item boundaries so it reads well (display only).
      if (match[4] === ',' && text[match.index + 1] === '{') parts.push(el('br'));
    }
    last = pattern.lastIndex;
  }
  if (last < text.length) parts.push(document.createTextNode(text.slice(last)));
  return parts;
}
