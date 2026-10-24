"""Native-managed, serialized, greedy MiniCPM inference. No global tensor caches."""

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

from .models import bundle_fingerprint, resolve_bundle
from .prompts import CONTRACT_VERSION, clean_output, merge_request, messages, user_request, validate_request

logger = logging.getLogger(__name__)


@dataclass
class UpscalerHandle:
    owner: Any
    processor: Any
    native_int8_layers: int
    identity: tuple
    load_seconds: float
    lock: Any = field(default_factory=threading.Lock)


def load_upscaler(model_name: str) -> UpscalerHandle:
    from .loading import load_minicpm

    started = time.perf_counter()
    identity = bundle_fingerprint(model_name)
    path = resolve_bundle(model_name)
    owner, processor, coverage = load_minicpm(path)
    if identity != bundle_fingerprint(model_name):
        raise RuntimeError("MiniCPM file changed during loading; queue the workflow again")
    return UpscalerHandle(owner, processor, coverage, identity, time.perf_counter() - started)


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


def _generate(owner, processor, request, picture, budget, slices):
    started = time.perf_counter()
    text = processor.apply_chat_template(
        messages(request, picture is not None),
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
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
    raw = processor.tokenizer.decode(tokens, skip_special_tokens=True)
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
            "generate_seconds": generated - prepared,
        },
    )


def upscale(
    upscaler: UpscalerHandle,
    prompt: str = "",
    image: torch.Tensor | None = None,
    max_new_tokens: int = 128,
    image_slices: int = 1,
    offload_after: bool = False,
) -> tuple[str, str]:
    started = time.perf_counter()
    prompt = validate_request(prompt, image is not None, max_new_tokens, image_slices)
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
        raw, truncated, first = _generate(
            owner,
            processor,
            user_request("" if picture else prompt, picture is not None),
            picture,
            min(max_new_tokens, 128) if picture and prompt else max_new_tokens,
            image_slices,
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
            )
            passes.append(second)
        else:
            grounding_warnings = []
        result, warnings = clean_output(raw, prompt, truncated)
        warnings = grounding_warnings + warnings
        inspection = {
            "schema_version": 1,
            "contract": CONTRACT_VERSION,
            "input_prompt": prompt,
            "image_sha256": hashlib.sha256(picture.tobytes()).hexdigest() if picture else None,
            "model": upscaler.identity[0].rsplit("/", 1)[-1],
            "artifact": {"bytes": upscaler.identity[1], "mtime_ns": upscaler.identity[2]},
            "mode": "text+image" if prompt and picture else "image" if picture else "text",
            "settings": {
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
