"""ComfyUI V3 entry point, loaded without importing host dependencies eagerly."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from comfy_api.latest import ComfyExtension

WEB_DIRECTORY = "./web"


async def comfy_entrypoint() -> ComfyExtension:
    from .comfyui import comfy_entrypoint as entrypoint

    return await entrypoint()
