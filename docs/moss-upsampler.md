# MOSS prompt upsampler (Qwen3.5-2B fine-tune)

**Load Prompt Upscaler → MOSS Prompt Upsampler → Preview / Style** expands a short idea
into a rich, vivid natural-language prompt for MOSS-Image and similar T2I models.

The model is [`NidAll/moss-qwen3.5-2b-upsampler-v2-bf16`](https://huggingface.co/NidAll/moss-qwen3.5-2b-upsampler-v2-bf16),
a BF16 fine-tune of `huihui-ai/Huihui-Qwen3.5-2B-abliterated` trained on
`NidAll/moss-pup-qwen35-curated-12k` (v2; LoRA r=32 on language attention and MLP; vision frozen).

## Prompt contract

The node follows the model card:

- System prompt, verbatim from SFT: `Expand the user prompt into a rich, vivid image
  generation prompt. Output only the final prompt.`
- The user turn is your draft. No instructions or lenses are added.
- Thinking is off (`enable_thinking=False`): ComfyUI's Qwen3.5 template appends the empty
  `<think>\n\n</think>\n\n` block.

Variety comes from sampling: each seed writes a different take. Defaults follow the v2 model
card (temperature 0.6, top_p 0.9, repetition penalty 1.05; top_k 20, min_p 0, no presence
penalty); temperature 0 decodes greedily and repeats exactly.

### Output guard (temporary v2 workaround)

v2 has three known output defects: visible text nobody asked for (watermarks, signatures,
credit lines, quoted titles and shop names, lettering), negation tails ("with no modern
signage", which T2I encoders tend to draw), and color words in black-and-white requests.
Changing the system prompt is not an option (the model was trained on one fixed prompt), so
the `guard` input (on by default, `comfyui/upscaler/moss_guard.py`) works around the model:

- Before generation, provenance tokens in the draft are replaced with what they mean
  visually: "trending on artstation" → "polished concept art", "unreal engine"/"octane
  render" → "crisp high-detail 3D render", "8k"/"4k"/"uhd" → "ultra-detailed". Artist names
  and titles stay.
- The kept take is cleaned against the draft: unrequested quoted text goes (`a firework reads
  "your name"` → `a firework`), a clause or sentence about watermarks, credits or lettering
  goes ("signature brushwork" stays), negation tails go unless the draft itself says
  no/without, and black-and-white drafts lose color words and gain a `Black-and-white
  photograph.` prefix if needed. If the draft asks for text (quotes, sign, poster, logo, title,
  ...), text descriptions stay.
- If cleaning would remove more than 30% of the prompt, the guard refuses the take. With
  `max_takes` above 1, a sampled run then writes another take (seed+1, ...); otherwise, or when
  every take is refused, the take with the fewest detected defects comes back unchanged with a
  warning to resample. Takes the guard can clean are never rewritten, so a normal run costs
  one generation. Greedy runs always write one take.

Inspection's `guard` block lists each take's seed, defect count and whether it was refused, the cleaning
report and the raw take when it changed. These are regular expressions: wording they do not
list ("a block-letter motif", "glyphs") still gets through, and the defect count uses the
same patterns, so it is not an independent measurement. Remove the guard once a retrained
model fixes the defects. `guard`, `max_takes` and `repetition_penalty` are optional
trailing inputs; saved graphs without them get the defaults.

Checked live with INT8 ConvRot on 2026-11-22 (10 drafts aimed at the known failures plus
three controls; an earlier best-of-2 variant, unguarded vs guarded Explore vs guarded Faithful): unguarded takes
had 9 detected defects in 4 of 10 drafts (shop names and street-sign text in an 1890s street,
"RUSH HOUR" signs, a title in the draft's own words over fireworks); guarded takes had none
left, and every edit removed only the lettering or the negation tail. The poster draft kept
its requested `"STARFALL"`, the "without any people" draft kept its absence clauses, and the
monochrome draft had no color words. The guard did not refuse any of 54 live takes, so best-of-2
was replaced by retry-on-refusal: a guarded take now costs one generation. Image quality with
guarded prompts was not evaluated.

### Style

The model writes its own medium in the first sentence (often "Full-color photograph..."),
which can fight a separately applied Style. The optional `style` input fixes that without
an instruction: a short look (for example a PromptStyler Next style clause) is appended to
the draft as a trailing clause, `<draft>, <style>`, capped at 30 words. Training drafts
already name media this way ("Art Nouveau illustration of ...", "film still of ..."), so the
model then writes the whole prompt in that look. Inspection reports `style` and the exact
`user_text` sent.

Checked with 4 drafts × 6 PromptStyler looks plus no style, greedy and at 0.7 (56 runs, INT8
ConvRot): every styled run opened with the requested medium (Art Nouveau illustration,
medium-format film photograph, Symbolist painting, children's anime art, punk zine,
two-strip color film still), none was truncated, the subject was kept in every run, and the
quoted sign text was kept in all 14 bakery runs. Painted and drawn looks did not pick up
camera vocabulary. The model sometimes adds detail to the medium ("Symbolist oil
painting"). Image quality with these prompts was not evaluated.

Training drafts are short (median 13 words, at most 40) and targets run about 150-380
words; v2 targets reach about 637 tokens, so `max_new_tokens` defaults to 700 (generation stops
at the end token anyway). If the budget runs out,
the cut-off tail is trimmed to the last full sentence and inspection says so. Long or
already detailed drafts are outside the training distribution: the model expands them
again and can drift.

## Speculative decoding (MTP draft head)

Decoding one token reads every INT8 linear plus the BF16 tied embedding/output head (248k
vocabulary, about 0.97 GiB), so decode is memory-bandwidth bound and already replays CUDA graphs
in core. The remaining lossless lever is core's MTP speculative decoding, which needs a Qwen3.5
MTP head. The v2 export has none, but its base model `huihui-ai/Huihui-Qwen3.5-2B-abliterated`
ships one (15 `mtp.*` tensors, about 116 MiB BF16). Grafting those tensors into the INT8 file
leaves every main-model tensor byte-identical; core detects `mtp.fc.weight` and the node then
calls `CLIP.generate(..., mtp=True)` (core's adaptive schedule). The main model verifies every
drafted token (its own argmax, or a sample from its own distribution), so the head changes speed,
not which prompts can come out. Outputs are not bit-identical to plain decoding: the verify pass
runs several tokens at once with different kernels, and near-tie argmax choices can flip.

The gain is modest because each drafted token also reads the full output head, and the head was
trained on the base model, not the fine-tune. Core's fixed MTP modes (`2`, `3`, `tree2s1`) were
slower than plain decoding in our measurement; only the adaptive default helped (single-digit to
about 10%). Measure on your own GPU before relying on it. A file without `mtp.*` tensors decodes
normally.

## Runtime

The checkpoint is an ordinary ComfyUI Qwen3.5-2B text model. Loading, VRAM management,
offload and decoding are ComfyUI core (`comfy.sd.load_clip`, `CLIP.generate` with the
quantized-matmul context), so the INT8 ConvRot layers run on comfy-kitchen kernels. The
loader recognises any Qwen3.5 hybrid checkpoint in `models/anima_prompt_architect/`; the
node refuses other upscaler families, and the LFM3 nodes refuse this one. The checkpoint
has no MTP head unless one is grafted (see above). Text only: the frozen vision tower is
kept but unused.

## Preparing the INT8 ConvRot file

Download the BF16 source explicitly, then convert offline with the Native Quantizer's
`text_encoder_qwen35` policy:

```sh
hf download NidAll/moss-qwen3.5-2b-upsampler-v2-bf16 \
  --revision f8bf07dd8291c56068749cc2223afdafe81ca2c5 --local-dir moss-upsampler-source
comfyquant moss-upsampler-source/model.safetensors --no-config --format int8-convrot \
  --components text_encoder --architecture text_encoder_qwen35 --int8-convrot-groupsize 256 \
  --device cuda --target-runtime nvidia --max-memory 1G --validate \
  --output /path/to/ComfyUI/models/anima_prompt_architect/moss-qwen3.5-2b-upsampler-v2-int8-convrot.safetensors
```

This selects 150 language linears (full attention, Gated DeltaNet `in_proj_qkv`,
`in_proj_z`, `out_proj`, and the MLPs) at INT8 ConvRot group 256. The tied
embedding/head, norms, recurrent gates (`in_proj_a/b`, `A_log`, `dt_bias`, conv) and the
vision tower stay BF16. The file is about 2.85 GiB.

Executable graph: [MOSS upsampler](../examples/comfyui-moss-upsampler-api.json).

The fine-tune inherits the base model's license and the abliterated base's behavior: it
does not refuse. Review prompts before generating. End-to-end MOSS image quality with
these prompts has not been evaluated here.
