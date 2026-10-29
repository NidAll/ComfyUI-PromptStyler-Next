# PromptStyler Next

Independent repository. Do not modify the original PromptStyler, ComfyUI core, models, dependencies, or unrelated running services. HEISS installation changes are authorized for the explicit Studio integration request of 2026-10-24; preserve user data and disabled automatic updates. Use current ComfyUI V3 APIs only. No compatibility shims. Core package must import without ComfyUI or third-party runtime dependencies. Python >=3.11. Public source and docs must be portable and omit workstation paths.

Owners: promptstyler_next/ owns engine, validation, adapters and pack data. comfyui/ owns V3 nodes. studio/ owns browser/Node integration. Python HTTP service belongs in promptstyler_next/service.py. Tests use pytest; optional Hypothesis is a development dependency only. Never load code, URLs, expressions, or arbitrary filesystem paths from pack input.

web/ owns the ComfyUI frontend extension. Style category filtering uses catalog
metadata on the existing combo; category is nonserialized browsing state and must
never change the selected full style ID implicitly. Preserve the saved widget
order and derive the category from restored IDs. Run `node --test tests/*.test.mjs`
and the actual V3 host tests after picker changes.

Use the existing ComfyUI venv for actual host tests; install dev tools only into a separate project environment. No heavy model downloads. Record validation limits, especially lack of image-quality acceptance. All implementation commits belong to this repository.

Public contracts are documented in docs/api.md, docs/packs.md and docs/studio.md. Full looks use distinct medium/texture claims; hard palette constraints belong only to the palette axis. Preserve this authoring boundary when adding styles.

llm-prompts/ owns the copyable semantic-base authoring toolkit and replay corpus.
Claim every authored axis in bundled packs, including variants, and review both
prose and tags for scene substitution or invented text. Run scripts/audit_library.py
and the base-corpus regressions after pack edits. Image and LLM quality claims
require actual evaluation beyond deterministic composition checks.

Optional VLM authoring belongs only to comfyui/upscaler/; importing the core,
HTTP service or node schemas must not load model tensors or initialize CUDA.
Use the existing packaged MiniCPM artifact, pinned local vendor code and native
Comfy ModelPatcher/Kitchen operations. Never download weights or upgrade host
dependencies automatically. Cache handles through the loader node, not global
tensor caches. Keep semantic-base contract/examples and diagnostics testable
without Torch. Reinstall the updated project into the existing ComfyUI venv.

Expanded text authoring must preserve the entire supplied premise in its assistant
prefix and generate continuation only. Reference inputs stay grounded; mode/schema
changes must retain the existing widget prefix and allow omitted new API fields.
Do not replace output-quality evaluation with length-only assertions.

The experimental LFM3-VL path owns `comfyui/upscaler/lfm3/` and
`lfm_prompts.py`. It performs complete MOSS Image Base/Anima scene rewrites;
the assistant-prefix continuation requirement above applies to MiniCPM only.
Keep the two runtime copies synchronized with Anima Prompt Architect, with
their pinned source notices and licenses. Use the offline preparation script
and native quantizer policy; do not fetch models or remote code at execution.
Check short/long text and image inference, cache correctness, actual Kitchen
dispatch, memory and generated captions before changing the measured recipe.
Expanded authoring uses bounded physical detail and preserves standalone absence
clauses. Repair may not discard satisfied lexical checks. Curated prompt examples
are inference guidance, not trained distillation; keep remaining invention/style
leakage and untested diffusion quality explicit in validation reports.
