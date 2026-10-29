import assert from "node:assert/strict";
import { test } from "node:test";
import { attachStylePicker } from "../web/style-picker.mjs";

const categories = {
  "cinema.noir": "cinema/classic",
  "cinema.softfocus": "cinema/modern",
  "ink.line": "illustration/ink",
  "custom.wash": "custom/watercolor",
};

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
  attachStylePicker(node, categories);
  return { node, category: node.widgets.find((w) => w.name === "category"), style: node.widgets.find((w) => w.name === "style") };
}

function select(widget, value) {
  widget.value = value;
  widget.callback?.(value);
}

test("category and parent filters narrow choices without substituting the selected style", () => {
  const { category, style } = fixture();
  assert.equal(category.value, "cinema/classic");
  assert.deepEqual(style.options.values, ["cinema.noir"]);
  select(category, "illustration");
  assert.deepEqual(style.options.values, ["ink.line"]);
  assert.equal(style.value, "cinema.noir");
  select(style, "ink.line");
  assert.equal(style.value, "ink.line");
  assert.equal(category.value, "illustration");
  select(category, "cinema");
  assert.deepEqual(style.options.values, ["cinema.noir", "cinema.softfocus"]);
  assert.equal(style.value, "ink.line");
  select(category, "All categories");
  assert.deepEqual(style.options.values, Object.keys(categories));
});

test("restored IDs infer their actual catalog category, including custom packs", () => {
  const { node, category, style } = fixture();
  select(category, "illustration");
  style.value = "custom.wash";
  node.onConfigure({});
  assert.equal(category.value, "custom/watercolor");
  assert.deepEqual(style.options.values, ["custom.wash"]);
  assert.equal(style.value, "custom.wash");
  // A removed pack's saved ID stays visible so execution can report the missing style.
  style.value = "removed.style";
  node.onConfigure({});
  assert.equal(category.value, "All categories");
  assert.equal(style.value, "removed.style");
});

test("browsing state leaves the saved widget prefix and executable inputs intact", () => {
  const { node, category } = fixture();
  assert.deepEqual(node.widgets.slice(0, 4).map((w) => w.name), ["prompt", "category", "style", "model"]);
  select(category, "custom");
  const saved = node.widgets.filter((w) => w.serialize !== false).map((w) => w.value);
  assert.deepEqual(saved, ["A ceramic bird", "cinema.noir", "generic", 0.75, "", []]);
  const inputs = Object.fromEntries(node.widgets.filter((w) => w.options?.serialize !== false).map((w) => [w.name, w.value]));
  assert.equal(inputs.style, "cinema.noir");
  assert.ok(!("category" in inputs));
});

test("filters stay independent across nodes and full IDs disambiguate style choices", () => {
  const first = fixture();
  const second = fixture("ink.line");
  select(first.category, "cinema");
  assert.deepEqual(second.style.options.values, ["ink.line"]);
  assert.equal(second.style.value, "ink.line");
  select(first.style, "custom.wash");
  assert.equal(first.category.value, "custom/watercolor");
});

test("existing configure and style callbacks retain their context, arguments and result", () => {
  const calls = [];
  const { node, style } = fixture();
  // Test hook chaining on a fresh node with existing host callbacks.
  node.widgets = node.widgets.filter((w) => w.name !== "category");
  style.options.values = Object.keys(categories);
  node.onConfigure = function (info) { calls.push([this, info]); return "configured"; };
  style.callback = function (value) { calls.push([this, value]); return "selected"; };
  attachStylePicker(node, categories);
  assert.equal(node.onConfigure("saved"), "configured");
  assert.equal(style.callback.call(style, "cinema.noir"), "selected");
  assert.deepEqual(calls, [[node, "saved"], [style, "cinema.noir"]]);
});
