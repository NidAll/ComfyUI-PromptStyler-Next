import { app } from "../../scripts/app.js";
import { attachStylePicker } from "./style-picker.mjs";

app.registerExtension({
  name: "PromptStylerNext.StylePicker",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "PSNextStyle") return;
    const styleInput = nodeData.input.required.style[1];
    const categories = styleInput.psnext_categories;
    const styles = styleInput.psnext_styles;
    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onCreated?.apply(this, arguments);
      attachStylePicker(this, categories, styles);
      return result;
    };
  },
});
