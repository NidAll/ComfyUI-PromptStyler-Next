# Python API

The public imports are `Engine`, `Recipe`, `Layer`, `Composition`, `Profile`,
`ModelAdapter` and `StylerError`. Python 3.11+ is required; no host imports occur.

```python
from promptstyler_next import Engine, Layer, Recipe

engine = Engine.builtin()
styles = engine.list_styles(query="ink", model="anima", category="illustration")
recipe = Recipe(
    prompt="A heron standing in shallow water",
    model="anima",
    styles=(Layer("illustration.gouache", 0.75),),
    locked_axes=("composition",),
)
result = engine.compose(recipe)
# Mapping input is validated identically:
assert engine.compose(recipe.to_dict()).fingerprint == result.fingerprint
```

`list_styles` accepts keyword-only `query`, `category`, `model`, `tags`, `kind`,
`limit` (0–1000), and `offset` (0–8192). Query terms must all match indexed metadata;
category filtering includes descendants. Tags are exact and all requested tags
must match. Model aliases resolve before eligibility filtering.

`get_style(id)` returns full metadata and clauses. `profiles()` returns capabilities,
guidance and sources. `recommend(prompt=..., model=..., limit=6)` returns metadata
with integer `score` and `reasons`; empty/no-overlap queries return no suggestions.
Metadata/results are copies, so UI changes cannot mutate an engine's catalog.

`compose` accepts one recipe and returns a frozen `Composition`. Its fields include
`positive`, `negative`, `profile`, `recipe`, `warnings`, `trace`, `fingerprint` and
`catalog_fingerprint`. `structured` returns a copy with the original subject,
format, selected axis clauses and protected axes. `to_dict()` produces the complete
JSON response. Neither API stores a prompt history.

## Error contract

Catch `StylerError`, a `ValueError` subclass. `code`, `message`, and `path` are
stable fields; `to_dict()` provides those fields for integrations. Example codes:

| Code | Meaning |
| --- | --- |
| `invalid_json`, `duplicate_key`, `input_too_large`, `input_too_deep` | Rejected transport or pack JSON |
| `unknown_field`, `missing_field`, `invalid_type` | Schema violation |
| `unsupported_schema`, `invalid_intensity` | Unsupported version or numeric input |
| `unknown_style`, `duplicate_style`, `duplicate_pack` | Catalog identity failure |
| `unsupported_style`, `unknown_profile` | Pack/model contract mismatch |
| `style_conflict` | Error-policy conflict on a declared axis |
| `invalid_caption` | Invalid structured caption field |

Unsupported negative text and unknown-model fallback are warnings in the result,
not hidden behavior. Invalid recipes fail before any encoder is called.

## Add a pack

```python
engine = Engine.builtin().with_packs(["./my-styles.json"])
```

For a custom-only catalog, use `Engine.from_packs([...])`; it retains builtin model
profiles without merging builtin styles. Paths are explicit, trusted configuration. There is no recursive directory scan,
remote pack fetch, executable plugin discovery or mutation of the original engine.
Duplicate IDs cannot override builtin content. Use a private ID namespace.

## Add a model adapter

Profiles and adapters are trusted Python code, registered explicitly. Register the
profile *before* loading packs that reference it. `Profile.from_dict` validates the
same record used by builtin profile JSON.

```python
from promptstyler_next import Engine, Profile
from promptstyler_next.adapters import NaturalAdapter

profile = Profile.from_dict(
    {
        "id": "my-caption-model",
        "name": "My caption model",
        "format": "natural",
        "negative": False,
        "weighting": False,
        "conditioning": "specialized",
        "guidance": "Use plain visual captions and the model's native encoding node.",
        "sources": [],
        "evidence": "conservative",
        "aliases": [],
    }
)
engine = Engine.builtin().with_adapter(profile, NaturalAdapter(revision="my-caption/1"))
```

For a genuinely different format, implement the `ModelAdapter` protocol:
`revision: str`, `locked_axes(prompt) -> tuple[str,...]` and
`render(prompt, clauses) -> str`. Clauses are immutable records with `axis`, `text`,
`tags` and `min_intensity`. Your adapter must be deterministic, preserve user
content, avoid I/O and mutable state, and change its revision when behavior changes.
Registration is not a sandbox for arbitrary code. Pack JSON cannot register code.

Model guidance, text formatting and conditioning are separate. Adding a model
profile does not prove any particular text encoder is compatible with another
model's conditioning tensors.
