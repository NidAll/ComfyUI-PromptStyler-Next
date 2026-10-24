"""ComfyUI owns model loading, tokenization, scheduling, and conditioning."""

from comfy_api.latest import ComfyExtension, io

from .nodes import PSNextCompose, PSNextEncode, PSNextStyle
from .upscaler_nodes import PSNextLoadUpscaler, PSNextUpscaleBase


class PromptStylerNextExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [PSNextStyle, PSNextCompose, PSNextEncode, PSNextLoadUpscaler, PSNextUpscaleBase]


async def comfy_entrypoint() -> PromptStylerNextExtension:
    return PromptStylerNextExtension()
