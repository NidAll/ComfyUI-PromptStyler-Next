# PromptStyler Next

A creative styling engine with explicit model profiles, composable visual directions,
and reproducible recipes. Use it from Python, ComfyUI V3, or a local style workbench
that can connect to HEISS Studio.

The engine has **no runtime dependencies**. It runs offline, does not load a model,
and does not send prompts to an external service. This is a separate implementation
and repository; the original [PromptStyler](https://github.com/NidAll/ComfyUI_PromptStyler)
remains independent.

## Start with a recipe

Python 3.11 or newer:

```sh
python -m pip install .
promptstyler-next serve --port 8791
```

Open [the local workbench](http://127.0.0.1:8791) to browse categories, search tags,
save favorites, order layers, tune intensity, protect prompt attributes and inspect
composition. It exports recipes for replay. Abstract palette swatches identify
entries; they are not generated image previews.

```python
from promptstyler_next import Engine

engine = Engine.builtin()
result = engine.compose(
    {
        "schema_version": 1,
        "prompt": 'A botanist in a rooftop greenhouse, a sign reading "OPEN"',
        "model": "flux",
        "styles": [
            {"id": "cinema.noir", "intensity": 0.8},
        ],
        "locked_axes": ["composition"],
        "conflict_policy": "last_wins",
    }
)
print(result.positive)
print(result.fingerprint)
print(result.to_dict()["trace"])
```

Or use the CLI:

```sh
promptstyler-next styles --query noir --model flux
promptstyler-next profiles
promptstyler-next compose examples/recipe.json
promptstyler-next recommend 'botanical ink illustration' --model anima
```

## One engine, three interfaces

| Interface | What it provides | Installation |
| --- | --- | --- |
| Python / CLI | Discovery, validated packs, composition, inspection, metadata recommendations | `pip install .` or a built wheel |
| ComfyUI V3 | Single-style node, JSON recipe node, native text conditioning for compatible profiles | Clone this complete repository into `ComfyUI/custom_nodes/` |
| Studio | Local workbench, versioned HTTP API, typed JS client, Express bridge for HEISS | Run the Python service; explicitly mount the bridge in HEISS source |

The Python wheel contains the engine, data, schemas and workbench. The complete Git
checkout or source distribution also contains the ComfyUI extension and Studio
module. Installing a wheel alone does not register ComfyUI nodes.

[ComfyUI instructions and workflows](docs/comfyui.md) explain standalone text and
conditioning paths. [HEISS integration](docs/studio.md) documents the actual server
mount and fresh-generation hook; HEISS does not provide a general third-party
plugin loader, so this package does not silently install a panel into it.

## What composition does

A style declares clauses on seven visual axes: medium, lighting, palette,
composition, texture, mood and detail. Intensity activates authored clause tiers,
without multiplying token weights or changing sampler settings. A zero-intensity
layer contributes no styling.

Layers can declare incompatible claims on an axis. Resolve them by first layer,
last layer, or an explicit error. Only that axis is suppressed; a new color grade
can change a palette while retaining the original drawing medium. Lock an axis to
protect a choice in the subject. Every applied, skipped, duplicate or suppressed
clause appears in the inspection trace.

The subject remains verbatim in prose/tag profiles, including exact quoted text,
Unicode, whitespace and encoder syntax. Fibo is different: its adapter preserves
the subject in `short_description` and maps styling to published caption fields.
Existing supplied caption fields take priority. The engine does not infer objects,
positions, hidden scene content, or free-form semantic contradictions.

## Model profiles

Profiles cover SDXL, FLUX, Qwen-Image, Qwen-Image 2.1, MOSS-Image, MOSS DMD,
Anima, Anima Turbo, Fibo 2 and an unknown-model fallback. They distinguish tags,
natural captions and structured captions, negative-prompt capabilities, native
conditioning paths and evidence limits. [Model sources and assumptions](docs/models.md)
are part of the public contract.

A profile describes a workflow convention, not every checkpoint in a family.
Unknown models get conservative prose with an inspection warning. Unsupported
negative prompts are omitted from output and preserved in the saved recipe.
Direct generic conditioning is available only for explicitly compatible profiles;
specialized encoders remain in the native workflow.

## Style packs and extension points

The library contains 832 authored entries in 33 packs, compared with 585 in the
audited reference. It covers cinema, photography, illustration, anime, manga, historical
fine art, printing, graphic design, 3D, architecture, material arts and more, with
independent color grades and modifiers. See [the library guide](docs/style-library.md)
for the inventory and curation policy.

Packs are versioned, bounded JSON data. IDs are stable, duplicates fail, and there
is no executable templating, dynamic import, remote loading or pack upload API.
Community packs retain their own declared license. Register trusted Python model
adapters explicitly; no engine changes are needed to add a profile.

- [Architecture and composition rules](docs/architecture.md)
- [Python API and extension guide](docs/api.md)
- [Custom pack format](docs/packs.md)
- [Development and release checks](docs/development.md)
- [Validation evidence and acceptance limits](docs/validation.md)
- [Reference audit](docs/reference-audit.md)

## Development

```sh
python -m pip install -e '.[dev]'
python -m pytest
ruff check .
ruff format --check .
mypy
node --test studio/tests/*.test.mjs
python -m build
```

Actual ComfyUI tests run separately with a ComfyUI checkout and its environment;
standalone environments skip only that host-specific module. CI tests Python
versions, property and HTTP contracts, Studio transport, real host registration,
strict typing and installed artifacts.

Code: [Apache-2.0](LICENSE). First-party style definitions: [CC0-1.0](STYLE-LICENSE).
No model weights or third-party style text are bundled. Model licenses and host
application licenses remain independent.
