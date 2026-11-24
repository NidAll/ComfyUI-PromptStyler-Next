# MOSS layout pipeline

How a MOSS-Image layout prompt is built, by hand or with AI help, and what was done to make each step fast.
Three projects take part:

| Part | Where | Job |
| --- | --- | --- |
| MOSS Image Layout Prompt Builder | [ComfyUI-Ming-Image-Prompt-Builder](https://github.com/NidAll/comfyui-ming-image-prompt-builder) (`moss.py`) | The only serializer: validates boxes, writes the official MOSS layout JSON, imports compiled prompts, drafts, Ideogram 4 JSON and 0–1000 assistant layouts |
| Layout Assist + LFM3 decode engine | this repository (`comfyui/upscaler/layout_assist.py`, `comfyui/upscaler/lfm3/engine.py`) | Writes layout JSON with LFM3-VL: lists objects, captions boxes, plans a layout from an idea, edits one by instruction |
| Studio builder overlay | this repository ([studio/moss-layout/](../studio/moss-layout/README.md)) | Browser editor and the HEISS routes that queue the AI graphs |

Box detection and OCR use ComfyUI core's **WeVisOne-VL Detect** node. Plain-text prompt expansion stays with
the [MOSS Prompt Upsampler](moss-upsampler.md); LFM3-VL handles everything that is JSON.

## Data flow

```mermaid
flowchart LR
  Board[Studio board] -->|serialize / import| Node[MOSS builder node routes]
  Board -->|AI task| Route[POST /api/moss-layout-ai]
  Route --> Graph[One ComfyUI graph]
  Graph --> W[WeVisOne-VL: list, detect, OCR]
  Graph --> L[Layout Assist: LFM3-VL]
  L -->|xyxy 0-1000 JSON| Board
  Node -->|MOSS prompt| Encode[CLIP Text Encode]
```

Coordinates have one form between the models and the board: `[x1, y1, x2, y2]` on a 0–1000 grid, items listed
back to front, with `"grid": "xyxy-1000"`. The builder node converts that onto the canvas
(MOSS: `[y_min, x_min, y_max, x_max]` in pixels from the canvas centre). Ideogram 4 JSON
(`[ymin, xmin, ymax, xmax]` on 0–1000, first element in front) goes through the same import, and the board
can copy a layout out as Ideogram 4 JSON.

## Tasks

Each AI action is one queued graph. Its steps are reported live and shown in the card.

| Task | Graph | Result |
| --- | --- | --- |
| `image`: extract layout + prompt | LFM3 `list_objects` → WeVisOne `detection` (+ `ocr`) → LFM3 `describe_regions` | Boxes, captions, summary, style tags, lettering |
| `describe` | LFM3 `describe_regions` (with the reference if there is one) | Captions for the given boxes; a rewrite keeps the box's subject |
| `text` | LFM3 `text_layout` | A layout from an idea |
| `edit` | LFM3 `edit_layout` | The layout with an instruction applied; locked boxes stay |
| `snap` | WeVisOne `referring` | The selected box fitted to the object its caption names |
| `ocr` | WeVisOne `ocr` | One text box per line of lettering |

Detector clean-up (`layout_assist.normalize_detections`, `merge_regions`) drops full-frame backdrops, parts or
clothing inside a boxed person, more than three boxes of one label, and object boxes that only repeat an OCR
line. OCR words are merged into lines before they become text boxes.

## Answer format

- Captions come back under numbered, quote-free keys (`"1 dog": "..."`), so each caption lands on its own box
  even if the model reorders them.
- Answers are repaired leniently and never retried. A describe answer with a stray quote is salvaged field
  by field, and gaps are filled the same way.
- Captions that echo the label or the box are cleaned up (`_unecho`).
- Meta tags that repeat an item's label or text are dropped, so meta stays style and medium.
- A rewrite passes the box's current caption as a hint, so a lone box keeps its subject.

## Speed work

- **LFM3 decode engine.** The Transformers generate loop is launch-bound at batch size 1. The engine
  prefills eagerly, then replays one captured CUDA graph per token, with fixed KV for full-attention layers,
  a 256-slot ring for sliding-window layers and a 6-tap state for short-convolution layers. It checks the
  stop condition on the host every 8 tokens. In our tests this decoded about three times faster than the
  Transformers loop; the gain depends on the GPU. Output is not bit-identical: teacher-forced argmax agreed
  99.2% of the time on text and 95.4% with an image. Details are in [lfm3-vl.md](lfm3-vl.md#fast-decode-engine).
  The engine lives on the loader's handle, is recaptured when the weights move, and leaves no model-owned
  caches.
- **One LFM3 call per image.** The describe step sees the full image plus box coordinates. Per-box crops
  were slower and miscounted.
- **Fewer model swaps.** OCR ignores its query, so its query is wired to the object list. ComfyUI then runs
  both WeVisOne nodes back to back (LFM3 → WeVisOne → LFM3), one swap fewer than running OCR first. Swaps
  dominate the image task when both models do not fit in VRAM together.
- **Bounded detector answers.** WeVisOne `max_length` is capped per task (detection 384, referring 160,
  OCR 640 tokens). This stops a rare repetition loop that otherwise runs to 4096 tokens.
- **Result cache.** Results are keyed by the task, its settings and the image bytes (SHA-256), with 40
  entries. Asking again answers at once. *Another take* skips the cache and samples at temperature 0.5 with
  a new seed; other requests decode greedily.
- **Small uploads.** The reference is sent as the board shows it, at most 1152 px, as JPEG.
- **Cheap progress.** The browser polls the job every 150 ms. The server follows ComfyUI's websocket for
  the active node and the token count, so no extra model work happens for progress.

## Limits

- Caption and layout quality was checked on a handful of renders, not a benchmark.
- OCR can misread stylized or small lettering.
- The effect of AI-made layouts on generated MOSS images has not been evaluated.
