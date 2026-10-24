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
    "claims": {"medium": "ink-and-wash"},
    "clauses": [
      {"axis": "medium", "text": "Render with precise ink lines and transparent watercolor washes", "tags": ["ink and watercolor"], "min_intensity": 0},
      {"axis": "texture", "text": "Leave fine paper fibers visible through the pigment", "tags": ["paper grain"], "min_intensity": 0.65}
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

`min_intensity` is finite and between 0 and 1. It gates the clause at or above that
threshold; intensity zero always bypasses every clause. Use the low tier for the
recognizable visual identity, higher tiers for secondary material/light/detail.
Do not use tiers to stuff a prompt with generic quality words.

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
