# MOSS layout builder for HEISS Studio

A visual MOSS-Image layout editor with an AI assistant, written as an overlay for a
[HEISS Studio](https://github.com/tristmeister/HEISS-UI) install. It is the browser and server half of the
pipeline described in [docs/moss-layout-pipeline.md](../../docs/moss-layout-pipeline.md):

- the builder never serializes prompts itself; it calls the **MOSS Image Layout Prompt Builder** node's
  routes in ComfyUI ([ComfyUI-Ming-Image-Prompt-Builder](https://github.com/NidAll/comfyui-ming-image-prompt-builder)),
  so Studio and ComfyUI write the same prompt;
- the AI menu queues small ComfyUI graphs built from this repository's **Layout Assist** node (LFM3-VL)
  and core **WeVisOne-VL Detect**.

| File | Role |
| --- | --- |
| `api/studio-layout-ui.mjs`, `api/studio-layout-ui.css` | Browser module: board, boxes, inspector, reference image, import/export, AI menu and its animation. `openLayoutBuilder({ prompt, onApply, onClose })` opens it. |
| `api/studio-layout-builder.mjs` | Express routes `POST /api/moss-layout/serialize` and `/import`, forwarded to the node's `/moss_prompt_builder/*` routes. |
| `api/studio-layout-assist.mjs` | Express routes `POST /api/moss-layout-ai` (start a task) and `GET /api/moss-layout-ai/status` (are the models installed). |
| `api/test-studio-layout-*.mjs` | Node tests. |

## Install into HEISS

The server modules import HEISS's own `server/comfy.js`, `server/comfy-queue.js` and `server/jobs.js`, so
they belong in the install's `api/` folder:

1. Copy the four `api/studio-layout-*` files into `<HEISS>/api/`.
2. In `<HEISS>/server/index.js`, import `mountLayoutRoutes` from `../api/studio-layout-builder.mjs`, call
   `mountLayoutRoutes(app)` after `express.json()`, and serve `studio-layout-ui.mjs` and
   `studio-layout-ui.css` under `/studio-assets/`.
3. Open the builder from the composer with `openLayoutBuilder`.

Progress and results use HEISS's job store: poll `GET /api/jobs/:id` and cancel with
`POST /api/jobs/:id/cancel`. ComfyUI needs PromptStyler Next (this repository), the MOSS builder node pack,
an LFM3-VL artifact for the loader, and `wevisone_vl_2b*.safetensors` in `models/text_encoders/` for
detection. Without WeVisOne, image extraction falls back to LFM3 alone; Snap and Lettering need it. The AI
menu shows which of the two models ComfyUI has.

## AI menu

Open it with the **AI** button or `I`. Escape or **Stop** cancels a running task.

- **From reference**: *Extract layout + prompt* (boxes, captions, summary, style tags and lettering from the
  reference image), *Lettering* (adds text boxes from OCR), *Snap* (fits the selected box to the object its
  caption names).
- **From words**: *New layout* from an idea, or *Change this layout* by instruction (Ctrl+Enter).
- **Captions**: describe empty boxes, or rewrite the selected ones.
- **Another take**: the same request with a new seed.

Pressing Ctrl+V anywhere while the builder is open makes a copied image or screenshot the reference, even
after a click on the board has moved focus outside the builder. The reference card (AI menu and Reference menu)
has **Replace…** (pick a file) and **Paste**; with no reference yet, the AI menu has **Paste image**. Both paste
buttons read the clipboard directly where the browser allows it. A pasted PNG that carries a layout offers to
import it.

Locked boxes survive every AI result. A new box that overlaps a locked one by IoU ≥ 0.5 is replaced by it.
The reference is sent as the board shows it (cover, contain, fill or actual size, at most 1152 px, JPEG).
While a task runs, the board shows a scan beam, the card lists each graph step as ComfyUI reaches it, and new
boxes fade in.

## Tests

Outside a HEISS install, a resolve hook maps the three HEISS imports to the small stand-ins in `tests/host/`.
The stand-ins are for tests only; never copy them into HEISS.

```bash
node --import ./tests/register.mjs --test api/test-studio-layout-*.mjs
```

Inside an install, run `node --test api/test-studio-layout-*.mjs` from its root.
