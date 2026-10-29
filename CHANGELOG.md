# Changelog

## Unreleased

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

Added a category-filtered picker to the ComfyUI Style node, including parent
categories and custom packs. Browsing keeps the current style until another is
selected. Saved full style IDs infer their category on load; execution inputs,
composition and fingerprints remain unchanged.

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
