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

from . import lfm_prompts
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


def load_upscaler(model_name: str) -> UpscalerHandle:
    started = time.perf_counter()
    identity = bundle_fingerprint(model_name)
    path = resolve_bundle(model_name)
    from safetensors import safe_open

    with safe_open(path, framework="pt", device="cpu") as reader:
        family = "lfm3_vl" if "lfm3_vl" in (reader.metadata() or {}) else "minicpm"
    if family == "lfm3_vl":
        from .lfm3 import load_lfm3

        owner, processor, coverage = load_lfm3(path)
    else:
        from .loading import load_minicpm

        owner, processor, coverage = load_minicpm(path)
    if identity != bundle_fingerprint(model_name):
        raise RuntimeError("Upscaler file changed during loading; queue the workflow again")
    return UpscalerHandle(
        owner, processor, coverage, identity, time.perf_counter() - started, model_family=family
    )


class ParagraphComplete(StoppingCriteria):
    """Match a few token IDs on-device instead of decoding the whole prefix per token."""

    def __init__(self, tokenizer: Any, input_length: int, device: Any):
        self.input_length = input_length
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


def _generate_lfm3(owner, processor, chat, picture, budget, slices):
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
    tokens = owner.model.generate(
        **inputs,
        do_sample=False,
        max_new_tokens=budget,
        use_cache=True,
        pad_token_id=processor.tokenizer.pad_token_id,
        stopping_criteria=StoppingCriteriaList(
            [ParagraphComplete(processor.tokenizer, input_length, owner.load_device)]
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
        passes = []
        reference = None
        grounding_warnings = []
        if picture is not None and prompt.strip():
            grounding = lfm_prompts.messages("", True, target_model, "faithful")
            observed, cut, timing = _generate_lfm3(
                owner, processor, grounding, picture, min(budget, 128), slices
            )
            reference, grounding_warnings, _ = lfm_prompts.inspect_output(
                observed, "", cut, target_model, allow_reference_text=True
            )
            passes.append({"stage": "grounding", **timing})
            chat = lfm_prompts.messages(
                lfm_prompts.reference_request(reference, prompt), False, target_model, "faithful"
            )
        raw, truncated, timing = _generate_lfm3(
            owner, processor, chat, None if reference else picture, budget, slices
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
                owner, processor, correction, None, budget, slices
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
