"""Native-managed, serialized local prompt authoring. No global tensor caches."""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import comfy.model_management as mm
import torch
from PIL import Image
from transformers import StoppingCriteria, StoppingCriteriaList

from ...promptstyler_next.lexicon import find_prose
from . import idea_prompts, lfm_prompts, moss_upsampler
from .models import bundle_fingerprint, resolve_bundle
from .prompts import (
    CONTRACT_VERSION,
    clean_output,
    expansion_prefix,
    merge_request,
    messages,
    user_request,
    validate_request,
)

logger = logging.getLogger(__name__)


@dataclass
class UpscalerHandle:
    owner: Any
    processor: Any
    native_int8_layers: int
    identity: tuple
    load_seconds: float
    lock: Any = field(default_factory=threading.Lock)
    model_family: str = "minicpm"
    speculative: bool = False
    # LFM3 graph decode engine (caches + captured step); built on first use, owned by this handle
    engine: Any = None


def load_upscaler(model_name: str) -> UpscalerHandle:
    started = time.perf_counter()
    identity = bundle_fingerprint(model_name)
    path = resolve_bundle(model_name)
    from safetensors import safe_open

    with safe_open(path, framework="pt", device="cpu") as reader:
        family = "lfm3_vl" if "lfm3_vl" in (reader.metadata() or {}) else "minicpm"
        if family == "minicpm" and moss_upsampler.is_upsampler_header(reader.keys()):
            family = moss_upsampler.FAMILY
    if family == moss_upsampler.FAMILY:
        # A plain ComfyUI Qwen3.5 text model: core owns loading, offload and decoding.
        owner, coverage, speculative = moss_upsampler.load(path)
        processor = None
    elif family == "lfm3_vl":
        from .lfm3 import load_lfm3

        owner, processor, coverage = load_lfm3(path)
    else:
        from .loading import load_minicpm

        owner, processor, coverage = load_minicpm(path)
    if identity != bundle_fingerprint(model_name):
        raise RuntimeError("Upscaler file changed during loading; queue the workflow again")
    return UpscalerHandle(
        owner, processor, coverage, identity, time.perf_counter() - started, model_family=family,
        speculative=family == moss_upsampler.FAMILY and speculative,
    )


class ParagraphComplete(StoppingCriteria):
    """Match a few token IDs on-device instead of decoding the whole prefix per token."""

    def __init__(self, tokenizer: Any, input_length: int, device: Any, paragraphs: bool = True):
        self.input_length = input_length
        # False keeps only the interrupt check, for answers that are several lines long.
        self.paragraphs = paragraphs
        # Tokenizers can merge repeated newlines into one token. Include their encodings.
        ids = {
            token
            for count in range(2, 17)
            for token in tokenizer.encode("\n" * count, add_special_tokens=False)
            if "\n\n" in tokenizer.decode([token])
        }
        self.ids = torch.tensor(sorted(ids), device=device, dtype=torch.long)
        newline = tokenizer.encode("\n", add_special_tokens=False)
        self.newline_id = newline[0] if len(newline) == 1 else -1

    def __call__(self, input_ids, scores, **kwargs):
        mm.throw_exception_if_processing_interrupted()
        if not self.paragraphs:
            return torch.zeros(input_ids.shape[0], dtype=torch.bool, device=input_ids.device)
        last = input_ids[:, -1:]
        done = (last == self.ids).any(dim=-1)
        if input_ids.shape[1] >= self.input_length + 2:
            done = done | (input_ids[:, -2:] == self.newline_id).all(dim=-1)
        return done


def pil_image(image: torch.Tensor) -> Image.Image:
    if (
        not isinstance(image, torch.Tensor)
        or image.ndim != 4
        or image.shape[0] != 1
        or image.shape[-1] != 3
        or min(image.shape[1:3]) < 1
        or image.shape[1] * image.shape[2] > 16_777_216
    ):
        raise ValueError("Connect one RGB IMAGE up to 16 megapixels; split batches before upscaling")
    value = image[0].detach()
    if not torch.isfinite(value).all():
        raise ValueError("IMAGE contains non-finite pixels")
    if max(value.shape[:2]) > 2048:
        ratio = 2048 / max(value.shape[:2])
        value = torch.nn.functional.interpolate(
            value.permute(2, 0, 1).unsqueeze(0),
            size=(max(1, round(value.shape[0] * ratio)), max(1, round(value.shape[1] * ratio))),
            mode="bilinear",
            align_corners=False,
        )[0].permute(1, 2, 0)
    return Image.fromarray((value.cpu().clamp(0, 1).float().numpy() * 255).round().astype("uint8"))


def _generate(owner, processor, request, picture, budget, slices, detail_mode, *, reference=False, prefix=""):
    started = time.perf_counter()
    text = processor.apply_chat_template(
        messages(request, picture is not None, detail_mode, reference),
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    text += prefix
    inputs = processor(
        text=[text],
        return_tensors="pt",
        **({"images": [picture], "max_slice_nums": slices} if picture is not None else {}),
    )
    input_length = inputs["input_ids"].shape[1]
    if input_length > 4096:
        raise ValueError(
            "Prepared input exceeds the fast path's 4,096-token limit; shorten the text or reduce slices"
        )
    inputs = inputs.to(owner.load_device, dtype=torch.bfloat16)
    prepared = time.perf_counter()
    with torch.inference_mode():
        tokens = owner.model.generate(
            **inputs,
            do_sample=False,
            max_new_tokens=budget,
            use_cache=True,
            pad_token_id=processor.tokenizer.eos_token_id,
            stopping_criteria=StoppingCriteriaList(
                [ParagraphComplete(processor.tokenizer, input_length, owner.load_device)]
            ),
        )[0, input_length:].cpu()
    generated = time.perf_counter()
    continuation = processor.tokenizer.decode(tokens, skip_special_tokens=True).lstrip()
    raw = prefix + continuation
    eos = owner.model.network.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos or []
    truncated = len(tokens) >= budget and int(tokens[-1]) not in eos and "\n\n" not in continuation
    return (
        raw,
        truncated,
        {
            "added_words": len(continuation.split()) if prefix else None,
            "input_tokens": input_length,
            "generated_tokens": len(tokens),
            "prepare_seconds": prepared - started,
            "generate_seconds": generated - prepared,
        },
    )


def lfm3_engine(upscaler):
    """The handle's graph decode engine, or None when CUDA graphs are unavailable."""
    if upscaler.model_family != "lfm3_vl" or not torch.cuda.is_available() or mm.args.disable_cuda_graphs:
        return None
    if torch.device(upscaler.owner.load_device).type != "cuda":
        return None
    from .lfm3.engine import engine_for

    return engine_for(upscaler)


def _paragraph_stop(tokenizer):
    """Host-side twin of ParagraphComplete for the engine: cut after a blank line."""
    ids = {
        token
        for count in range(2, 17)
        for token in tokenizer.encode("\n" * count, add_special_tokens=False)
        if "\n\n" in tokenizer.decode([token])
    }
    newline = tokenizer.encode("\n", add_special_tokens=False)
    newline = newline[0] if len(newline) == 1 else -1

    def stop(tokens):
        for index, token in enumerate(tokens):
            if index == 0:
                continue  # ParagraphComplete never stops on the first generated token
            if token in ids or (index >= 1 and token == newline and tokens[index - 1] == newline):
                return index + 1
        return None

    return stop


def _engine_generate(engine, owner, processor, inputs, budget, sampling, seed, paragraphs):
    from .lfm3.engine import Sampling

    eos = owner.model.network.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else list(eos or [])
    settings = Sampling(seed=int(seed))
    if sampling and sampling.get("do_sample", True) and "temperature" in sampling:
        settings = Sampling(
            temperature=float(sampling["temperature"]), top_p=float(sampling.get("top_p", 1.0)),
            top_k=int(sampling.get("top_k", 0)), min_p=float(sampling.get("min_p", 0.0)),
            repetition_penalty=float(sampling.get("repetition_penalty", 1.0)), seed=int(seed),
        )
    stop_fn = _paragraph_stop(processor.tokenizer) if paragraphs else None
    import comfy.utils

    bar = comfy.utils.ProgressBar(budget)  # live token count for the UI (one message per check window)
    tokens, stopped, info = engine.generate(inputs, budget, eos, settings, stop_fn=stop_fn,
                                            on_tokens=lambda count: bar.update_absolute(count, budget))
    raw = processor.tokenizer.decode(tokens, skip_special_tokens=True).strip()
    return raw, not stopped and len(tokens) >= budget, info


def _generate_lfm3(
    owner, processor, chat, picture, budget, slices, *, sampling=None, seed=0, paragraphs=True, engine=None
):
    """Greedy by default; ``sampling`` (temperature/top_p/min_p) samples reproducibly from ``seed``.

    With ``engine`` the decode runs as one CUDA graph per token (about 3x faster on this model);
    runs with a ``sequence_bias`` keep the transformers loop, which applies multi-token biases.
    """
    started = time.perf_counter()
    mm.throw_exception_if_processing_interrupted()
    text = processor.apply_chat_template(
        chat, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )
    image_kwargs = (
        {
            "images": [picture],
            "images_kwargs": {"size": {"shortest_edge": 65536, "longest_edge": 512 * 512 * slices}},
        }
        if picture is not None
        else {}
    )
    inputs = processor(text=[text], return_tensors="pt", **image_kwargs)
    input_length = inputs["input_ids"].shape[1]
    if input_length + budget > owner.model.network.config.text_config.max_position_embeddings:
        raise ValueError("Input and output budget exceed the LFM3 context window")
    prepared = time.perf_counter()
    mm.load_models_gpu([owner], memory_required=640 * 1024**2, force_full_load=True)
    inputs = inputs.to(owner.load_device, dtype=torch.bfloat16)
    placed = time.perf_counter()
    if engine is not None and not (sampling and sampling.get("sequence_bias")):
        raw, truncated, info = _engine_generate(engine, owner, processor, inputs, budget, sampling, seed, paragraphs)
        return raw, truncated, {
            "input_tokens": input_length,
            "generated_tokens": info["generated_tokens"],
            "prepare_seconds": prepared - started,
            "placement_seconds": placed - prepared,
            "generate_seconds": time.perf_counter() - placed,
            "engine": info["engine"],
            "tokens_per_second": info["tokens_per_second"],
        }
    if sampling:
        torch.manual_seed(int(seed) & 0xFFFFFFFFFFFFFFFF)
    tokens = owner.model.generate(
        **inputs,
        **({"do_sample": True, **sampling} if sampling else {"do_sample": False}),
        max_new_tokens=budget,
        use_cache=True,
        pad_token_id=processor.tokenizer.pad_token_id,
        stopping_criteria=StoppingCriteriaList(
            [ParagraphComplete(processor.tokenizer, input_length, owner.load_device, paragraphs)]
        ),
    )[0, input_length:].cpu()
    generated = time.perf_counter()
    raw = processor.tokenizer.decode(tokens, skip_special_tokens=True).strip()
    eos = owner.model.network.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos or []
    truncated = len(tokens) >= budget and int(tokens[-1]) not in eos and "\n\n" not in raw
    return (
        raw,
        truncated,
        {
            "input_tokens": input_length,
            "generated_tokens": len(tokens),
            "prepare_seconds": prepared - started,
            "placement_seconds": placed - prepared,
            "generate_seconds": generated - placed,
        },
    )


def _fidelity_issues(diagnostics):
    return {
        (key, value)
        for key in (
            "missing_quoted_text",
            "unexpected_quoted_text",
            "missing_relation_details",
            "style_terms",
        )
        for value in diagnostics.get(key, [])
    } | {(key, value) for key, values in diagnostics["missing_lexical_cues"].items() for value in values}


def upscale_lfm3(upscaler, prompt, image, budget, slices, offload_after, detail_mode, target_model):
    started = time.perf_counter()
    prompt = validate_request(prompt, image is not None, budget, slices, detail_mode)
    if type(offload_after) is not bool:
        raise ValueError("offload_after must be a boolean")
    picture = pil_image(image) if image is not None else None
    chat = lfm_prompts.messages(prompt, picture is not None, target_model, detail_mode)
    while not upscaler.lock.acquire(timeout=0.1):
        mm.throw_exception_if_processing_interrupted()
    try:
        mm.throw_exception_if_processing_interrupted()
        owner, processor = upscaler.owner, upscaler.processor
        engine = lfm3_engine(upscaler)
        passes = []
        reference = None
        grounding_warnings = []
        if picture is not None and prompt.strip():
            grounding = lfm_prompts.messages("", True, target_model, "faithful")
            observed, cut, timing = _generate_lfm3(
                owner, processor, grounding, picture, min(budget, 128), slices, engine=engine
            )
            reference, grounding_warnings, _ = lfm_prompts.inspect_output(
                observed, "", cut, target_model, allow_reference_text=True
            )
            passes.append({"stage": "grounding", **timing})
            chat = lfm_prompts.messages(
                lfm_prompts.reference_request(reference, prompt), False, target_model, "faithful"
            )
        raw, truncated, timing = _generate_lfm3(
            owner, processor, chat, None if reference else picture, budget, slices, engine=engine
        )
        passes.append({"stage": "rewrite", **timing})
        raw, removed_style_clauses = lfm_prompts.remove_style_clauses(raw)
        raw, restored_exclusions = lfm_prompts.restore_exclusions(raw, prompt)
        result, warnings, fidelity = lfm_prompts.inspect_output(
            raw, prompt, truncated, target_model, allow_reference_text=picture is not None
        )
        initial_fidelity = fidelity
        repair_accepted = None
        if (
            fidelity["missing_quoted_text"]
            or fidelity["unexpected_quoted_text"]
            or fidelity.get("style_terms")
            or fidelity["missing_relation_details"]
            or any(fidelity["missing_lexical_cues"].values())
        ):
            repair_source = lfm_prompts.reference_request(reference, prompt) if reference else prompt
            correction = lfm_prompts.messages(
                lfm_prompts.repair_request(repair_source, result, fidelity), False, target_model, "faithful"
            )
            raw, repaired_truncated, timing = _generate_lfm3(
                owner, processor, correction, None, budget, slices, engine=engine
            )
            passes.append({"stage": "repair", **timing})
            raw, repaired_style_clauses = lfm_prompts.remove_style_clauses(raw)
            raw, repaired_exclusions = lfm_prompts.restore_exclusions(raw, prompt)
            repaired, repaired_warnings, repaired_fidelity = lfm_prompts.inspect_output(
                raw, prompt, repaired_truncated, target_model, allow_reference_text=picture is not None
            )
            # Keep the first draft when a repair loses a previously satisfied check.
            repair_accepted = _fidelity_issues(repaired_fidelity) < _fidelity_issues(fidelity) and not (
                repaired_truncated and not truncated
            )
            if repair_accepted:
                result, warnings, fidelity = repaired, repaired_warnings, repaired_fidelity
                restored_exclusions = repaired_exclusions
                removed_style_clauses = repaired_style_clauses
        warnings = grounding_warnings + warnings
        inspection = {
            "schema_version": 2,
            "contract": lfm_prompts.CONTRACT_VERSION,
            "input_prompt": prompt,
            "model_family": "lfm3_vl",
            "target_model": target_model,
            "model": upscaler.identity[0].rsplit("/", 1)[-1],
            "artifact": {"bytes": upscaler.identity[1], "mtime_ns": upscaler.identity[2]},
            "mode": "text+image" if prompt and picture else "image" if picture else "text",
            "authoring": "complete_rewrite",
            "fidelity": fidelity,
            "initial_fidelity": initial_fidelity,
            "repair_accepted": repair_accepted,
            "restored_exclusions": restored_exclusions,
            "removed_style_clauses": removed_style_clauses,
            "passes": passes,
            "reference_content": reference,
            "image_sha256": hashlib.sha256(picture.tobytes()).hexdigest() if picture else None,
            "settings": {
                "detail_mode": detail_mode,
                "max_new_tokens": budget,
                "image_max_pixels": 512 * 512 * slices if picture else None,
                "offload_after": offload_after,
                "sampling": "greedy",
                "thinking": False,
            },
            "input_tokens": sum(p["input_tokens"] for p in passes),
            "generated_tokens": sum(p["generated_tokens"] for p in passes),
            "native_int8_layers": upscaler.native_int8_layers,
            "seconds": {
                "model_load": upscaler.load_seconds,
                "prepare": sum(p["prepare_seconds"] for p in passes),
                "placement": sum(p["placement_seconds"] for p in passes),
                "generate": sum(p["generate_seconds"] for p in passes),
                "total": time.perf_counter() - started,
            },
            "warnings": warnings,
            "base_prompt": result,
        }
        return result, json.dumps(inspection, ensure_ascii=False, sort_keys=True, indent=2)
    finally:
        try:
            if offload_after or sys.exc_info()[0] is not None:
                mm.unload_model_and_clones(upscaler.owner)
        finally:
            upscaler.lock.release()


def upscale(
    upscaler: UpscalerHandle,
    prompt: str = "",
    image: torch.Tensor | None = None,
    max_new_tokens: int = 192,
    image_slices: int = 1,
    offload_after: bool = False,
    detail_mode: str = "expanded",
    target_model: str = "moss_image_base",
) -> tuple[str, str]:
    _refuse_upsampler(upscaler)
    if isinstance(upscaler, UpscalerHandle) and upscaler.model_family == "lfm3_vl":
        return upscale_lfm3(
            upscaler, prompt, image, max_new_tokens, image_slices, offload_after, detail_mode, target_model
        )
    started = time.perf_counter()
    prompt = validate_request(prompt, image is not None, max_new_tokens, image_slices, detail_mode)
    if type(offload_after) is not bool:
        raise ValueError("offload_after must be a boolean")
    if not isinstance(upscaler, UpscalerHandle):
        raise ValueError("Connect PromptStyler Next: Load Prompt Upscaler")
    picture = pil_image(image) if image is not None else None
    while not upscaler.lock.acquire(timeout=0.1):
        mm.throw_exception_if_processing_interrupted()
    try:
        mm.throw_exception_if_processing_interrupted()
        owner, processor = upscaler.owner, upscaler.processor
        placing = time.perf_counter()
        mm.load_models_gpu([owner], memory_required=640 * 1024**2, force_full_load=True)
        placement_seconds = time.perf_counter() - placing
        # Ground the image independently first: small VLMs otherwise ignored text changes
        # or moved unrelated objects in the combined-input evaluation. No extra model load.
        prefix = expansion_prefix(prompt) if picture is None and detail_mode == "expanded" else ""
        raw, truncated, first = _generate(
            owner,
            processor,
            user_request(prompt, picture is not None, detail_mode),
            picture,
            min(max_new_tokens, 128) if picture and prompt else max_new_tokens,
            image_slices,
            "faithful" if picture and prompt else detail_mode,
            prefix=prefix,
        )
        passes = [first]
        reference = None
        if picture is not None and prompt:
            reference, grounding_warnings = clean_output(raw, "", truncated)
            raw, truncated, second = _generate(
                owner,
                processor,
                merge_request(reference, prompt),
                None,
                max_new_tokens,
                image_slices,
                detail_mode,
                reference=True,
            )
            passes.append(second)
        else:
            grounding_warnings = []
        result, warnings = clean_output(raw, prompt, truncated)
        warnings = grounding_warnings + warnings
        if prefix and len(prompt.split()) <= 20 and first["added_words"] < 12:
            warnings.append("Little scene detail was added; inspect the result or increase the output budget")
        inspection = {
            "schema_version": 1,
            "contract": CONTRACT_VERSION,
            "input_prompt": prompt,
            "source_preserved": bool(prefix),
            "added_words": first["added_words"],
            "image_sha256": hashlib.sha256(picture.tobytes()).hexdigest() if picture else None,
            "model": upscaler.identity[0].rsplit("/", 1)[-1],
            "artifact": {"bytes": upscaler.identity[1], "mtime_ns": upscaler.identity[2]},
            "mode": "text+image" if prompt and picture else "image" if picture else "text",
            "settings": {
                "detail_mode": detail_mode,
                "max_new_tokens": max_new_tokens,
                "image_slices": image_slices,
                "offload_after": offload_after,
                "sampling": "greedy",
                "thinking": False,
            },
            "input_tokens": sum(item["input_tokens"] for item in passes),
            "generated_tokens": sum(item["generated_tokens"] for item in passes),
            "passes": passes,
            "reference_content": reference,
            "native_int8_layers": upscaler.native_int8_layers,
            "seconds": {
                "model_load": upscaler.load_seconds,
                "prepare": sum(item["prepare_seconds"] for item in passes),
                "placement": placement_seconds,
                "generate": sum(item["generate_seconds"] for item in passes),
                "total": time.perf_counter() - started,
            },
            "warnings": warnings,
            "base_prompt": result,
        }
        logger.info(
            "PromptStyler upscaled %s input: %d tokens in %.3fs",
            inspection["mode"],
            inspection["generated_tokens"],
            inspection["seconds"]["generate"],
        )
        return result, json.dumps(inspection, ensure_ascii=False, sort_keys=True, indent=2)
    finally:
        # Cached handles remain owned by ComfyUI, which can offload them for diffusion.
        try:
            if offload_after or sys.exc_info()[0] is not None:
                mm.unload_model_and_clones(upscaler.owner)
        finally:
            upscaler.lock.release()


def _idea_sampling(temperature: float, bias: list | None = None) -> dict:
    # min_p keeps high temperatures coherent on a small model; 0 means greedy.
    settings = (
        {"temperature": float(temperature), "top_p": 0.95, "min_p": 0.05}
        if temperature > 0
        else {"do_sample": False}
    )
    return {**settings, **({"sequence_bias": bias} if bias else {})}


def _word_bias(tokenizer, words: list[str], strength: float) -> list:
    """Soft penalties (not bans) for whole words, in lower and capitalised forms after a space."""
    seen, bias = set(), []
    for word in words:
        for form in (" " + word, " " + word.capitalize()):
            ids = tuple(tokenizer.encode(form, add_special_tokens=False))
            if ids and ids not in seen:
                seen.add(ids)
                bias.append([list(ids), strength])
    return bias


def ideate(
    upscaler: UpscalerHandle,
    prompt: str,
    exploration: str = "explore",
    detail: str = "balanced",
    target_model: str = "general",
    lens: str = "auto",
    structure: str = "auto",
    seed: int = 0,
    temperature: float = 0.85,
    avoid: str = "",
    recent: str = "",
    max_new_tokens: int = 0,
    earlier: str = "",
    style_mode: str = "open",
    style: str = "",
    style_axes: str = "",
) -> tuple[str, str]:
    """A new prompt idea from a draft: seeded lens/structure, brainstorm, novelty pick, develop, check.

    ``avoid`` lists earlier concepts (novelty and brainstorm); ``earlier`` lists earlier full prompts, whose
    recurring wording is penalised during decoding so each idea is described in fresh words too.
    ``style_mode`` neutral/match keeps the look out of the idea (see ``idea_prompts.style_context``).
    """
    started = time.perf_counter()
    look = idea_prompts.style_context(style_mode, style, style_axes)
    draft = idea_prompts.validate(
        prompt,
        exploration,
        detail,
        target_model,
        lens,
        structure,
        temperature,
        avoid,
        recent,
        max_new_tokens,
        earlier,
    )
    _refuse_upsampler(upscaler)
    if not isinstance(upscaler, UpscalerHandle) or upscaler.model_family != "lfm3_vl":
        raise ValueError("Prompt ideas need the LFM3-VL model; select an lfm3 file in Load Prompt Upscaler")
    earlier_ideas = idea_prompts.avoid_list(avoid)
    chosen = idea_prompts.plan(seed, exploration, detail, lens, structure, recent, look)
    budget = idea_prompts.token_budget(detail, draft, max_new_tokens)
    while not upscaler.lock.acquire(timeout=0.1):
        mm.throw_exception_if_processing_interrupted()
    try:
        owner, processor = upscaler.owner, upscaler.processor
        engine = lfm3_engine(upscaler)
        # Near-ban the model's stock adjectives; gently steer away from words earlier ideas kept reusing.
        penalised = idea_prompts.bias_words(idea_prompts.avoid_list(earlier) or earlier_ideas, draft)
        bias = _word_bias(processor.tokenizer, list(idea_prompts.OVERUSED), -6.0) + _word_bias(
            processor.tokenizer, penalised, -1.5
        )
        if look["mode"] != "open":
            # Look words are steered away from softly; the draft's own words stay free to use.
            own = idea_prompts.content_words(draft)
            look_words = [word for word in idea_prompts.STYLE_WORDS if idea_prompts.stem(word) not in own]
            bias += _word_bias(processor.tokenizer, look_words, -2.5)
        passes = []
        # Brainstorming is sampled hotter than the final prompt so the candidates really differ.
        raw, _, timing = _generate_lfm3(
            owner,
            processor,
            idea_prompts.brainstorm_messages(draft, exploration, chosen, earlier_ideas),
            None,
            40 * chosen["concepts"] + 40,
            1,
            sampling=_idea_sampling(min(1.5, temperature + 0.2) if temperature else 0, bias),
            seed=seed,
            engine=engine,
            paragraphs=False,
        )
        passes.append({"stage": "brainstorm", **timing})
        concepts = idea_prompts.parse_concepts(raw)
        ranked = idea_prompts.rank_concepts(concepts, earlier_ideas, draft, exploration, chosen["rng_state"])
        attempts = []
        for attempt in range(2):
            concept, concept_novelty = (
                ranked[attempt] if attempt < len(ranked) else (ranked[0] if ranked else ("", 1.0))
            )
            raw, truncated, timing = _generate_lfm3(
                owner,
                processor,
                idea_prompts.develop_messages(draft, exploration, detail, target_model, chosen, concept),
                None,
                budget,
                1,
                sampling=_idea_sampling(temperature, bias),
                seed=seed + 1 + attempt * 7919,
                engine=engine,
            )
            passes.append({"stage": "develop" if not attempt else "retry", **timing})
            try:
                text, warnings = idea_prompts.clean_idea(raw, truncated)
            except RuntimeError as error:
                attempts.append(
                    {"text": "", "warnings": [str(error)], "quality": {"issues": ["control"], "novelty": 0}}
                )
                continue
            text, removed_look = idea_prompts.scrub_style(text, draft, look, find_prose)
            text, restored_exclusions = lfm_prompts.restore_exclusions(text, draft)
            text, restored_quotes = idea_prompts.restore_quotes(text, draft)
            quality = idea_prompts.assess(text, draft, exploration, detail, earlier_ideas)
            attempts.append(
                {
                    "text": text,
                    "warnings": warnings,
                    "quality": quality,
                    "concept": concept,
                    "concept_novelty": concept_novelty,
                    "restored_exclusions": restored_exclusions,
                    "restored_quotes": restored_quotes,
                    "removed_look": removed_look,
                }
            )
            # A retry develops the next-ranked concept with a new sample.
            if not quality["issues"]:
                break
        usable = [item for item in attempts if item["text"]]
        if not usable:
            raise RuntimeError("The prompt model returned no usable idea; try again")
        best = min(usable, key=lambda item: (len(item["quality"]["issues"]), -item["quality"]["novelty"]))
        warnings = list(best["warnings"])
        labels = {
            "too_short": "The idea came out short",
            "lost_subject": "The idea may have drifted from your subject",
            "echo": "The idea stayed close to your draft",
            "repeat": "The idea resembles an earlier one",
        }
        warnings += [labels[issue] for issue in best["quality"]["issues"] if issue in labels]
        if best["quality"].get("invented_text"):
            warnings.append(
                "The idea added readable text you did not ask for: "
                + ", ".join(best["quality"]["invented_text"])
            )
        inspection = {
            "schema_version": 2,
            "contract": idea_prompts.CONTRACT_VERSION,
            "input_prompt": draft,
            "model_family": "lfm3_vl",
            "model": upscaler.identity[0].rsplit("/", 1)[-1],
            "mode": "idea",
            "authoring": "idea",
            "idea": {
                "exploration": exploration,
                "lenses": [{"key": item.key, "label": item.label} for item in chosen["lenses"]],
                "structure": {"key": chosen["structure"].key, "label": chosen["structure"].label},
                "sparks": chosen["sparks"],
                "concepts": concepts,
                "concept": best["concept"],
                "concept_novelty": best["concept_novelty"],
                "style": {
                    "mode": look["mode"],
                    "axes": sorted(look["axes"]),
                    "removed": best["removed_look"],
                },
            },
            "quality": best["quality"],
            "attempts": len(attempts),
            "attempt_issues": [item["quality"]["issues"] for item in attempts],
            "penalised_words": penalised,
            "restored_exclusions": best["restored_exclusions"],
            "restored_quotes": best["restored_quotes"],
            "settings": {
                "detail": detail,
                "target_model": target_model,
                "max_new_tokens": budget,
                "seed": seed,
                "temperature": temperature,
                "sampling": {key: value for key, value in _idea_sampling(temperature).items()},
                "thinking": False,
            },
            "passes": passes,
            "generated_tokens": sum(item["generated_tokens"] for item in passes),
            "seconds": {
                "model_load": upscaler.load_seconds,
                "generate": sum(item["generate_seconds"] for item in passes),
                "total": time.perf_counter() - started,
            },
            "warnings": warnings,
            "base_prompt": best["text"],
        }
        logger.info(
            "PromptStyler idea (%s, %s): %d tokens in %.3fs",
            exploration,
            chosen["structure"].key,
            inspection["generated_tokens"],
            inspection["seconds"]["generate"],
        )
        return best["text"], json.dumps(inspection, ensure_ascii=False, sort_keys=True, indent=2)
    finally:
        try:
            if sys.exc_info()[0] is not None:
                mm.unload_model_and_clones(upscaler.owner)
        finally:
            upscaler.lock.release()


def _refuse_upsampler(upscaler) -> None:
    if isinstance(upscaler, UpscalerHandle) and upscaler.model_family == moss_upsampler.FAMILY:
        raise ValueError(
            "This is the MOSS prompt upsampler; connect it to PromptStyler Next: MOSS Prompt Upsampler"
        )


def upsample_moss(
    upscaler: UpscalerHandle,
    prompt: str,
    seed: int = 0,
    temperature: float = moss_upsampler.DEFAULT_SAMPLING["temperature"],
    top_p: float = moss_upsampler.DEFAULT_SAMPLING["top_p"],
    top_k: int = moss_upsampler.DEFAULT_SAMPLING["top_k"],
    min_p: float = moss_upsampler.DEFAULT_SAMPLING["min_p"],
    presence_penalty: float = moss_upsampler.DEFAULT_SAMPLING["presence_penalty"],
    max_new_tokens: int = moss_upsampler.DEFAULT_MAX_NEW_TOKENS,
    offload_after: bool = False,
    style: str = "",
    repetition_penalty: float = moss_upsampler.DEFAULT_REPETITION_PENALTY,
    guard: bool = True,
    max_takes: int = 1,
) -> tuple[str, str]:
    """Expand a draft with the MOSS fine-tune: its SFT system prompt, thinking off, seeded sampling."""
    if not isinstance(upscaler, UpscalerHandle) or upscaler.model_family != moss_upsampler.FAMILY:
        raise ValueError("Select the moss-qwen3.5 upsampler file in Load Prompt Upscaler")
    if type(offload_after) is not bool or type(guard) is not bool:
        raise ValueError("offload_after and guard must be booleans")
    moss_upsampler.validate_prompt(prompt)
    while not upscaler.lock.acquire(timeout=0.1):
        mm.throw_exception_if_processing_interrupted()
    try:
        mm.throw_exception_if_processing_interrupted()
        text, inspection = moss_upsampler.upsample(
            upscaler.owner,
            prompt,
            seed=seed,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            presence_penalty=presence_penalty,
            repetition_penalty=repetition_penalty,
            max_new_tokens=max_new_tokens,
            style=style,
            guard=guard,
            max_takes=max_takes,
            speculative=upscaler.speculative,
        )
        inspection["native_int8_layers"] = upscaler.native_int8_layers
        inspection["model_load_seconds"] = round(upscaler.load_seconds, 2)
        inspection["base_prompt"] = text
        logger.info(
            "PromptStyler MOSS upsampler: %d tokens in %.2fs (%d take(s), guard: %s)",
            inspection["upsample"]["output_tokens"],
            inspection["upsample"]["seconds"],
            len(inspection["guard"]["takes"]),
            "; ".join(inspection["guard"]["report"]) or ("clean" if guard else "off"),
        )
        return text, json.dumps(inspection, ensure_ascii=False, sort_keys=True, indent=2)
    finally:
        try:
            if offload_after or sys.exc_info()[0] is not None:
                mm.unload_model_and_clones(upscaler.owner.patcher)
        finally:
            upscaler.lock.release()


def layout_assist(upscaler, task, image=None, request="", layout="", objects=None, words=None, seed=0,
                  temperature=0.0, scene="", lettering=True):
    """One LFM3 layout task. Returns (layout JSON, detector labels, inspection JSON, image has lettering).

    The task logic (regions, prompts, parsing) is ``layout_assist.prepare``/``finish``; this runs the model.
    ``scene`` is a list_objects answer (its layout output): its background nouns join the describe step's
    list of things without a box."""
    from . import layout_assist as assist

    if not isinstance(upscaler, UpscalerHandle) or upscaler.model_family != "lfm3_vl":
        raise ValueError("Select the LFM3-VL file in Load Prompt Upscaler")
    picture = pil_image(image) if image is not None else None
    job = assist.prepare(task, request=request, layout=layout, objects=objects, words=words,
                         image_size=picture.size if picture is not None else None, scene=scene, lettering=lettering)
    task, regions, background = job["task"], job["regions"], job["background"]
    use_picture = picture if job["use_image"] else None
    sampling = {"temperature": float(temperature), "top_p": 0.9, "top_k": 40} if temperature > 0 else None
    while not upscaler.lock.acquire(timeout=0.1):
        mm.throw_exception_if_processing_interrupted()
    try:
        mm.throw_exception_if_processing_interrupted()
        engine = lfm3_engine(upscaler)
        raw, truncated, timing = _generate_lfm3(
            upscaler.owner, upscaler.processor, job["messages"], use_picture, job["budget"], 1, sampling=sampling,
            seed=seed, paragraphs=False, engine=engine,
        )
    finally:
        upscaler.lock.release()
    try:
        result, labels = assist.finish(job, raw)
    except (ValueError, json.JSONDecodeError) as error:
        logging.warning("Layout Assist: unreadable %s answer (%s): %s", task, error, raw[:800])
        raise ValueError(f"LFM3 wrote an unreadable layout ({error}). Try again or reword the request.") from error
    if task == "list_objects" and result.get("warnings"):
        logging.warning("Layout Assist: unreadable list answer: %s", raw[:800])
    if truncated:
        result.setdefault("warnings", []).append("The answer hit its length budget; the last part may be missing.")
    lettering = result.get("lettering", True) is not False
    inspection = {"task": task, "regions": len(regions), "truncated": truncated, **timing,
                  **({"background": background} if background else {}), "raw": raw[:4000]}
    return json.dumps(result, ensure_ascii=False), labels, json.dumps(inspection, ensure_ascii=False), lettering
