# Reference audit and design decisions

Audit date: 2026-10-24. References were fetched into independent read-only audit
checkouts; implementation commits belong only to the new repository.

## Original PromptStyler

Audited [NidAll/ComfyUI_PromptStyler at
7c837d1ba4ceae2ccb7e1f164dc190d9cd2b0d58](https://github.com/NidAll/ComfyUI_PromptStyler/tree/7c837d1ba4ceae2ccb7e1f164dc190d9cd2b0d58).
Its 24 style packs contain 585 entries. The legacy snapshot also contains 585;
those are alternate representations, not 1170 distinct styles.

Reusable ideas: stable style IDs, searchable taxonomy, explicit visual styles and
color-grade overlays, pack-based distribution, and access to the exact text sent
to the encoder. Its single-node workflow is approachable for a user who wants to
pick a look and continue sampling.

The audited executable entry point registers one V1 conditioning node. Its
`nodes.py` has its own template loader/composer, while `style_library.py` contains
another richer implementation with search, strength and overlays. README advanced
node descriptions are broader than the actual registration at this revision; this
audit treats source registration as authoritative. Compatibility/fallback paths
and two implementations make it harder to reason about one public composition
contract. The default path splits and rejoins the subject as comma phrases, so it
can normalize whitespace or remove user repetitions. Variants use prefix/suffix
strings and a default fallback rather than explicit model capability contracts.

PromptStyler Next keeps the useful concepts but independently implements one
standalone engine, immutable validated clauses, declared axis conflicts, model
profiles, user-text preservation, and inspectable recipes. It copies neither
legacy source nor template prose, and implements no old node IDs or interfaces.

## HEISS Studio

Audited [tristmeister/HEISS-UI at
871e1934cbe03153499fa05ec79747b3173f2999](https://github.com/tristmeister/HEISS-UI/tree/871e1934cbe03153499fa05ec79747b3173f2999),
version 0.18.1. Source inspection covered server setup and access guards,
`useGenerationActions.ts`, graph builders, package metadata and imported workflow
composition. Its React/Vite frontend and Express ESM server communicate through
fresh-generation bodies before the server builds a ComfyUI graph.

There is no general style-plugin loader to target. The chosen integration is an
explicit same-origin Express mount to a local Python sidecar, plus a typed client
and generation-body helper. This avoids a second JavaScript algorithm and avoids
modifying graph builders. A workbench supplies a functional reference browser;
maintainers can use its contract in their own React panel. Exact integration and
retry/conditioning boundaries are documented in [studio.md](studio.md).

## Current ComfyUI conventions

The extension uses `ComfyExtension`, `comfy_entrypoint`, `io.ComfyNode`, schema
inputs/outputs and scheduled native encoding. References:
[official ComfyUI guidance](https://github.com/Comfy-Org/ComfyUI/blob/master/AGENTS.md),
[V3 migration and extension documentation](https://docs.comfy.org/custom-nodes/v3-migration),
and native installed API source. Actual host registration tests use ComfyUI
`7cebca52227c63b4180ceed448cbd7ad22903b6d`; CI pins that public revision for a
repeatable contract check rather than assuming future `latest` remains identical.

The integration directory is named `comfyui/` to avoid shadowing the host's
`comfy` package. Text styling and optional conditioning are separate nodes.
Native model management, tokenization and encoding remain with ComfyUI.

## Deliberate tradeoffs

- Standard-library runtime: predictable installation and no ComfyUI dependency
  changes. JSON Schema is an editor/test artifact; explicit runtime validation
  enforces the same shapes and additional cross-record invariants.
- Deterministic semantic *axes*, not an embedded language model: declared conflicts
  and protected user choices are inspectable; arbitrary language understanding and
  visual quality prediction are not claimed.
- Authored clause tiers, not numeric prompt-weight interpolation: intensity is
  meaningful across architectures without pretending a universal weighting syntax.
- Accurate native encoders: specialized families use text handoff to their native
  workflow; unsupported conditioning is explicit rather than a generic CLIP guess.
- Original authored packs and precise process language: no copied legacy text,
  artist-identity shortcuts or meaningless quality boosters. Image-generation
  acceptance remains separate from structural validation.
