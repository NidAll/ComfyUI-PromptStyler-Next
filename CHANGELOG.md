# Changelog

## Unreleased

- LFM3-VL decodes through a native CUDA-graph engine (about 3× faster than the Transformers loop in our tests);
  Transformers remains the fallback for token-biased requests and non-CUDA devices.
- New **Layout Assist** node (`PSNextLayoutAssist`): MOSS layout JSON from LFM3-VL (list objects,
  describe boxes, idea → layout, edit by instruction, image → layout), boxes as xyxy on 0–1000.
- HEISS Studio MOSS layout builder overlay ([studio/moss-layout/](studio/moss-layout/README.md)): visual
  editor with an AI menu (image → layout + prompt, idea → layout, edit, captions, snap, lettering), live step
  animation, result cache, Ideogram 4 import/export. Pipeline: [docs/moss-layout-pipeline.md](docs/moss-layout-pipeline.md).
- New **MOSS Prompt Upsampler** node (`PSNextMossUpsampler`) for the Qwen3.5-2B
  MOSS-Image upsampling fine-tune: exact SFT system prompt, thinking off, seeded
  Qwen3.5 sampling, 640-token budget with sentence trimming. It runs through ComfyUI's
  native Qwen3.5 text model, so INT8 ConvRot layers use comfy-kitchen kernels.
  **Load Prompt Upscaler** lists Qwen3.5 checkpoints in the prompt-model folder; the
  LFM3 nodes refuse them with a pointer to the new node. See
  [docs/moss-upsampler.md](docs/moss-upsampler.md).
- The MOSS upsampler takes an optional `style` look, appended to the draft as a trailing
  clause (at most 30 words), so the prompt is written in the selected medium instead of
  the model's default photograph. Inspection reports `style` and `user_text`; the
  contract version is now `moss-upsampler-2`.
- MOSS upsampler v2 (`NidAll/moss-qwen3.5-2b-upsampler-v2-bf16`): defaults follow its
  model card (temperature 0.6, top_p 0.9, new `repetition_penalty` 1.05, 700-token budget).
  A temporary output **guard** (on by default) swaps provenance tokens in the draft and
  removes unrequested visible text, negation tails and black-and-white color words; the new
  `max_takes` input rewrites a sampled take only when the guard refuses it (cleaning would
  remove more than 30%). Inspection adds a `guard` block; the contract version is now
  `moss-upsampler-3`.
- A MOSS upsampler checkpoint carrying a Qwen3.5 MTP draft head (`mtp.*`, for example grafted
  from the base model) decodes through ComfyUI core's adaptive MTP speculative path;
  inspection reports `upsample.speculative`.

## 0.6.0a1 (experimental, 2026-11-19)

Experimental pre-release on the `experimental/0.6.0a1` branch, not yet merged into
`main`. Style text and fingerprints change for every bundled pack. Image adherence was
checked only on the small matched-seed comparison in [validation](docs/validation.md).

**Style adherence.** Selected styles are now written so text encoders follow them:

- Every bundled clause was rewritten from an instruction ("Render the subject as...")
  into a short visual description, without negations, conditions, scene references or
  a mood axis. Anima tags favour model-known tags such as `watercolor (medium)`.
- Natural profiles render one compact style phrase after the prompt; tag profiles
  escape brackets for ComfyUI and skip tags already present (adapter revisions
  `natural/2`, `tags/2`, `fibo-caption/2`; engine `promptstyler-next/2`).
- Three standard tiers (0 / 0.4 / 0.75) and a per-profile `style_budget` keep stacked
  styles within what small encoders read: core identities always render.
- New recipe field `prompt_conflicts` (`replace` by default, or `keep`): style words in
  the prompt on axes the selection sets, such as "A photo of" or `realistic`, are
  removed from the styled prompt and reported. The ComfyUI Style node gains it as an
  optional advanced input appended after `enabled`, so saved widget order is unchanged.
- Library cleanup: 1,003 entries in 49 packs. Studio packs cut to 10 entries each and
  renamed (`weather`, `textile`, `garden-art`, `jewelry`, `lettering`), lettering
  limited to text-capable models, grades and effects consolidated, Information
  Hierarchy retired, authors unified. 161 retired IDs are listed in the pack's
  `retired` map; recipes and saved ComfyUI workflows using them still load.
- `scripts/audit_library.py` is now an authoring lint (`--check`, `--vocab`).
- Studio: Subtle/Balanced/Strong strength, look Strong / color Balanced / effects
  Subtle defaults, at most two effects outside free mixing, one look per model family,
  and a "Style wins over prompt words" switch. Image Clone always replaces caption
  style words.

Added **Prompt Idea** (LFM3-VL): each seed turns a draft into a new prompt idea. A seeded lens and
prompt structure rotate away from recently used ones, the model brainstorms concepts and the one
least like earlier ideas is developed, then quoted text and exclusions are restored and a lost subject,
echo or repeat triggers one retry. Stock adjectives and wording recurring across earlier prompts are
softly penalised during decoding. Upscale Base Prompt and its measured recipe are unchanged; the shared
LFM3 decode gained optional seeded sampling (greedy stays the default).

Added an enabled toggle to the ComfyUI Style node. Disabling it passes raw positive
and negative text through unchanged, without style additions or model formatting.
Existing saved workflows and API graphs remain enabled by default.

Added the responsive Studio style browser with Looks/Color/Effects, accent-insensitive
metadata search, favorites, named presets and per-workflow persistence. Replay
helpers restore selections and full browser state atomically; storage events keep
tabs synchronized. Existing gallery/composer integration stays in place.

Fixed LFM3 example graph tests on clean CI hosts by providing a tiny temporary
metadata artifact through real model discovery instead of requiring installed weights.

Added offline LFM3-VL 2B scene rewriting for MOSS Image Base and Anima, with
style-neutral action/contact examples, exact-text diagnostics and one bounded
repair that cannot discard previously satisfied lexical checks. Detailed inputs
use the same contract without an arbitrary length threshold. Explicit standalone
absence clauses are restored, and repeated requested labels avoid needless repair.
Existing MiniCPM
continuation and saved node widget order remain available.

The benchmark now selects the image-model target and output budget and establishes
its standalone inference context. Optional runtime tests skip cleanly when host
dependencies are absent.

Fused compatible native INT8 Q/K/V projections and routed text/vision attention
through ComfyUI, with causal/sliding masks and shared grouped-head expansion.

## 0.5.0 — 2026-10-29

Added a category-filtered picker to the ComfyUI Style node, including parent
categories and custom packs. Browsing keeps the current style until another is
selected. Saved full style IDs infer their category on load; execution inputs,
composition and fingerprints remain unchanged.

Added a searchable ComfyUI Style explorer with readable names, category groups,
Look/Color/Effect filters and explicit Apply. Visual directions show model
variants, intensity tiers and protected axes before selection. Browsing controls
stay out of saved widget values and executable API inputs.
The explorer is the only visible style selection control; its button shows the
selected name. The original style ID remains hidden in the saved/API widget contract.

Refined illustration and anime technique categories and authored visual identities,
plus six scene-themed treatments. Updated prose and tags together to reduce
setting, weather, symbol and scale substitution. Changed packs advance their
content versions; existing IDs remain, but styled text and fingerprints change.

## 0.4.1 — 2026-10-24

Fixes prompt upscaling that only paraphrased short ideas. Expanded is now the
default: it retains the complete text premise in an assistant prefix and generates
supporting physical detail in one pass. Faithful offers concise clarification;
reference/image paths retain their evaluated grounding behavior. Adds an optional
appended detail-mode widget, a 192-token default for new nodes, source/addition
inspection and a cache contract revision. Strengthens quoted-text validation so
changed labels cannot pass as matching substrings. Existing widgets and API
graphs without the new mode remain usable.

## 0.4.0 — 2026-10-24

Added optional V3 Load Prompt Upscaler and Upscale Base Prompt nodes for the existing
MiniCPM-V 4.7 1B native INT8 deployment. Text, image and combined inputs feed the
semantic-base toolkit contract before shared style composition. Includes native
model placement, cached handles, fused decoding, paragraph-token stopping, bounded
inputs, quoted-text checks, diagnostics and executable workflow examples. The core
and Studio service remain independent of the VLM runtime.

## 0.3.0 — 2026-10-24

Adds a seven-prompt LLM toolkit for semantic base creation, neutralization,
reference captioning, controlled expansion, editing, auditing and recipe authoring.
Includes six frozen base scenes and five native-handoff recipe examples.

Reviews the existing 48 packs: revises 201 prose/tag clauses across 19 packs to
reduce setting substitution, entity duplication and invented lettering. Adds 529
missing axis claims so layered presets and grades resolve their visual directions
consistently. Existing IDs remain; revised packs advance their content versions.
Multi-style outputs and fingerprints may change because previously additive
clauses now participate in conflict resolution.

Adds four focused packs with 32 authored entries: Computational Surfaces,
Optical Material Accents, Animation Finishing and Information Hierarchy. Current
inventory: 1,164 entries across 52 packs (1,017 styles, 69 grades, 78 modifiers).
Adds a repeatable bundled-authoring audit, full-corpus composition regressions and
toolkit source-distribution checks. No new runtime dependencies or native model
capability claims. Image quality and LLM-output acceptance remain unmeasured.

## 0.2.0 — 2026-10-24

Native HEISS composer panel, managed Python sidecar, explicit host profile mapping,
and one-node native graph composition. Generated image captions can feed the
optional `PSNextCompose.prompt` input. Adds the Fibo edit instruction profile,
preserving plain edit instructions and nested structured captions. Includes browser
request, native graph, sidecar lifecycle, and linked-caption execution validation.

## 0.1.0 — 2026-10-24

Initial independent implementation: deterministic visual-axis composition, typed
immutable recipes, validated original style packs, explicit model profiles,
inspectable conflicts/intensity/protected axes, Fibo caption mapping, Python/CLI,
three ComfyUI V3 nodes, a local style workbench and a reusable HEISS transport.

Includes property and regression tests, actual-host registration checks, real HTTP
and Node bridge tests, schema contracts, strict static checks and packaging gates.
See the validation guide for the tested scope and outstanding image-quality/live
HEISS acceptance boundaries.
