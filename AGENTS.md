# PromptStyler Next

Independent repository. Do not modify the original PromptStyler, ComfyUI core, models, dependencies, or unrelated running services. HEISS installation changes are authorized for the explicit Studio integration request of 2026-10-24; preserve user data and disabled automatic updates. Use current ComfyUI V3 APIs only. No compatibility shims. Core package must import without ComfyUI or third-party runtime dependencies. Python >=3.11. Public source and docs must be portable and omit workstation paths.

Owners: promptstyler_next/ owns engine, validation, adapters and pack data. comfyui/ owns V3 nodes. studio/ owns browser/Node integration. Python HTTP service belongs in promptstyler_next/service.py. Tests use pytest; optional Hypothesis is a development dependency only. Never load code, URLs, expressions, or arbitrary filesystem paths from pack input.

Use the existing ComfyUI venv for actual host tests; install dev tools only into a separate project environment. No heavy model downloads. Record validation limits, especially lack of image-quality acceptance. All implementation commits belong to this repository.

Public contracts are documented in docs/api.md, docs/packs.md and docs/studio.md. Full looks use distinct medium/texture claims; hard palette constraints belong only to the palette axis. Preserve this authoring boundary when adding styles.
