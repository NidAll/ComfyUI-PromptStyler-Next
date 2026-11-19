# Style pack contract

JSON Schema files ship under `promptstyler_next/schemas/`. Editors can validate
against the Pack, Recipe and Profiles schemas. Runtime validation also enforces
cross-record identity, model references, active-claim consistency and JSON bounds.
Schemas have protocol version 1; pack content uses its own semantic version.

```json
{
  "schema_version": 1,
  "id": "community.botanical",
  "version": "1.0.0",
  "name": "Botanical studies",
  "description": "Restrained studies in ink and translucent washes.",
  "license": "CC0-1.0",
  "author": "Your name",
  "styles": [{
    "id": "community.botanical-fieldbook",
    "name": "Fieldbook wash",
    "description": "Measured ink lines with spare transparent pigment.",
    "category": "illustration/botanical",
    "kind": "style",
    "tags": ["botanical", "ink", "wash"],
    "claims": {"medium": "community.botanical-fieldbook", "texture": "community.botanical-fieldbook"},
    "clauses": [
      {"axis": "medium", "text": "ink and transparent watercolor study", "tags": ["watercolor (medium)", "ink (medium)"], "min_intensity": 0},
      {"axis": "texture", "text": "fine paper fibers under the pigment", "tags": ["paper texture"], "min_intensity": 0.4}
    ],
    "negative": [],
    "models": [],
    "variants": {}
  }]
}
```

IDs are lowercase dotted/dashed/underscored names, at most 96 characters. Categories
are slash-separated identifiers. `kind` is `style`, `grade` or `modifier`. A claim
maps an axis to an identity: different identities conflict; identical identities
can coexist. Declare only axes represented by clauses, including in every variant.
An unclaimed clause is additive and cannot participate in declared-claim conflict
resolution.

The bundled library claims every authored axis, using the style ID as the identity. Use the same policy for
contributed bundled packs so later lighting, palette and composition layers can
replace earlier directions. Administrator-owned external packs may deliberately
use additive clauses, but must assess the resulting contradictions themselves.
Review the tag form as carefully as the prose: a safe conditional description
must not become an unconditional setting, person, timestamp or label tag.

`min_intensity` is finite and between 0 and 1. It gates the clause at or above that
threshold; intensity zero always bypasses every clause. Bundled packs use three
standard tiers, which Studio names Subtle, Balanced and Strong:

| Tier | `min_intensity` | Use it for |
| --- | --- | --- |
| Core | `0` | The recognizable identity. A look starts with its medium. |
| Supporting | `0.4` | One secondary light, palette, composition or texture direction. |
| Finish | `0.75` | Fine technique detail. |

Each profile has a `style_budget` (words for prose and captions, tags for tag
models). Core clauses always render; supporting and finish clauses that would
exceed the budget are skipped and reported as `budget_skipped` in the trace, so
stacking several styles cannot flood a small text encoder.

## Writing clauses for image encoders

Clause text is read by a text encoder, not by an instruction-following model.
The bundled packs follow these rules, and `scripts/audit_library.py` checks them:

- Describe the visual result as a short noun phrase: "hand-inked anime cel art",
  not "Render the subject as hand-inked anime cel art".
- Never refer to the prompt or scene ("the subject", "existing", "supplied").
- No negation ("without", "no", "not") and no conditions ("if", "unless"): the
  encoder reads the negated words as requests.
- Keep core clauses to 8 words, other clauses to 12, and a whole look to about
  26 words at full strength. No brackets, colons or semicolons in text.
- Use 1-3 tags per clause, each at most 4 words. For booru-trained tag models
  (Anima), prefer tags the model knows, such as `watercolor (medium)`, `lineart`
  or `film grain`. `--vocab <tag list>` reports the known-tag share; every look
  needs at least one known tag.
- No mood axis: express mood through light, palette or composition.
- Hard palette words (monochrome, black-and-white, greyscale) belong only on
  the palette axis.

Rendering joins the selected clauses into one compact phrase after the prompt.
Tag profiles escape brackets (`watercolor \\(medium\\)`) so ComfyUI reads them
literally, and skip tags the prompt already contains.

## Retired styles

A pack may list `"retired": [{"id": "old.id", "replacement": "new.id"}]`. A recipe
that still names a retired ID composes with its replacement and a `style_replaced`
notice; an ID without a replacement is skipped with `style_retired`. Retired IDs
must not be live styles, and replacements must be. ComfyUI keeps retired IDs as
valid hidden values of the Style node so saved workflows keep loading.

Every clause has natural `text` and optional concise `tags`. A tag adapter uses
tags when present, otherwise the clause text. An exact model variant replaces the
entire clause/negative list for that profile; it does not append implicitly. Add
variants only when a documented convention justifies different content.

`models: []` means every registered profile is eligible. A nonempty list explicitly
restricts eligibility. Variant/restriction model IDs must exist in the registry;
a typo does not silently fall back. Restrictions represent curated intent, not a
claim that excluded models could never generate a related look.

Negatives are optional, unscoped phrases. Prefer positive visual descriptions.
They are omitted for unsupported profiles and when that style was partially
suppressed by a conflicting layer, a protected axis, or an intensity threshold. The engine preserves the user's own negative
prompt in the recipe even when its profile cannot use it.

## Preview metadata

Optional `preview` has `path`, `alt` and `kind` (`reference`, `generated`, `swatch`).
Use a relative `.png`, `.jpg`, `.jpeg`, `.webp` or `.avif` path, without traversal,
backslashes, URL schemes or an absolute root. Provide meaningful alt text and
accurate provenance. These paths are metadata only: the service never serves
arbitrary pack paths. A host implementing preview resolution must constrain assets
to its own known directory and license/provenance policy.

## Limits and loading

A JSON pack is at most 4 MiB, 24 levels deep, 2048 styles. A catalog supports at most
64 packs and 8192 styles. Each style has up to 32 clauses and variants. Recipe JSON
is bounded at its transport, with at most 16 distinct layers and 32768 characters
per prompt field. Unknown fields, duplicate JSON keys and non-finite values fail.
Packs never run string formatting: `{prompt}`, shell text and code-shaped strings
are literal text.

Core: `Engine.builtin().with_packs([...])`. CLI: put repeatable `--pack` before the
command. ComfyUI: place administrator-owned `.json` files in `custom_packs/` and
restart ComfyUI. Service: pass repeatable `--pack` at startup. Reloading creates a
complete new snapshot; it never edits a catalog in use.

## Contribution review

Describe a distinct visual practice using specific material, light, mark, palette
and compositional decisions. Avoid living-artist identity shortcuts, generic
“masterpiece” boosters, contradictions and arbitrary camera jargon. Preserve the
subject; do not invent characters, scenery, text or branded objects. Explain any
model restrictions and attach primary-source support for model-specific variants.
Include attribution and licensing for contributed text and previews. Test the pack
and inspect it at low, medium and high intensities with compatible layers.
