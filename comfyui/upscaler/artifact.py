"""Read bounded data assets from the existing self-contained MiniCPM deployment."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

ASSET_KEY = "__anima_prompt_architect_assets__"
FILES = frozenset(
    (
        "config.json",
        "processor_config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "chat_template.jinja",
        "generation_config.json",
    )
)


def unpack_assets(payload: bytes, digest: str) -> dict[str, str]:
    if len(payload) > 32 * 1024**2 or hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("Embedded MiniCPM assets failed integrity validation")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if (
                len(members) != len(FILES)
                or {item.filename for item in members} != FILES
                or sum(item.file_size for item in members) > 64 * 1024**2
            ):
                raise ValueError("Unexpected or oversized embedded MiniCPM assets")
            return {name: archive.read(name).decode("utf-8") for name in FILES}
    except (zipfile.BadZipFile, UnicodeError) as error:
        raise ValueError("Invalid embedded MiniCPM asset archive") from error


def read_assets(path: Path) -> dict[str, str]:
    from safetensors import safe_open

    with safe_open(path, framework="pt", device="cpu") as reader:
        manifest = json.loads((reader.metadata() or {}).get("anima_prompt_architect", "{}"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("version") != 1
            or manifest.get("kind") != "minicpm"
        ):
            raise ValueError("Select a self-contained MiniCPM INT8 ConvRot Prompt Architect artifact")
        asset = reader.get_slice(ASSET_KEY)
        shape = asset.get_shape()
        if asset.get_dtype() != "U8" or len(shape) != 1 or shape[0] > 32 * 1024**2:
            raise ValueError("Embedded MiniCPM asset tensor must be bounded uint8 data")
        payload = reader.get_tensor(ASSET_KEY).numpy().tobytes()
    return unpack_assets(payload, manifest.get("assets_sha256", ""))


def validate_config(config: dict) -> None:
    """Only the tested 1B architecture is accepted; no arbitrary AutoModel or remote code."""
    if not isinstance(config, dict):
        raise ValueError("Unsupported MiniCPM configuration")
    text = config.get("text_config", {})
    vision = config.get("vision_config", {})
    if not isinstance(text, dict) or not isinstance(vision, dict):
        raise ValueError("Unsupported MiniCPM subconfiguration")
    if (
        config.get("model_type") != "minicpmv4_7"
        or text.get("model_type") != "qwen3_5_text"
        or text.get("hidden_size") != 1024
        or text.get("num_hidden_layers") != 24
        or text.get("intermediate_size") != 3584
        or text.get("vocab_size") != 248094
        or vision.get("hidden_size") != 1152
        or vision.get("num_hidden_layers") != 27
        or vision.get("intermediate_size") != 4304
        or config.get("insert_layer_id") != 6
        or text.get("head_dim") != 256
        or text.get("num_attention_heads") != 8
        or text.get("num_key_value_heads") != 2
        or text.get("linear_key_head_dim") != 128
        or text.get("linear_value_head_dim") != 128
        or text.get("linear_num_key_heads") != 16
        or text.get("linear_num_value_heads") != 16
        or text.get("linear_conv_kernel_dim") != 4
        or text.get("layer_types") != (["linear_attention"] * 3 + ["full_attention"]) * 6
        or text.get("max_position_embeddings") != 262144
        or text.get("mtp_num_hidden_layers", 1) != 1
        or vision.get("num_attention_heads") != 16
        or vision.get("image_size") != 980
        or vision.get("patch_size") != 14
        or config.get("image_size") != 448
        or config.get("patch_size") != 14
        or config.get("merge_kernel_size") != [2, 2]
        or config.get("merger_times") != 1
    ):
        raise ValueError("Unsupported MiniCPM configuration; expected the packaged MiniCPM-V 4.7 1B")
