# LFM3-VL prompt rewriting (experimental)

Select `lfm3-vl-2b-int8-convrot.safetensors` in **Load Prompt Upscaler** and
choose `moss_image_base` or `anima` in **Upscale Base Prompt**. Other image-model
targets are outside this experiment. Connect the resulting scene prose to
Style/Compose, then the appropriate image model's text encoder.

LFM3-VL rewrites the complete caption. Expanded first retains the supplied scene,
then requests a few concrete details about existing subjects' pose, shape, parts
and contact. Curated examples teach literal surreal actions and shared-object
relationships. Detailed inputs use the same contract, with no word-count cutoff.
Faithful uses a concise preservation example and requests minimal changes.
Image-only input produces a grounded caption.
Image plus text first grounds the reference, then describes the requested final
scene in a second text pass. A failed lexical fidelity check can trigger one
additional repair. The first draft is retained if a repair loses a previously
satisfied lexical check or fails to improve the checks. Explicit standalone
`No ...` / `Without ...` clauses are restored verbatim and listed in inspection.
Repeated descriptions of the same requested label do not count as new wording.
No assistant premise is copied into the generation prefix.

This is inference-time behavior guidance, not teacher-model training or weight
distillation. Artistic treatment belongs in Style/Compose. Inspection flags a
limited set of style terms outside quoted display text and can request a repair;
it does not reliably recognize every aesthetic phrase.
Pure comma clauses containing only recognized aesthetic vocabulary are removed
and listed in `removed_style_clauses`. Clauses containing scene nouns, semantic
colors or quoted text are retained; ambiguous style language remains a warning.

Inspection records the contract, target, each stage, timings, token counts,
reference caption, initial/final fidelity checks and unresolved warnings. These
checks recognize only limited textual cues. They cannot prove subject bindings,
negations or scene fidelity. The model can invent scenery, miss details or alter
relationships even without a warning. Expanded mode can still invent a setting,
material or prop; Faithful is the conservative choice. Review before generation. Longer captions
are not automatically better, and image-quality parity has not been established.

## Single-file installation

Place the prepared artifact in `ComfyUI/models/anima_prompt_architect/`. It
contains weights plus hash-checked configuration, tokenizer, processor, chat
template and generation settings. The pinned runtime is local package code;
embedded data never imports executable code. Nodes do not download models or
upgrade dependencies. The existing MiniCPM route remains available.

The port was tested with Transformers 5.15.1 and native ComfyUI/Kitchen CUDA
operations. Text uses the upstream convolution/full/sliding-attention pattern;
vision and projector remain BF16. The tied head shares the BF16 token embedding.
Native GEMV and byte-preserving MLP/QKV projection fusion are enabled. Text and
vision use ComfyUI's selected attention dispatcher with explicit causal/sliding
masks. Masked grouped-query inputs use ComfyUI's shared head-expansion helper.
The language
recipe selects 142 matrices with INT8 ConvRot group 256; other model weights stay
BF16. This is a mixed-precision artifact requiring this custom-node consumer,
not a model for stock CLIP or diffusion checkpoint loaders.

`max_new_tokens` defaults to 192 and is an output budget, not a guaranteed length.
For LFM3, each `image_slices` unit permits up to 512×512 processed pixels while
retaining aspect ratio. One is the fast default; additional detail costs memory
and time. `offload_after` trades repeated-edit latency for immediate VRAM release;
ComfyUI can otherwise offload the managed handle when another model needs memory.

## Offline preparation

Use the updated Native Quantizer with `lfm3_vl_2b` support. Download explicitly,
then convert from local files using ComfyUI's Python environment:

```sh
hf download LiquidAI/LFM3-VL-2B \
  --revision f83d2b0a2296aaa277f394990a9b8b949ddf9691 --local-dir lfm3-vl-source
python scripts/prepare_lfm3.py --source lfm3-vl-source \
  --output /path/to/ComfyUI/models/anima_prompt_architect/lfm3-vl-2b-int8-convrot.safetensors \
  --device cuda --convrot-groupsize 256
```

The script preserves the source, validates conversion and publishes a new file
atomically. It also supports `--format bf16` for a separate reference bundle,
`--exclude` for sensitivity experiments and groups 16/64/256. Group 256 with
fusion was fastest among the measured candidates on the development GPU; this
does not establish a universal optimal recipe or prompt-quality equivalence.

The native runtime has numerical prefill/decode, vision, tied-weight, projection
fusion and width-7 convolution regressions. Real text, image and reference-edit
captions were also inspected. Different valid attention kernels can change
BF16 rounding and greedy captions; byte-preserved projection weights do not imply
identical generated text. End-to-end Anima/MOSS image quality remains untested.

For a portable local timing run, use `scripts/benchmark_upscaler.py` with
`--comfyui-root`, `--model-name lfm3-vl-2b-int8-convrot.safetensors`,
`--target-model anima` or `moss_image_base`, and `--max-new-tokens`.
Compare equal token workloads separately from caption latency, which varies with
output length and the number of repair/grounding passes.

The model is governed by the upstream **LFM Open License v1.0**. Vendored Python
files retain their Apache-2.0 notices; see the runtime's `NOTICE.md` and licenses.
Weights are separate from this source repository and have not been published here.

Executable graphs: [MOSS Base](../examples/comfyui-lfm3-moss_image_base-api.json)
and [Anima](../examples/comfyui-lfm3-anima-api.json).
