"""MOSS prompt upsampler: a Qwen3.5-2B fine-tune run through ComfyUI's native text model.

The checkpoint is a plain ComfyUI Qwen3.5 text encoder (INT8 ConvRot for the Kitchen kernels).
Loading, VRAM management and decoding belong to ComfyUI core (`comfy.sd.load_clip`,
`CLIP.generate`); this module owns only the fine-tune's prompt contract and output cleaning.
The v2 fine-tune's known output defects are handled by the temporary guard in `moss_guard`.
Importing it does not load Torch or model management.
"""

from __future__ import annotations

import json
import re

from . import moss_guard

CONTRACT_VERSION = "moss-upsampler-3"
FAMILY = "qwen35_upsampler"

# Exact system prompt used during SFT (model card); the user turn is the draft, thinking stays off.
SYSTEM_PROMPT = (
    "Expand the user prompt into a rich, vivid image generation prompt. Output only the final prompt."
)

# v2 training targets reach about 637 tokens; generation stops at end-of-sequence anyway, and a
# smaller budget cuts the longest takes (often right where a watermark sentence would be trimmed).
DEFAULT_MAX_NEW_TOKENS = 700
MAX_PROMPT_CHARS = 6000
# A selected PromptStyler look rides along as a short trailing clause of the draft. Training drafts
# are at most 40 words, so the look is capped well inside that; see docs/moss-upsampler.md.
MAX_STYLE_WORDS = 30

# The v2 model card's sampling (temperature 0.55-0.65, top_p 0.9); temperature 0 decodes greedily.
DEFAULT_SAMPLING = {"temperature": 0.6, "top_p": 0.9, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0}
DEFAULT_REPETITION_PENALTY = 1.05
# Guarded sampled runs write another take (seed+1, ...) only when the guard gives up on the last one.
MAX_TAKES = 4

_HEADER_KEY = "model.language_model.layers.0.linear_attn.A_log"
_NORM_KEY = "model.language_model.layers.0.input_layernorm.weight"
_THINK = re.compile(r"<think>.*?</think>", re.S)
_SENTENCE_END = re.compile(r"[.!?][\"'”’)\]]*(?=\s|$)")


def is_upsampler_header(keys) -> bool:
    """A Qwen3.5 hybrid text model in the prompt-model folder is treated as this upsampler."""
    return _HEADER_KEY in keys and _NORM_KEY in keys


def validate_prompt(prompt: str) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Enter a prompt to upsample")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"The upsampler accepts up to {MAX_PROMPT_CHARS} characters")
    return prompt.strip()


def compose_draft(draft: str, style: str = "") -> tuple[str, str]:
    """The user turn: the draft, then the style as a trailing ", <look>" clause. Returns (text, style used)."""
    style = re.sub(r"\s+", " ", style or "").strip().strip(" .,;")
    if not style:
        return draft, ""
    words = style.split()
    if len(words) > MAX_STYLE_WORDS:
        style = " ".join(words[:MAX_STYLE_WORDS]).rstrip(" .,;")
    return f"{draft.rstrip(' .,;')}, {style}", style


def clean_output(text: str, truncated: bool) -> tuple[str, list[str]]:
    """One paragraph, no reasoning block or wrapper quotes; a cut-off tail is trimmed to a sentence."""
    warnings = []
    text = _THINK.sub("", text).replace("<think>", "").replace("</think>", "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    if truncated:
        ends = list(_SENTENCE_END.finditer(text))
        if ends and ends[-1].end() > len(text) // 2:
            text = text[: ends[-1].end()].strip()
        warnings.append("The output budget ran out before the model finished; the last sentence was trimmed.")
    return text, warnings


def sampling(temperature: float, top_p: float, top_k: int, min_p: float, presence_penalty: float) -> dict:
    if temperature <= 0:
        return {"do_sample": False, "temperature": 1.0, "top_p": 1.0, "top_k": 0, "min_p": 0.0, "presence_penalty": 0.0}
    return {
        "do_sample": True,
        "temperature": float(temperature),
        "top_p": float(top_p),
        "top_k": int(top_k),
        "min_p": float(min_p),
        "presence_penalty": float(presence_penalty),
    }


# A checkpoint carrying a Qwen3.5 MTP draft head (`mtp.*`) decodes speculatively through core's MTP
# path. The main model verifies every drafted token (greedy argmax, or a sample from its own
# distribution), so the head changes speed only, never which prompts can come out.
MTP_KEY = "mtp.fc.weight"


def load(path):
    """Load through ComfyUI's Qwen3.5 text-encoder path; returns (clip, INT8 layer count, has MTP head)."""
    from safetensors import safe_open

    with safe_open(str(path), framework="pt", device="cpu") as reader:
        keys = list(reader.keys())
        if not is_upsampler_header(keys):
            raise ValueError("Select a Qwen3.5 MOSS upsampler checkpoint")
        width = reader.get_slice(_NORM_KEY).get_shape()[0]
        if width != 2048:
            raise ValueError(f"Expected the Qwen3.5-2B upsampler (hidden size 2048), found {width}")
        quantized = [key for key in keys if key.endswith(".comfy_quant")]
        for key in quantized:
            conf = json.loads(bytes(reader.get_tensor(key).tolist()))
            if conf.get("format") != "int8_tensorwise" or not conf.get("convrot") or conf.get("full_precision_matrix_mult", False):
                raise ValueError(f"Expected accelerated INT8 ConvRot metadata for {key}")

    import comfy.model_management as mm
    import comfy.sd
    import folder_paths

    if quantized and mm.get_torch_device().type != "cuda":
        raise RuntimeError("The INT8 ConvRot upsampler needs the CUDA/Kitchen backend")
    clip = comfy.sd.load_clip(
        ckpt_paths=[str(path)],
        embedding_directory=folder_paths.get_folder_paths("embeddings"),
        clip_type=comfy.sd.CLIPType.STABLE_DIFFUSION,
    )
    return clip, len(quantized), MTP_KEY in keys


def upsample(
    clip,
    prompt: str,
    *,
    seed: int = 0,
    temperature: float = DEFAULT_SAMPLING["temperature"],
    top_p: float = DEFAULT_SAMPLING["top_p"],
    top_k: int = DEFAULT_SAMPLING["top_k"],
    min_p: float = DEFAULT_SAMPLING["min_p"],
    presence_penalty: float = DEFAULT_SAMPLING["presence_penalty"],
    repetition_penalty: float = DEFAULT_REPETITION_PENALTY,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    style: str = "",
    guard: bool = True,
    max_takes: int = 1,
    speculative: bool = False,
) -> tuple[str, dict]:
    """Expand one draft (optionally with a short style clause); returns the prompt and an inspection.

    With `guard`, provenance tokens in the draft are replaced first and each take is cleaned against
    the draft. A sampled run writes another take (seed+1, ...) only when the guard gives up on the
    last one (cleaning would remove too much), up to `max_takes`; if every take is refused, the one
    with the fewest detected defects comes back unchanged with a warning. Greedy runs write one take
    (a retry would repeat it).
    """
    import time

    asked, style = compose_draft(validate_prompt(prompt), style)
    draft = moss_guard.prep(asked) if guard else asked
    settings = sampling(temperature, top_p, top_k, min_p, presence_penalty)
    limit = max(1, min(int(max_takes), MAX_TAKES)) if settings["do_sample"] and guard else 1
    stops = _stop_ids(clip)
    started = time.perf_counter()
    tokens = clip.tokenize(draft, system_prompt=SYSTEM_PROMPT, thinking=False, min_length=1)
    prompt_tokens = sum(len(row) for row in next(iter(tokens.values())))
    takes = []
    for index in range(limit):
        take_seed = (int(seed) + index) & 0xFFFFFFFFFFFFFFFF
        generated = clip.generate(
            tokens,
            max_length=int(max_new_tokens),
            repetition_penalty=float(repetition_penalty),
            seed=take_seed,
            mtp=bool(speculative),  # True = core's adaptive MTP schedule (fixed modes measured slower here)
            **settings,
        )
        truncated = not generated or generated[-1] not in stops
        text, warnings = clean_output(clip.decode(generated), truncated)
        if not text:
            continue
        cleaned, report = moss_guard.clean(asked, text) if guard else (text, [])
        found = moss_guard.defects(asked, text) if guard else 0
        takes.append({"seed": take_seed, "text": text, "cleaned": cleaned, "report": report, "warnings": warnings,
                      "tokens": len(generated), "truncated": truncated, "defects": found})
        if report != [moss_guard.SKIPPED]:
            break
    seconds = time.perf_counter() - started
    if not takes:
        raise RuntimeError("The upsampler returned no prompt; try another seed")
    accepted = [take for take in takes if take["report"] != [moss_guard.SKIPPED]]
    best = accepted[0] if accepted else min(takes, key=lambda take: (take["defects"], -len(take["text"])))
    text, report = best["cleaned"], best["report"]
    warnings = list(best["warnings"])
    if report == [moss_guard.SKIPPED]:
        warnings.append("The guard left this take unchanged because cleaning would remove too much; try another take.")
    return text, {
        "contract": CONTRACT_VERSION,
        "model_family": FAMILY,
        "system_prompt": SYSTEM_PROMPT,
        "user_text": draft,
        "style": style,
        "upsample": {
            "seed": best["seed"],
            "sampling": {**settings, "repetition_penalty": float(repetition_penalty)},
            "prompt_tokens": prompt_tokens,
            "output_tokens": best["tokens"],
            "max_new_tokens": int(max_new_tokens),
            "truncated": best["truncated"],
            "words": len(text.split()),
            "seconds": round(seconds, 2),
            "speculative": bool(speculative),
        },
        "guard": {
            "enabled": bool(guard),
            "prepped": draft != asked,
            "takes": [{"seed": take["seed"], "defects": take["defects"], "words": len(take["text"].split()),
                       "refused": take["report"] == [moss_guard.SKIPPED]} for take in takes],
            "defects": best["defects"],
            "report": report,
            "raw": best["text"] if text != best["text"] else "",
        },
        "warnings": warnings,
    }


def _stop_ids(clip) -> set:
    # SD1Tokenizer keeps the wrapped tokenizer under the attribute named by `.clip`.
    table = getattr(clip.tokenizer, clip.tokenizer.clip).tokenizer.get_vocab()
    return {table[name] for name in ("<|im_end|>", "<|endoftext|>") if name in table}
