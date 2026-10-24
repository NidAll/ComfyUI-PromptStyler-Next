# Style and semantic handoff review — 0.3.0

The 2026-10-24 review examined the existing 48-pack, 1,132-entry catalog before
adding new content. Strict loading and programmatic checks covered every clause,
both its prose and tag rendering, model references, variants, identities and
axis ownership. Editorial review focused on candidates that changed setting,
entity count, lettering or fixed scene content, and on the recently added
scene-themed packs. This is a targeted authoring review supported by complete
structural scans, not a claim that a regex understands every semantic conflict.

## Findings and changes

| Finding | Why it matters | Change |
| --- | --- | --- |
| Literal scene substitution | A base with people could receive an "empty school corridor" tag or an instruction to replace its setting | Recast location-themed presets as rendering, spatial-rhythm and light treatments of supplied forms |
| Prose and tags disagreed | Safe prose could still become an unsafe tag phrase in SDXL/Anima | Revised both representations together, including conditional text-preservation phrases |
| Unclaimed authored axes | A later grade could not replace an earlier palette clause that was merely additive | Added 529 missing claims; every bundled base/variant clause now owns its axis |
| Added text or symbols | A timecode modifier could fabricate a readout unrelated to the user's sign | Timecode styling now requires supplied timecode text; no arbitrary timestamp is created |
| Duplicated representation | Contact-sheet and reflection wording could multiply supplied people or objects | Keep a single supplied scene; use margins, contour rhythm or tonal echoes instead |
| Frozen setting assumptions | Furniture, water, screens and architecture leaked from the aesthetic's name into arbitrary subjects | Removed or made those treatments conditional on supplied forms/materials |

The review revised **201 clauses and their tags across 19 existing packs** and
changed 307 existing entries through text or claim edits. Stable IDs are retained;
each changed pack's minor content version advances. Most changes are in Analog
Horror, Cozy Nostalgia, Dreamcore, Internet Aesthetics, Liminal Spaces, Weirdcore
and Symbolism/Metaphysical Art. Targeted fixes also cover the other added packs,
Botanical, Culinary, Garden Art and Landscape/Weather.

Preset names and search tags may still name the aesthetic's source setting.
Those are discovery metadata; only the selected clause text/tags are sent to the
model. A "school hallway" reference now describes institutional stillness and
existing geometric rhythm, rather than requiring a school or removing its people.

All bundled axes are conservatively owned. With `last_wins`, a later layer can
replace a full look's lighting, composition or palette on the same axis. With
`first_wins`, the first declared direction is retained; `error` rejects competing
claims. This increases predictable suppression, but may change old multi-style
outputs. A locked axis still suppresses all style clauses on it. Unclaimed
additive clauses remain legal for administrator-authored community packs; they
are outside the bundled policy checked by the review tool.

## Added coverage

The review favored small complementary packs rather than another broad genre list:

| Pack | Entries | Purpose |
| --- | --- | --- |
| Computational Surfaces | 8 styles | Contour engraving, field-pattern lacquer, distance relief, arc inlay, dithered fibers, cellular glass, interference satin and density-coded plotting |
| Optical Material Accents | 8 modifiers | Local light-response effects on appropriate supplied materials |
| Animation Finishing | 8 modifiers | Line cadence, shadow grouping, registration, optical compositing and detail economy for still images |
| Information Hierarchy | 8 modifiers | Supplied text, connectors, label association, counts and spatial relationships remain readable during stylization |

The resulting catalog has **1,164 entries in 52 packs**: **1,017 styles, 69 grades
and 78 modifiers**. These are authored visual descriptions, not physical optical
simulation, animation output or a new set of model capabilities. Conditional
instructions are retained in tag renderings where a short unconditional tag
would change the meaning. New packs use the existing profiles; no undocumented
model-specific variant is claimed.

## Base prompt toolkit

[The LLM toolkit](../llm-prompts/README.md) supplies seven copyable authoring
prompts, six frozen semantic scenes and five replayable recipes. A useful base
reserves artistic choices for the presets while retaining real content facts.
Avoiding a global palette does not justify erasing a required red life jacket.
Explicit identity colors may require a palette lock; fixed spatial relationships
may require a composition lock. Those choices necessarily limit incompatible
parts of a style. They cannot be inferred perfectly from arbitrary prose.

Model-native handoff remains separate. Natural and tag profiles retain the base
string; Fibo generation places it in `short_description`. Existing structured
fields win under Fibo's adapter. Edit instructions remain in the native reference
workflow. MOSS Layout, other model wrappers, dimensions, samplers and LoRAs are
not produced by these metaprompts unless a separate workflow expressly needs them.

## Reproducing the checks

```sh
python scripts/audit_library.py --check
python -m pytest tests/test_library.py tests/test_base_prompts.py -q
```

Run the scripts from a checkout with the project installed, for example with
`pip install -e '.[dev]'` in a separate development environment. The audit emits
the exact catalog fingerprint, full inventory counts and authoring errors. Its
content hints are incomplete review candidates; zero hints is not semantic proof.

Corpus regressions exercise every eligible entry using natural, tag and structured
output profiles across six subjects and three authored intensity tiers. They check
exact base serialization, recipe replay, axis-lock traces and reviewed scene/tag
regressions. Every registered profile also runs the general library composition
test. Archive checks include the toolkit, examples and scripts in the source
distribution and compare all pack bytes with the wheel.

## Evidence limits

No LLM was used as an automated judge of its own metaprompts, and no image quality
grid was generated. Source review and deterministic tests cannot establish that
all presets produce equally strong images. Anima's documented realism/text
limitations, distilled checkpoints' intrinsic looks, exact-text failures and
aggressive abstraction still matter. Use the [visual evaluation plan](../llm-prompts/examples/README.md)
with the actual checkpoint and workflow before claiming model-specific aesthetic
quality. Pack revisions intentionally change catalog/recipe fingerprints; replay
old pack versions when exact historical styled text is needed.
