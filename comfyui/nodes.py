"""Thin V3 adapters over the shared deterministic engine."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from comfy_api.latest import io

from ..promptstyler_next import Engine
from ..promptstyler_next.types import Composition
from ..promptstyler_next.validation import parse_json

_CUSTOM_PACKS = Path(__file__).resolve().parents[1] / "custom_packs"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Load one immutable catalog per host process from administrator-owned files."""
    paths = sorted(_CUSTOM_PACKS.glob("*.json"))
    for path in paths:
        if path.is_symlink():
            raise ValueError(f"Custom pack {path.name!r} must be a regular JSON file, not a symlink")
    return Engine.builtin().with_packs(paths) if paths else Engine.builtin()


def _outputs(composition: Composition) -> io.NodeOutput:
    data = composition.to_dict()
    inspection = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    return io.NodeOutput(data["positive"], data["negative"], inspection)


class PSNextStyle(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        engine = get_engine()
        styles = []
        offset = 0
        while page := engine.list_styles(limit=1000, offset=offset):
            styles.extend(page)
            offset += len(page)
        return io.Schema(
            node_id="PSNextStyle",
            display_name="PromptStyler Next: Style",
            category="PromptStyler Next",
            description="Preserves your prompt and adds one curated style. Advanced inputs expose negative text and protected axes.",
            search_aliases=["style", "prompt", "promptstyler", "aesthetic"],
            inputs=[
                io.String.Input("prompt", multiline=True, dynamic_prompts=False),
                io.Combo.Input(
                    "style",
                    options=[style["id"] for style in styles],
                    extra_dict={"psnext_categories": {style["id"]: style["category"] for style in styles}},
                ),
                io.Combo.Input(
                    "model", options=[profile["id"] for profile in engine.profiles()], default="generic"
                ),
                io.Float.Input(
                    "intensity",
                    default=0.75,
                    min=0.0,
                    max=1.0,
                    step=0.05,
                    display_mode=io.NumberDisplay.slider,
                    tooltip="Activates curated detail tiers; zero bypasses the style. It is not a sampler weight.",
                ),
                io.String.Input(
                    "negative",
                    default="",
                    multiline=True,
                    advanced=True,
                    tooltip="Preserved in the recipe; emitted only for profiles supporting negative prompts.",
                ),
                io.MultiCombo.Input(
                    "locked_axes",
                    options=["medium", "lighting", "palette", "composition", "texture", "mood", "detail"],
                    default=[],
                    advanced=True,
                    tooltip="Skip style clauses on these axes to protect choices already in your prompt.",
                ),
            ],
            outputs=[
                io.String.Output("positive", display_name="positive"),
                io.String.Output("negative", display_name="negative"),
                io.String.Output("inspection", display_name="inspection"),
            ],
        )

    @classmethod
    def execute(
        cls,
        prompt: str,
        style: str,
        model: str = "generic",
        intensity: float = 0.75,
        negative: str = "",
        locked_axes: list[str] | None = None,
    ) -> io.NodeOutput:
        return _outputs(
            get_engine().compose(
                {
                    "schema_version": 1,
                    "prompt": prompt,
                    "negative": negative,
                    "model": model,
                    "styles": [{"id": style, "intensity": intensity}],
                    "locked_axes": locked_axes or [],
                }
            )
        )


class PSNextCompose(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PSNextCompose",
            display_name="PromptStyler Next: Compose Recipe",
            category="PromptStyler Next/advanced",
            description="Compose an ordered, reproducible style recipe. Conflict decisions and capability warnings are included in inspection.",
            inputs=[
                io.String.Input(
                    "recipe",
                    multiline=True,
                    dynamic_prompts=False,
                    default='{"schema_version":1,"prompt":"A quiet mountain village","model":"sdxl","styles":[]}',
                ),
                io.String.Input(
                    "prompt",
                    optional=True,
                    force_input=True,
                    advanced=True,
                    tooltip="Optional native text input overrides the recipe subject, for image-generated captions.",
                ),
            ],
            outputs=[
                io.String.Output("positive", display_name="positive"),
                io.String.Output("negative", display_name="negative"),
                io.String.Output("inspection", display_name="inspection"),
            ],
        )

    @classmethod
    def execute(cls, recipe: str, prompt: str | None = None) -> io.NodeOutput:
        value = parse_json(recipe)
        if prompt is not None and isinstance(value, dict):
            value = {**value, "prompt": prompt}
        return _outputs(get_engine().compose(value))


class NativeTextEncoder(Protocol):
    def tokenize(self, text: str) -> Any: ...
    def encode_from_tokens_scheduled(self, tokens: Any) -> Any: ...


class PSNextEncode(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        supported = [
            profile["id"] for profile in get_engine().profiles() if profile["conditioning"] == "clip"
        ]
        return io.Schema(
            node_id="PSNextEncode",
            display_name="PromptStyler Next: Encode Text",
            category="PromptStyler Next/conditioning",
            description="Uses the connected native encoder for compatible text-only profiles. Use model-native nodes for specialized workflows.",
            inputs=[
                io.Clip.Input("clip"),
                io.String.Input("positive", multiline=True, force_input=True),
                io.String.Input("negative", multiline=True, force_input=True),
                io.Combo.Input("model", options=supported, default="sdxl"),
            ],
            outputs=[
                io.Conditioning.Output("positive", display_name="positive"),
                io.Conditioning.Output("negative", display_name="negative"),
            ],
        )

    @classmethod
    def execute(cls, clip: NativeTextEncoder, positive: str, negative: str, model: str) -> io.NodeOutput:
        profile = next((profile for profile in get_engine().profiles() if profile["id"] == model), None)
        if profile is None or profile["conditioning"] != "clip":
            raise ValueError(
                f"Profile {model!r} requires its model-native text encoder. "
                "Connect PromptStyler Next string outputs to the workflow's native encoding node."
            )
        if negative and not profile["negative"]:
            raise ValueError(
                f"Profile {model!r} does not support negative prompts; leave negative text empty"
            )
        if clip is None:
            raise ValueError("Connect a native CLIP/text encoder loaded for the selected model")
        return io.NodeOutput(
            clip.encode_from_tokens_scheduled(clip.tokenize(positive)),
            clip.encode_from_tokens_scheduled(clip.tokenize(negative)),
        )
