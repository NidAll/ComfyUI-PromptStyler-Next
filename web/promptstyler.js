import { app } from "../../scripts/app.js";
import { attachStylePicker } from "./style-picker.mjs";

app.registerExtension({
  name: "PromptStylerNext.StylePicker",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "PSNextStyle") return;
    const categories = nodeData.input.required.style[1].psnext_categories;
    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onCreated?.apply(this, arguments);
      attachStylePicker(this, categories);
      return result;
    };
  },
});
