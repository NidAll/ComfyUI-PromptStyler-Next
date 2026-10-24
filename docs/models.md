# Model profiles and evidence

Profiles describe the workflow contract. They do not load models, select samplers, change guidance, claim that different architectures understand identical syntax, or guarantee image quality. `profiles.json` is the machine-readable inventory. Source review date: 2026-10-24.

| ID | Added language | Text negatives | Generic CLIP node |
| --- | --- | --- | --- |
| `generic` | Natural prose | Suppressed | Rejected |
| `sdxl` | Concise tags | Available with CFG | Supported |
| `flux` | Natural prose | Suppressed | Use native FLUX workflow |
| `qwen-image` | Natural prose | Requires enabled CFG | Use native image-aware workflow |
| `qwen-image-2.1` | Natural prose | Suppressed for CFG-free default | Use native image-aware workflow |
| `moss-image` | Natural prose | Available with CFG | Use native MOSS workflow |
| `moss-image-dmd` | Natural prose | Suppressed at CFG 1 | Use native MOSS workflow |
| `anima` | Lowercase spaced tags | Available with CFG | Supported |
| `anima-turbo` | Lowercase spaced tags | Suppressed at CFG 1 | Supported |
| `fibo` | JSON caption fields | Text interface unsupported | Use native Fibo workflow |
| `fibo-edit` | Preserved edit instruction or caption JSON | Suppressed | Use native Fibo edit workflow |

“Supported” means the node uses the host's native scheduled text encoding with the supplied encoder. It does not verify that the user connected the right weights. Profiles marked `specialized` deliberately reject the generic encoding node; styled strings remain available for the correct native nodes.

## SDXL

The official model uses two CLIP encoders. PromptStyler supplies concise descriptive tags; this is a practical formatting choice, not a claim that SDXL requires tags. For separate encoder prompts, sizing metadata or refiner conditioning, use native SDXL nodes. `weighting=true` records the ComfyUI encoder's syntax capability; intensity does not emit weighted expressions. [Model card](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0), [Diffusers SDXL API](https://huggingface.co/docs/diffusers/api/pipelines/stable_diffusion/stable_diffusion_xl).

## FLUX

BFL recommends descriptive language covering the subject, action, style, context and light, and states that negative prompts are unsupported. The profile appends natural sentences and reports suppressed negatives. It does not infer which FLUX variant is loaded or manufacture guidance conditioning. [Official image quick reference](https://github.com/black-forest-labs/skills/blob/master/README.md), [BFL negative-prompt guidance](https://help.bfl.ai/articles/7734566352-does-flux-2-support-negative-prompting).

## Qwen-Image

The original model's examples use descriptive captions and explicit lettering. Negative text works only when the actual workflow enables classifier-free guidance. The `qwen-image` profile exposes that capability, without claiming that the supplied graph enables it. [Qwen model card](https://huggingface.co/Qwen/Qwen-Image), [pipeline API](https://huggingface.co/docs/diffusers/api/pipelines/qwenimage).

The separate `qwen-image-2.1` profile follows the documented CFG-free default. It conservatively suppresses negatives even though explicitly configured CFG workflows can consume them. Choose an explicit trusted custom profile for that alternate workflow. [Qwen-Image 2.1 API](https://huggingface.co/docs/diffusers/main/api/pipelines/qwenimage21).

## MOSS-Image

The SFT model accepts natural language, tags and structured layout prompts; the bundled profile deliberately chooses captions. It supports text negatives with guidance. Existing layouts and image-reference operations belong in native MOSS workflows; no bounding boxes or scene entities are invented. [Official model card](https://huggingface.co/OpenMOSS-Team/MOSS-Image-SFT), [author's guide](https://github.com/OpenMOSS/MOSS-Image/blob/main/USERGUIDE.md).

`moss-image-dmd` describes a CFG-1 DMD/DMD2 workflow with no negative branch. This is separate from the full model profile and does not install or select a LoRA. [LoRA author's Kromoss card](https://huggingface.co/lodestones/Kromoss), [DMD2 release description](https://huggingface.co/lodestones/MOSS-Image-Base-8-steps-dmd/commit/da05cb3b52899179e2bb5f7efe1058fefcbae21b).

## Anima

Anima supports tags, natural language and mixtures. System-added tags are lowercase with spaces. No score, quality, artist or safety tokens are inserted. The Aesthetic version does not need score tags. The normal profile supports negatives; the Turbo profile conservatively follows CFG 1. Weighting is marked false because token-weight behavior differs across native encoder paths; intensity uses clause selection. Photographic-only packs explicitly exclude Anima. Two authored variants reinterpret noir and clay as illustration. [Official Anima card](https://huggingface.co/circlestone-labs/Anima).

## Fibo 2

Fibo generation expects structured captions. The adapter maps the user's unmodified text into `short_description`, then maps explicit style axes into `style_medium`, `lighting.conditions`, `aesthetics.color_scheme`, `aesthetics.composition`, `aesthetics.mood_atmosphere` and `artistic_style`. Existing caption fields win, including empty strings. It never fabricates objects, locations, references or `text_render` entries. This is a deterministic partial-caption mapper, not a VLM captioner or full semantic parser. Native Fibo negative captions and edit instructions remain outside the text-negative interface. [Official Diffusers Fibo 2 API](https://huggingface.co/docs/diffusers/main/api/pipelines/bria_fibo2), [Bria caption example](https://raw.githubusercontent.com/Bria-AI/FIBO/main/default_json_caption.json).

`fibo-edit` preserves plain edit instructions and appends natural visual directions.
For JSON input it styles caption fields, including a nested `structured_caption`,
while preserving `edit_instruction` and user fields. It does not infer the intended
edit from a reference image. Choose `fibo` for text-to-image captions.

## Unknown models and extensions

An unknown model resolves to the conservative generic profile with a warning. It receives prose without assumed weighting, negatives or conditioning support. Trusted Python callers can register profiles and adapters through `AdapterRegistry`; untrusted JSON packs cannot import code. Profile aliases are exact identifiers, not model-filename guessing. The same style carries prose clauses and compact tags, so adapters format only system-owned additions while preserving the user's wording.

## Validation limits

Tests exercise schema validity, supported-style filtering, deterministic formatting, negative handling and native encoder calls. They do not establish visual quality, optimal prompting or equivalence across checkpoints. Distilled variants and fine-tunes may have stronger intrinsic styles. Evaluate representative scenes and seeds with the actual workflow before making visual claims.
