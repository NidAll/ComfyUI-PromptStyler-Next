# Contributing

Start with [architecture](docs/architecture.md), [development](docs/development.md)
and the relevant [pack](docs/packs.md), [model](docs/models.md),
[ComfyUI](docs/comfyui.md), or [Studio](docs/studio.md) contract.

Keep the deterministic engine independent of host frameworks, model weights and
network services. Add only dependencies justified by a real capability gap.
Describe the user-visible trigger, result and meaningful validation in a change.

Style contributions need distinct authored visual direction, accurate process
language, provenance for preview assets and an explicit license. New model
capabilities need primary-source evidence and appropriate adapter/host tests.
Do not claim quality or acceleration from schema checks alone.

For bundled packs, claim every authored clause axis and review both prose and tags
for invented scene content. Run `python scripts/audit_library.py --check` and the
base-corpus tests. Toolkit contributions should preserve semantic facts and exact
text while deferring optional art direction; see [the toolkit](llm-prompts/README.md).

Code contributions use Apache-2.0. First-party pack contributions are intended for
CC0-1.0 unless agreed otherwise; third-party packs retain their declared license.
