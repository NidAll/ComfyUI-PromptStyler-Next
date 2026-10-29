import assert from "node:assert/strict";
import { test } from "node:test";
import {
  attachStylePicker,
  buildCategoryGroups,
  claimAxisLabels,
  clauseIntensityStatus,
  filterStyles,
  styleDetailsForModel,
} from "../web/style-picker.mjs";

const categories = {
  "cinema.noir": "cinema/classic",
  "cinema.softfocus": "cinema/modern",
  "ink.line": "illustration/ink",
  "custom.wash": "custom/watercolor",
};

const styles = [
  {
    id: "cinema.noir",
    name: "Café Noir",
    description: "A restrained monochrome cinema look.",
    category: "cinema/classic",
    kind: "style",
    tags: ["noir", "black and white"],
    models: [],
    claims: { medium: "silver gelatin print" },
    clauses: [
      { axis: "medium", text: "silver gelatin print texture", tags: ["photographic"], min_intensity: 0 },
      { axis: "texture", text: "visible film grain", tags: ["grain"], min_intensity: 0.9 },
    ],
    variants: {
      anima: {
        clauses: [{ axis: "medium", text: "Anima-compatible film rendering", tags: ["photographic"], min_intensity: 0.5 }],
        negative: ["digital color"],
      },
    },
  },
  {
    id: "cinema.softfocus",
    name: "Soft Focus",
    description: "Gentle highlight bloom with low contrast.",
    category: "cinema/modern",
    kind: "style",
    tags: ["portrait", "glow"],
    models: ["anima"],
    claims: { lighting: "soft highlight bloom" },
    clauses: [{ axis: "lighting", text: "gentle highlight bloom", tags: ["soft"], min_intensity: 0.4 }],
  },
  {
    id: "ink.line",
    name: "Ink Line",
    description: "Crisp drawn contours with open paper.",
    category: "illustration/ink",
    kind: "modifier",
    tags: ["drawing", "linework"],
    models: [],
    claims: { medium: "ink on paper" },
    clauses: [{ axis: "texture", text: "dry ink contours", tags: ["ink"], min_intensity: 0.25 }],
  },
  {
    id: "custom.wash",
    name: "Café Watercolor",
    description: "Transparent watercolor edges and paper grain.",
    category: "custom/watercolor",
    kind: "grade",
    tags: ["watercolor", "wash"],
    models: ["flux"],
    claims: { palette: "warm transparent washes" },
    clauses: [{ axis: "palette", text: "warm transparent washes", tags: ["warm"], min_intensity: 0.3 }],
  },
];

function fixture(selected = "cinema.noir") {
  const node = {
    widgets: [
      { name: "prompt", value: "A ceramic bird" },
      { name: "style", value: selected, options: { values: Object.keys(categories) } },
      { name: "model", value: "generic" },
      { name: "intensity", value: 0.75 },
      { name: "negative", value: "" },
      { name: "locked_axes", value: [] },
    ],
    addWidget(type, name, value, callback, options) {
      const widget = { type, name, value, callback, options };
      this.widgets.push(widget);
      return widget;
    },
    setDirtyCanvas() {},
  };
  attachStylePicker(node, categories, styles);
  return {
    node,
    browse: node.widgets.find((w) => w.type === "button"),
    style: node.widgets.find((w) => w.name === "style"),
  };
}

function select(widget, value) {
  widget.value = value;
  widget.callback?.(value);
}

test("the explorer is the only visible style selection control", () => {
  const { node, browse, style } = fixture();
  assert.equal(style.hidden, true);
  assert.ok(!node.widgets.some((w) => w.name === "category"));
  assert.deepEqual(node.widgets.filter((w) => !w.hidden).slice(0, 3).map((w) => w.name),
    ["prompt", "Style explorer", "model"]);
  assert.equal(browse.label, "Style explorer · Café Noir");
  assert.equal(style.value, "cinema.noir");
  assert.deepEqual(style.options.values, Object.keys(categories));
});

test("restored IDs update the explorer label without substituting a style", () => {
  const { node, browse, style } = fixture();
  style.value = "custom.wash";
  node.onConfigure({});
  assert.equal(browse.label, "Style explorer · Café Watercolor");
  assert.equal(style.value, "custom.wash");
  style.value = "removed.style";
  node.onConfigure({});
  assert.equal(browse.label, "Style explorer · removed.style");
  assert.equal(style.value, "removed.style");
});

test("the hidden style retains the original saved widget prefix and API input", () => {
  const { node, browse, style } = fixture();
  assert.equal(browse.serialize, false);
  assert.equal(browse.options.serialize, false);
  const saved = node.widgets.filter((w) => w.serialize !== false).map((w) => w.value);
  assert.deepEqual(saved, ["A ceramic bird", "cinema.noir", "generic", 0.75, "", []]);
  const inputs = Object.fromEntries(node.widgets.filter((w) => w.options?.serialize !== false).map((w) => [w.name, w.value]));
  assert.equal(inputs.style, "cinema.noir");
  assert.ok(!("category" in inputs));
  assert.ok(!("Style explorer" in inputs));
  select(style, "ink.line");
  assert.equal(browse.label, "Style explorer · Ink Line");
});

test("existing configure and style callbacks retain their context, arguments and result", () => {
  const calls = [];
  const { node, style } = fixture();
  // Test hook chaining on a fresh node with existing host callbacks.
  node.widgets = node.widgets.filter((w) => w.type !== "button");
  style.options.values = Object.keys(categories);
  node.onConfigure = function (info) { calls.push([this, info]); return "configured"; };
  style.callback = function (value) { calls.push([this, value]); return "selected"; };
  attachStylePicker(node, categories);
  assert.equal(node.onConfigure("saved"), "configured");
  assert.equal(style.callback.call(style, "cinema.noir"), "selected");
  assert.deepEqual(calls, [[node, "saved"], [style, "cinema.noir"]]);
});

test("catalog search is accent-insensitive, token-AND, and spans name, ID, description, and tags", () => {
  assert.deepEqual(filterStyles(styles, { query: "cafe watercolor" }).map((item) => item.id), ["custom.wash"]);
  assert.deepEqual(filterStyles(styles, { query: "SOFTFOCUS cinema" }).map((item) => item.id), ["cinema.softfocus"]);
  assert.deepEqual(filterStyles(styles, { query: "highlight glow" }).map((item) => item.id), ["cinema.softfocus"]);
  assert.deepEqual(filterStyles(styles, { query: "ink dry" }), []);
  assert.deepEqual(filterStyles(styles, { query: "ink contours" }).map((item) => item.id), ["ink.line"]);
});

test("kind and parent category filters cover every style with readable hierarchy counts", () => {
  assert.deepEqual(filterStyles(styles, { kind: "style" }).map((item) => item.id), ["cinema.noir", "cinema.softfocus"]);
  assert.deepEqual(filterStyles(styles, { kind: "grade" }).map((item) => item.id), ["custom.wash"]);
  assert.deepEqual(filterStyles(styles, { kind: "modifier" }).map((item) => item.id), ["ink.line"]);
  assert.deepEqual(filterStyles(styles, { category: "cinema" }).map((item) => item.id), ["cinema.noir", "cinema.softfocus"]);
  assert.deepEqual(filterStyles(styles, { category: "cinema/classic" }).map((item) => item.id), ["cinema.noir"]);

  const groups = buildCategoryGroups(styles);
  assert.deepEqual(groups[0], { value: "", label: "All categories (4)", count: 4 });
  const illustration = groups.find((group) => group.label === "Illustration (1)");
  assert.ok(illustration);
  assert.deepEqual(illustration.children, [
    { value: "illustration", label: "All Illustration (1)", count: 1 },
    { value: "illustration/ink", label: "Ink (1)", count: 1 },
  ]);
});

test("model details use the selected variant and label intensity tiers without composing prompts", () => {
  const noir = styles[0];
  const anima = styleDetailsForModel(noir, "anima");
  assert.equal(anima.usesVariant, true);
  assert.equal(anima.clauses[0].text, "Anima-compatible film rendering");
  assert.deepEqual(anima.negative, ["digital color"]);

  const generic = styleDetailsForModel(noir, "generic");
  assert.equal(generic.usesVariant, false);
  assert.equal(generic.clauses[0].text, "silver gelatin print texture");
  assert.deepEqual(generic.negative, []);

  assert.deepEqual(clauseIntensityStatus(noir.clauses[1], 0.75), {
    active: false,
    label: "Starts at 0.9; current intensity 0.75",
  });
  assert.deepEqual(clauseIntensityStatus(noir.clauses[1], 0.9), {
    active: true,
    label: "Active at intensity 0.9",
  });
  assert.deepEqual(clauseIntensityStatus(noir.clauses[1], 0), {
    active: false,
    label: "Inactive at intensity 0",
  });
  assert.deepEqual(clauseIntensityStatus(noir.clauses[0], 0.75, ["medium"]), {
    active: false,
    protected: true,
    label: "Protected by workflow",
  });
  assert.deepEqual(claimAxisLabels({
    detail: "hierarchy.lettering-clearance",
    texture: "hierarchy.lettering-clearance",
  }), ["Detail", "Texture"]);
});
