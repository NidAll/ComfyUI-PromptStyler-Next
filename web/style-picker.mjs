const ALL = "All categories";

export function attachStylePicker(node, categories) {
  const style = node.widgets.find((widget) => widget.name === "style");
  const ids = [...style.options.values];
  const groups = new Set();
  for (const path of Object.values(categories)) {
    const parts = path.split("/");
    for (let i = 1; i <= parts.length; i++) groups.add(parts.slice(0, i).join("/"));
  }

  function matches(id, category) {
    return category === ALL || categories[id] === category || categories[id]?.startsWith(`${category}/`);
  }

  function filter() {
    style.options.values = ids.filter((id) => matches(id, category.value));
    node.setDirtyCanvas(true, true);
  }

  const category = node.addWidget("combo", "category", ALL, filter, {
    values: [ALL, ...[...groups].sort()],
    serialize: false,
  });
  // ComfyUI uses separate flags for workflow persistence and API inputs.
  category.serialize = false;
  category.tooltip = "Filter style choices, including subcategories. Your selected style stays active until you choose another.";
  // Only the existing style ID is serialized; this control is browsing state.
  node.widgets.splice(node.widgets.indexOf(category), 1);
  node.widgets.splice(node.widgets.indexOf(style), 0, category);

  function restore() {
    category.value = categories[style.value] ?? ALL;
    filter();
  }

  const onConfigure = node.onConfigure;
  node.onConfigure = function () {
    const result = onConfigure?.apply(this, arguments);
    restore();
    return result;
  };

  const onStyle = style.callback;
  style.callback = function () {
    const result = onStyle?.apply(this, arguments);
    if (!matches(style.value, category.value)) restore();
    return result;
  };
  restore();
}
