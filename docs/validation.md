# Validation and release status

Version 0.3.0 source is maintained in the GitHub repository
`NidAll/ComfyUI-PromptStyler-Next`. The semantic-base toolkit and pack review are documented in
[the 0.3.0 review](style-review.md). This source update creates no package-index
release or version tag.

## 0.3.0 toolkit and reviewed catalog

The final source passes 178 standalone tests, including Hypothesis and JSON
Schema tests, plus 27 actual ComfyUI host tests and all 18 Node/Studio tests.
Combined runtime statement/branch coverage is 93%. Ruff lint/format and strict
core Mypy pass. The bundled authoring audit covers all 1,164 entries, 52 packs,
11 profiles and 3,801 clauses including variants, with zero axis-ownership or
hard-palette classification errors. Its zero content hints are only a limited
heuristic result; the editorial review and its limits are documented separately.

The source archive includes all seven LLM prompt files, the six-scene semantic
corpus and five recipe examples. Wheel/source byte comparisons and an isolated
installed-wheel composition pass confirm the complete catalog. Tests verify
serialized base preservation across the catalog, not generated-image fidelity.
No LLM-output benchmark or model image-quality grid was run for this version.

## Earlier engine and integration acceptance

| Check | Result and scope |
| --- | --- |
| Standalone Python 3.14 | 157 tests passed, including property-based Unicode/recipe tests and real HTTP tests |
| Installed ComfyUI Python 3.12 | 183 tests passed, 1 skipped; the optional Hypothesis module is absent in the host environment but passed in the isolated development environment |
| Runtime coverage | 93% including branches; engine composition 99% |
| ComfyUI V3 host contract | 26 tests passed: actual schemas, registration, real prompt validation, native text previews and explicitly doubled encoder delegation |
| Live ComfyUI API | Isolated CPU server registered all three nodes and successfully executed the bundled text-only graph through `/prompt` and `/history`; no image models loaded |
| Node transport | 12 tests passed, including a real Python sidecar, HTTP bridge, typed-client behavior, raw duplicate-key rejection, errors and limits |
| Actual Express / HEISS guard | Bridge mounted in Express 5 with HEISS's actual request guard; strict input, metadata preservation and foreign-origin rejection passed |
| Static checks | Ruff lint/format and strict Mypy passed |
| Earlier library snapshot | 1,132 entries, 48 packs, 11 profiles; schema/ID/provenance checks, all eligible style/profile compositions, staged intensity and intent-preservation checks passed |
| Packaging | Wheel/source archive inspections and clean installed-wheel smoke outside the checkout passed; checksums accompany artifacts |

The property tests cover arbitrary valid Unicode, finite intensities, recipe
round-trips and protected axes. Regression tests cover huge integer JSON values,
style-wide negatives after conflict/protected-axis/intensity suppression, and
ComfyUI's required literal wrapper for array-valued API widgets.

Builtin authoring checks catch duplicate IDs/titles/descriptions/primary clauses,
stock quality boosters, unsupported model references and hard palette constraints
outside the palette axis. Concrete library regressions verify that a color grade
replaces noir's monochrome requirement and that incompatible material looks cannot
silently keep both rendering processes.

## Expanded style inventory

The original validated catalog had 832 entries in 33 packs. Fifteen authored
CC0-1.0 packs were promoted into the built-in library, adding 300 entries
(225 styles, 45 grades and 30 modifiers). The inventory at that stage contained 1,132 entries
across 48 packs; 0.3.0 expands it to 1,164 entries in 52 packs. All 15 packs pass strict JSON pack loading with the built-in
catalog, without duplicate pack, style ID or title collisions. The full existing
test suite and distribution checks were rerun for the expanded inventory on
2026-10-24.

## Browser acceptance

The workbench was exercised in a real browser: discovery, model/query filters,
favorites save/remove/filter, recipe layers, ordering, intensity, stale-output copy
protection, advanced axis locks, unsupported-negative warnings and composed output
inspection. Bookmarked filters survive refresh. Selected styles cannot be added
twice. Raw imported recipe JSON reaches Python validation before normalization.

Hallmark static inspection reported zero failures and zero reflex findings. Its
optional Puppeteer render tier was unavailable; actual browser visual inspection
was performed separately. Abstract swatches are clearly identified, with no
fabricated image previews or visual-quality metrics.

## Performance scope

A local CPU text-only probe over 1000 two-layer compositions measured approximately
0.09 ms median and 0.17 ms p95 after a roughly 191 ms cold catalog load. These are
observations for this engine/library snapshot, not an inference benchmark or a
universal latency guarantee. Composition does not allocate model tensors or load
weights. Profile/pack content is snapshot-based and reproducible.

## Acceptance boundaries

No image-generation quality grid was run. The tests establish text/schema/transport
correctness, not optimal prompts, aesthetic fidelity, pixel equivalence or uniform
capabilities across fine-tuned checkpoints. Fibo's mapper validates touched caption
fields and preserves opaque user fields; it is not full native caption-schema
validation or an image-conditioned captioner.

The conditioning node delegates to a connected native encoder; real weights were
not loaded during this validation. The actual ComfyUI API smoke uses text-only
nodes. Live authenticated HEISS generation and a full installed React composer
panel were not exercised. HEISS requires the explicit guarded source mount and a
host UI hook documented in the integration guide.

CI workflows are configured for Python 3.11–3.14, Node and a pinned ComfyUI CPU
contract job. Hosted workflow status is separate from the local validation above.
This source update creates no tag or package-index release and makes no
image-quality claim. Existing PromptStyler, user services, models and host
dependencies are preserved.

## Studio integration 0.2.0

The standalone suite passed 159 tests (the host module is skipped outside ComfyUI),
with 93% combined statement/branch coverage. All 27 actual-host node tests and 18
JavaScript transport/generation/lifecycle tests passed. Ruff checks/format and strict
core mypy passed. The node module is verified in its real host rather than imported
through standalone mypy. Wheel and source checks include an outside-checkout
dependency-free wheel installation. The catalog at that integration acceptance
snapshot contained 832 entries in 33 packs and 11 profiles; the expanded 48-pack
inventory is validated above and uses the same shared `Engine.builtin()` path.

An isolated copy of the installed HEISS release passed browser search, selection,
preview and Generate recipe capture; selection survives lazy gallery loading and a
controlled generation error. All three installed saved workflows passed graph
injection, original-input preservation and retry identity checks. A real model-free
ComfyUI queue execution passed with a generated text link feeding PSNextCompose.
Bridge health, foreign-origin rejection, remote-client denial and duplicate JSON
rejection passed. Release preservation/rollback and guarded frontend patch checks
passed, including lazy-entry imports and compressed asset parity.

These checks do not run Anima, MOSS or Fibo image inference, establish perceptual
quality, or test an authenticated remote Studio session. No image models were loaded.
