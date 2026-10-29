const ALL_CATEGORIES = "All categories";
const ALL_KINDS = "all";
const PAGE_SIZE = 60;
const STYLE_TAG_ID = "psnext-style-picker-css";
const KIND_FILTERS = [
  { value: ALL_KINDS, label: "All styles" },
  { value: "style", label: "Looks" },
  { value: "grade", label: "Color grades" },
  { value: "modifier", label: "Effects" },
];

const KIND_LABELS = new Map(KIND_FILTERS.map(({ value, label }) => [value, label]));

export function filterStyles(styles, { query = "", kind = ALL_KINDS, category = "" } = {}) {
  const terms = foldText(query).split(/\s+/u).filter(Boolean);
  return styles.filter((style) => {
    if (kind !== ALL_KINDS && style.kind !== kind) return false;
    if (category && style.category !== category && !style.category?.startsWith(category + "/")) return false;
    const fields = [style.name, style.id, style.description, ...(Array.isArray(style.tags) ? style.tags : [])];
    const searchable = foldText(fields.filter((field) => typeof field === "string").join(" "));
    return terms.every((term) => searchable.includes(term));
  });
}

export function buildCategoryGroups(styles, { query = "", kind = ALL_KINDS } = {}) {
  const visible = filterStyles(styles, { query, kind });
  const allPaths = new Set();
  const counts = new Map();
  for (const style of styles) {
    const parts = categoryParts(style.category);
    for (let i = 1; i <= parts.length; i++) allPaths.add(parts.slice(0, i).join("/"));
  }
  for (const style of visible) {
    const parts = categoryParts(style.category);
    for (let i = 1; i <= parts.length; i++) {
      const path = parts.slice(0, i).join("/");
      counts.set(path, (counts.get(path) ?? 0) + 1);
    }
  }

  const roots = [...allPaths].filter((path) => !path.includes("/")).sort(compareText);
  return [
    { value: "", label: ALL_CATEGORIES + " (" + visible.length + ")", count: visible.length },
    ...roots.map((root) => {
      const paths = [...allPaths]
        .filter((path) => path === root || path.startsWith(root + "/"))
        .sort((a, b) => a.split("/").length - b.split("/").length || compareText(a, b));
      return {
        label: humanizePath(root) + " (" + (counts.get(root) ?? 0) + ")",
        children: paths.map((path) => {
          const parts = path.split("/");
          const suffix = parts.slice(1).map(humanizeSegment).join(" / ");
          const label = suffix || "All " + humanizeSegment(root);
          return {
            value: path,
            label: label + " (" + (counts.get(path) ?? 0) + ")",
            count: counts.get(path) ?? 0,
          };
        }),
      };
    }),
  ];
}

export function styleDetailsForModel(style, model) {
  const variant = model && style.variants && style.variants[model];
  const hasVariant = Boolean(variant && Array.isArray(variant.clauses));
  return {
    clauses: hasVariant ? variant.clauses : Array.isArray(style.clauses) ? style.clauses : [],
    negative: Array.isArray(variant?.negative)
      ? variant.negative
      : Array.isArray(style.negative) ? style.negative : [],
    usesVariant: hasVariant,
  };
}

export function claimAxisLabels(claims) {
  if (!claims || typeof claims !== "object" || Array.isArray(claims)) return [];
  return Object.keys(claims).map(humanizeSegment);
}

export function clauseIntensityStatus(clause, intensity, lockedAxes = []) {
  if (Array.isArray(lockedAxes) && lockedAxes.includes(clause.axis)) {
    return { active: false, protected: true, label: "Protected by workflow" };
  }
  const threshold = finiteNumber(clause.min_intensity) ? clause.min_intensity : 0;
  const current = finiteNumber(intensity) ? intensity : Number(intensity);
  if (!Number.isFinite(current)) {
    return { active: null, label: "Starts at intensity " + formatNumber(threshold) };
  }
  if (current === 0) return { active: false, label: "Inactive at intensity 0" };
  if (current < threshold) {
    return {
      active: false,
      label: "Starts at " + formatNumber(threshold) + "; current intensity " + formatNumber(current),
    };
  }
  return { active: true, label: "Active at intensity " + formatNumber(current) };
}

export function attachStylePicker(node, categories, styles = []) {
  const style = node.widgets.find((widget) => widget.name === "style");
  const ids = [...style.options.values];
  const categoryById = categories ?? {};
  const metadataById = new Map((Array.isArray(styles) ? styles : []).map((item) => [item.id, item]));
  const browserState = { query: "", kind: ALL_KINDS, category: "", visibleCount: PAGE_SIZE };
  const catalog = ids.map((id) => metadataById.get(id) ?? {
    id,
    name: id,
    description: "",
    category: categoryById[id] ?? "",
    kind: "style",
    tags: [],
    models: [],
    claims: {},
    clauses: [],
  });
  // Keep the original widget in its saved/API position, off every UI surface.
  style.hidden = true;

  function restore() {
    const selected = metadataById.get(style.value);
    browse.label = "Style explorer · " + (selected ? displayName(selected) : style.value);
    browse.tooltip = "Selected: " + style.value + ". Open the explorer to search and choose a style.";
    node.setDirtyCanvas(true, true);
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
    restore();
    return result;
  };

  const browse = node.addWidget("button", "Style explorer", "", openDialog, { serialize: false });
  browse.serialize = false;
  browse.options.serialize = false;
  browse.tooltip = "Search styles and inspect their claims, model eligibility, and intensity tiers before choosing.";
  node.widgets.splice(node.widgets.indexOf(browse), 1);
  node.widgets.splice(node.widgets.indexOf(style), 0, browse);
  restore();

  function openDialog() {
    if (typeof document === "undefined" || typeof document.createElement !== "function") return;
    ensureStyles();
    const previousFocus = document.activeElement;
    const graphCanvas = node.canvas?.canvas
      ?? node.canvas
      ?? node.graph?.list_of_graphcanvas?.find((item) => item.canvas?.isConnected)?.canvas;
    const modelWidget = node.widgets.find((widget) => widget.name === "model");
    const intensityWidget = node.widgets.find((widget) => widget.name === "intensity");
    const lockedAxesWidget = node.widgets.find((widget) => widget.name === "locked_axes");
    const dialogId = ++nextDialogId;
    const dialog = createElement("dialog", "psnext-style-picker");
    dialog.setAttribute("aria-labelledby", "psnext-style-picker-title-" + dialogId);
    const shell = createElement("div", "psnext-style-picker__shell");
    const heading = createElement("h2", "", "Style explorer");
    heading.id = "psnext-style-picker-title-" + dialogId;
    const headingBlock = createElement("header", "psnext-style-picker__header");
    headingBlock.append(heading);
    const closeButton = createButton("Close", "psnext-style-picker__close");
    closeButton.setAttribute("aria-label", "Close style browser");
    headingBlock.append(closeButton);
    shell.append(headingBlock);

    const controls = createElement("div", "psnext-style-picker__filters");
    const search = createLabeledControl("search", "Search styles", "search-" + dialogId);
    search.input.type = "search";
    search.input.placeholder = "Name, ID, description, or tag";
    search.input.autocomplete = "off";
    search.input.spellcheck = false;
    search.input.value = browserState.query;
    const kindSelect = createLabeledControl("kind", "Kind", "kind-" + dialogId);
    const categorySelect = createLabeledControl("category", "Category", "category-" + dialogId);
    controls.append(search.wrapper, kindSelect.wrapper, categorySelect.wrapper);
    shell.append(controls);

    const current = catalog.find((item) => item.id === style.value);
    const currentText = current
      ? "Current style: " + displayName(current) + " (" + current.id + ")"
      : "Current style ID: " + style.value;
    const currentBanner = createElement("p", "psnext-style-picker__current", currentText);
    currentBanner.setAttribute("aria-live", "polite");
    shell.append(currentBanner);

    const resultHeading = createElement("div", "psnext-style-picker__results-heading");
    const resultCount = createElement("p", "psnext-style-picker__result-count", "");
    resultCount.setAttribute("aria-live", "polite");
    resultHeading.append(resultCount);
    shell.append(resultHeading);
    const resultList = createElement("div", "psnext-style-picker__results");
    resultList.id = "psnext-style-picker-results-" + dialogId;
    resultList.setAttribute("role", "list");
    resultList.setAttribute("aria-label", "Matching styles");
    shell.append(resultList);

    const selectionStatus = createElement("p", "psnext-style-picker__chosen", "Choose a style, then apply it to the node.");
    selectionStatus.setAttribute("aria-live", "polite");
    const footer = createElement("footer", "psnext-style-picker__footer");
    footer.append(selectionStatus);
    const footerButtons = createElement("div", "psnext-style-picker__actions");
    const applyButton = createButton("Apply chosen style", "psnext-style-picker__apply");
    applyButton.disabled = true;
    footerButtons.append(applyButton, createButton("Close", "psnext-style-picker__close"));
    footer.append(footerButtons);
    shell.append(footer);
    dialog.append(shell);

    let chosenId = null;
    let visibleCount = browserState.visibleCount;
    let firstChooseButton = null;
    let focusButtonId = null;

    function updateCategoryOptions() {
      const selected = categorySelect.input.value || browserState.category;
      const groups = buildCategoryGroups(catalog, {
        query: search.input.value,
        kind: kindSelect.input.value || browserState.kind,
      });
      categorySelect.input.replaceChildren();
      for (const group of groups) {
        if (!group.children) {
          categorySelect.input.append(createOption(group.value, group.label));
          continue;
        }
        const optgroup = document.createElement("optgroup");
        optgroup.label = group.label;
        for (const item of group.children) optgroup.append(createOption(item.value, item.label));
        categorySelect.input.append(optgroup);
      }
      categorySelect.input.value = selected;
      if (categorySelect.input.value !== selected) browserState.category = "";
    }

    function updateKindOptions() {
      const selected = kindSelect.input.value || browserState.kind || ALL_KINDS;
      const base = filterStyles(catalog, { query: search.input.value, category: categorySelect.input.value });
      kindSelect.input.replaceChildren();
      for (const kind of KIND_FILTERS) {
        const count = kind.value === ALL_KINDS
          ? base.length
          : base.filter((item) => item.kind === kind.value).length;
        kindSelect.input.append(createOption(kind.value, kind.label + " (" + count + ")"));
      }
      kindSelect.input.value = selected;
      if (kindSelect.input.value !== selected) browserState.kind = ALL_KINDS;
    }

    function updateChosen() {
      const item = catalog.find((entry) => entry.id === chosenId);
      selectionStatus.textContent = item
        ? "Chosen: " + displayName(item) + " (" + item.id + "). Apply to update the node."
        : "Choose a style, then apply it to the node.";
      applyButton.disabled = !item;
    }

    function renderResults() {
      resultList.replaceChildren();
      const matches = filterStyles(catalog, {
        query: search.input.value,
        kind: kindSelect.input.value || ALL_KINDS,
        category: categorySelect.input.value,
      });
      const shown = matches.slice(0, visibleCount);
      resultCount.textContent = matches.length + " matching " + (matches.length === 1 ? "style" : "styles");
      if (matches.length > shown.length) {
        resultCount.textContent += " · showing " + shown.length + "; refine the filters or show more";
      }
      if (!matches.length) {
        resultList.append(createElement("p", "psnext-style-picker__empty", "No styles match these filters."));
      }
      firstChooseButton = null;
      let buttonToFocus = null;
      for (const item of shown) {
        const row = createElement("article", "psnext-style-picker__item");
        row.setAttribute("role", "listitem");
        if (item.id === style.value) {
          row.classList.add("is-current");
          row.append(createElement("span", "psnext-style-picker__badge", "Current workflow style"));
        }
        if (item.id === chosenId) row.append(createElement("span", "psnext-style-picker__badge is-chosen", "Chosen to apply"));

        const title = createElement("h3", "psnext-style-picker__name", displayName(item));
        const description = createElement(
          "p",
          "psnext-style-picker__description",
          typeof item.description === "string" && item.description ? item.description : "No description provided.",
        );
        row.append(title, description);
        row.append(createElement("p", "psnext-style-picker__line",
          (KIND_LABELS.get(item.kind) ?? humanizeSegment(item.kind)) + " · " + humanizePath(item.category)));
        appendModelEligibility(row, item.models, modelWidget?.value);
        appendStyleDetails(row, item, modelWidget?.value, intensityWidget?.value, lockedAxesWidget?.value);

        const chooseButton = createButton(item.id === chosenId ? "Chosen" : "Choose", "psnext-style-picker__choose");
        chooseButton.setAttribute("aria-label", "Choose " + displayName(item) + " (" + item.id + ")");
        chooseButton.addEventListener("click", () => {
          chosenId = item.id;
          focusButtonId = item.id;
          updateChosen();
          renderResults();
        });
        row.append(chooseButton);
        resultList.append(row);
        if (!firstChooseButton) firstChooseButton = chooseButton;
        if (item.id === focusButtonId) buttonToFocus = chooseButton;
      }
      if (matches.length > shown.length) {
        const moreButton = createButton("Show next " + PAGE_SIZE, "psnext-style-picker__more");
        moreButton.addEventListener("click", () => {
          focusButtonId = matches[visibleCount]?.id ?? null;
          visibleCount += PAGE_SIZE;
          browserState.visibleCount = visibleCount;
          renderResults();
        });
        resultList.append(moreButton);
      }
      focusButtonId = null;
      buttonToFocus?.focus();
    }

    function render() {
      updateCategoryOptions();
      updateKindOptions();
      renderResults();
    }

    function closeDialog() {
      if (dialog.open) dialog.close();
      else finishClose();
    }

    function finishClose() {
      dialog.remove();
      const focusTarget = previousFocus && previousFocus !== document.body && previousFocus.isConnected
        ? previousFocus
        : graphCanvas;
      if (typeof focusTarget?.focus === "function") focusTarget.focus();
    }

    search.input.addEventListener("input", () => {
      browserState.query = search.input.value;
      visibleCount = PAGE_SIZE;
      browserState.visibleCount = visibleCount;
      render();
    });
    kindSelect.input.addEventListener("change", () => {
      browserState.kind = kindSelect.input.value || ALL_KINDS;
      visibleCount = PAGE_SIZE;
      browserState.visibleCount = visibleCount;
      render();
    });
    categorySelect.input.addEventListener("change", () => {
      browserState.category = categorySelect.input.value;
      visibleCount = PAGE_SIZE;
      browserState.visibleCount = visibleCount;
      render();
    });
    closeButton.addEventListener("click", closeDialog);
    footerButtons.lastElementChild.addEventListener("click", closeDialog);
    applyButton.addEventListener("click", () => {
      if (!chosenId) return;
      style.value = chosenId;
      style.callback?.call(style, chosenId);
      closeDialog();
    });
    dialog.addEventListener("close", finishClose, { once: true });
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      closeDialog();
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) closeDialog();
    });
    dialog.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeDialog();
      } else if (event.key === "Enter" && !event.isComposing && event.target === search.input && firstChooseButton) {
        event.preventDefault();
        firstChooseButton.click();
      }
    });

    resultList.setAttribute("aria-labelledby", "psnext-style-picker-results-title-" + dialogId);
    resultCount.id = "psnext-style-picker-results-title-" + dialogId;
    updateChosen();
    render();
    document.body.append(dialog);
    dialog.showModal();
    search.input.focus();
  }
}

function appendTags(parent, tags) {
  if (!Array.isArray(tags) || tags.length === 0) return;
  const line = createElement("p", "psnext-style-picker__line");
  line.append(createElement("strong", "", "Tags: "));
  line.append(document.createTextNode(tags.filter((tag) => typeof tag === "string").join(", ")));
  parent.append(line);
}

function appendClaims(parent, claims) {
  const axes = claimAxisLabels(claims);
  if (axes.length) appendLabeledText(parent, "Claims", axes.join(", "));
}

function appendModelEligibility(parent, models, currentModel) {
  const eligible = Array.isArray(models) ? models.filter((model) => typeof model === "string") : [];
  const value = eligible.length ? eligible.join(", ") : "All model profiles";
  appendLabeledText(parent, "Model eligibility", value);
  if (eligible.length && currentModel && !eligible.includes(currentModel)) {
    appendLabeledText(parent, "Current model", currentModel + " is not listed; the style will not be substituted automatically.");
  }
}

function appendStyleDetails(parent, style, model, intensity, lockedAxes) {
  const details = styleDetailsForModel(style, model);
  const tags = Array.isArray(style.tags) ? style.tags : [];
  const claims = style.claims && typeof style.claims === "object" && !Array.isArray(style.claims)
    ? Object.keys(style.claims)
    : [];
  if (!tags.length && !claims.length && !details.clauses.length && !details.negative.length) return;

  const disclosure = createElement("details", "psnext-style-picker__details");
  disclosure.append(createElement("summary", "", "Visual directions"));
  appendLabeledText(disclosure, "Style ID", style.id);
  appendTags(disclosure, tags);
  appendClaims(disclosure, style.claims);
  if (details.clauses.length) {
    const section = createElement("section", "psnext-style-picker__details");
    section.append(createElement("h4", "", details.usesVariant
      ? "Instructions for " + model
      : "Shared visual directions"));
    const list = createElement("ul", "psnext-style-picker__detail-list");
    for (const clause of details.clauses) {
      const item = createElement("li");
      const text = typeof clause.text === "string" ? clause.text : String(clause.text ?? "");
      item.append(createElement("strong", "", humanizeSegment(clause.axis) + ": "));
      item.append(document.createTextNode(text));
      const status = clauseIntensityStatus(clause, intensity, lockedAxes);
      item.append(createElement(
        "span",
        "psnext-style-picker__threshold" + (status.active === false ? " is-inactive" : "")
          + (status.protected ? " is-protected" : ""),
        " — " + status.label,
      ));
      list.append(item);
    }
    section.append(list);
    disclosure.append(section);
  }
  if (details.negative.length) appendLabeledText(disclosure, "Negative additions", details.negative.join(", "));
  parent.append(disclosure);
}

function appendLabeledText(parent, label, value) {
  const line = createElement("p", "psnext-style-picker__line");
  line.append(createElement("strong", "", label + ": "));
  line.append(document.createTextNode(String(value ?? "")));
  parent.append(line);
}

function createLabeledControl(name, label, id) {
  const wrapper = createElement("label", "psnext-style-picker__control");
  const caption = createElement("span", "", label);
  wrapper.htmlFor = id;
  const input = createElement(name === "search" ? "input" : "select");
  input.id = id;
  wrapper.append(caption, input);
  return { wrapper, input };
}

function createOption(value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  return option;
}

function createButton(label, className) {
  const button = createElement("button", className, label);
  button.type = "button";
  return button;
}

function createElement(tag, className = "", text = undefined) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function ensureStyles() {
  if (document.getElementById(STYLE_TAG_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_TAG_ID;
  style.textContent = [
    "dialog.psnext-style-picker { color: var(--fg-color, #eee); background: var(--comfy-menu-bg, #242424); border: 1px solid var(--border-color, #555); border-radius: 12px; padding: 0; width: min(920px, calc(100vw - 24px)); max-width: calc(100vw - 24px); max-height: calc(100dvh - 24px); box-shadow: 0 18px 70px #0009; }",
    "dialog.psnext-style-picker::backdrop { background: #0009; }",
    "dialog.psnext-style-picker, dialog.psnext-style-picker * { box-sizing: border-box; }",
    "dialog.psnext-style-picker .psnext-style-picker__shell { display: flex; flex-direction: column; gap: 14px; max-height: calc(100dvh - 24px); overflow: auto; padding: 18px; }",
    "dialog.psnext-style-picker .psnext-style-picker__header, dialog.psnext-style-picker .psnext-style-picker__footer, dialog.psnext-style-picker .psnext-style-picker__actions, dialog.psnext-style-picker .psnext-style-picker__results-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }",
    "dialog.psnext-style-picker h2, dialog.psnext-style-picker h3, dialog.psnext-style-picker h4, dialog.psnext-style-picker p { margin: 0; }",
    "dialog.psnext-style-picker .psnext-style-picker__filters { display: grid; grid-template-columns: minmax(220px, 2fr) minmax(150px, 1fr) minmax(200px, 1fr); gap: 10px; }",
    "dialog.psnext-style-picker .psnext-style-picker__control { display: flex; flex-direction: column; gap: 5px; font-size: 0.9rem; }",
    "dialog.psnext-style-picker input, dialog.psnext-style-picker select, dialog.psnext-style-picker button { color: inherit; background: var(--comfy-input-bg, #171717); border: 1px solid var(--border-color, #555); border-radius: 6px; font: inherit; padding: 8px 10px; }",
    "dialog.psnext-style-picker button { cursor: pointer; }",
    "dialog.psnext-style-picker button:disabled { cursor: not-allowed; opacity: 0.55; }",
    "dialog.psnext-style-picker :focus-visible { outline: 2px solid var(--primary-color, #65adff); outline-offset: 2px; }",
    "dialog.psnext-style-picker .psnext-style-picker__current, dialog.psnext-style-picker .psnext-style-picker__chosen, dialog.psnext-style-picker .psnext-style-picker__result-count { color: var(--descrip-text, #c6c6c6); }",
    "dialog.psnext-style-picker .psnext-style-picker__results { display: flex; flex-direction: column; gap: 10px; overflow: auto; min-height: 100px; max-height: min(52vh, 620px); padding: 1px 4px 1px 1px; }",
    "dialog.psnext-style-picker .psnext-style-picker__item { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; padding: 12px; border: 1px solid var(--border-color, #484848); border-radius: 8px; }",
    "dialog.psnext-style-picker .psnext-style-picker__item.is-current { border-color: var(--primary-color, #65adff); }",
    "dialog.psnext-style-picker .psnext-style-picker__name { font-size: 1rem; }",
    "dialog.psnext-style-picker .psnext-style-picker__description { line-height: 1.4; }",
    "dialog.psnext-style-picker .psnext-style-picker__line { overflow-wrap: anywhere; line-height: 1.35; }",
    "dialog.psnext-style-picker .psnext-style-picker__details { width: 100%; padding-top: 5px; border-top: 1px solid var(--border-color, #484848); }",
    "dialog.psnext-style-picker .psnext-style-picker__details > summary { cursor: pointer; font-weight: 600; padding: 4px 0; }",
    "dialog.psnext-style-picker .psnext-style-picker__detail-list { display: flex; flex-direction: column; gap: 7px; margin: 7px 0 0; padding-left: 20px; }",
    "dialog.psnext-style-picker .psnext-style-picker__threshold { color: var(--descrip-text, #b9b9b9); font-size: 0.9em; }",
    "dialog.psnext-style-picker .psnext-style-picker__threshold.is-inactive { color: #e5bb75; }",
    "dialog.psnext-style-picker .psnext-style-picker__threshold.is-protected { color: #8fc7ff; font-weight: 600; }",
    "dialog.psnext-style-picker .psnext-style-picker__badge { display: inline-block; color: var(--fg-color, #eee); border: 1px solid var(--primary-color, #65adff); border-radius: 999px; padding: 2px 8px; font-size: 0.78rem; }",
    "dialog.psnext-style-picker .psnext-style-picker__badge.is-chosen { border-color: #82c98a; }",
    "dialog.psnext-style-picker .psnext-style-picker__choose, dialog.psnext-style-picker .psnext-style-picker__more { align-self: flex-end; }",
    "dialog.psnext-style-picker .psnext-style-picker__footer { align-items: flex-end; border-top: 1px solid var(--border-color, #484848); padding-top: 12px; }",
    "dialog.psnext-style-picker .psnext-style-picker__apply { background: var(--comfy-menu-bg, #303030); border-color: var(--primary-color, #65adff); }",
    "dialog.psnext-style-picker .psnext-style-picker__empty { padding: 24px 10px; text-align: center; }",
    "@media (max-width: 640px) { dialog.psnext-style-picker .psnext-style-picker__shell { padding: 12px; gap: 11px; } dialog.psnext-style-picker .psnext-style-picker__filters { grid-template-columns: 1fr; } dialog.psnext-style-picker .psnext-style-picker__footer { align-items: stretch; flex-direction: column; } dialog.psnext-style-picker .psnext-style-picker__actions { justify-content: flex-end; } }",
  ].join("\n");
  document.head.append(style);
}

function categoryParts(category) {
  return typeof category === "string" ? category.split("/").filter(Boolean) : [];
}

function humanizePath(path) {
  return categoryParts(path).map(humanizeSegment).join(" / ") || "Uncategorized";
}

function humanizeSegment(segment) {
  return String(segment ?? "")
    .replace(/[-_]+/gu, " ")
    .replace(/\b\p{L}/gu, (letter) => letter.toLocaleUpperCase());
}

function foldText(value) {
  return String(value ?? "").normalize("NFD").replace(/[\u0300-\u036f]/gu, "").toLocaleLowerCase();
}

function displayName(style) {
  return typeof style.name === "string" && style.name ? style.name : String(style.id ?? "Unnamed style");
}

function compareText(left, right) {
  return left.localeCompare(right, undefined, { sensitivity: "base" });
}

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function formatNumber(value) {
  return String(Number(value.toFixed(2)));
}

let nextDialogId = 0;
