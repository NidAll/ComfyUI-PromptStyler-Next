"""V3 nodes for the optional native MiniCPM base-prompt authoring stage."""

from comfy_api.latest import io

from .upscaler.models import DEFAULT_MODEL, bundle_fingerprint, model_choices
from .upscaler.prompts import CONTRACT_VERSION, DETAIL_MODES

UPSCALER = io.Custom("PSNEXT_UPSCALER")


class PSNextLoadUpscaler(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        choices = model_choices()
        return io.Schema(
            node_id="PSNextLoadUpscaler",
            display_name="PromptStyler Next: Load Prompt Upscaler",
            category="PromptStyler Next/upscaling",
            description="Load the local self-contained MiniCPM-V 4.7 1B INT8 model. ComfyUI caches this handle and manages its VRAM. Requires the native CUDA/Kitchen backend.",
            search_aliases=["minicpm", "vlm", "prompt", "upscale"],
            inputs=[
                io.Combo.Input(
                    "model_name",
                    options=choices,
                    default=DEFAULT_MODEL if DEFAULT_MODEL in choices else choices[0],
                )
            ],
            outputs=[UPSCALER.Output("upscaler")],
        )

    @classmethod
    def fingerprint_inputs(cls, model_name: str):
        return bundle_fingerprint(model_name)

    @classmethod
    def execute(cls, model_name: str) -> io.NodeOutput:
        try:
            from .upscaler.runtime import load_upscaler

            return io.NodeOutput(load_upscaler(model_name))
        except ImportError as error:
            raise RuntimeError(
                "Prompt Upscaler needs the documented host runtime; see docs/upscaler.md. The styling engine works independently."
            ) from error


class PSNextUpscaleBase(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PSNextUpscaleBase",
            display_name="PromptStyler Next: Upscale Base Prompt",
            category="PromptStyler Next/upscaling",
            description="Expand an idea with concrete scene detail, or use faithful mode to clarify without additions. Accepts text, one image, or both; aesthetic choices stay with Style or Compose Recipe. Review the output: a small VLM can misread or invent details.",
            search_aliases=["enhance", "expand", "caption", "vlm", "base prompt"],
            inputs=[
                UPSCALER.Input("upscaler"),
                io.String.Input("prompt", default="", multiline=True, dynamic_prompts=False),
                io.Image.Input("image", optional=True),
                io.Int.Input(
                    "max_new_tokens",
                    default=192,
                    min=32,
                    max=384,
                    advanced=True,
                    tooltip="Maximum output budget. Decoding stops at EOS or a blank paragraph; higher budgets can be slower.",
                ),
                io.Int.Input(
                    "image_slices",
                    default=1,
                    min=1,
                    max=4,
                    advanced=True,
                    tooltip="One slice is fastest. More slices help fine details and text, using more time and VRAM.",
                ),
                io.Boolean.Input(
                    "offload_after",
                    default=False,
                    advanced=True,
                    tooltip="Keep false for fastest repeated edits. ComfyUI can still offload automatically. True immediately releases this model's VRAM after each execution.",
                ),
                io.Combo.Input(
                    "detail_mode",
                    options=list(DETAIL_MODES),
                    default="expanded",
                    optional=True,
                    tooltip="Expanded preserves your scene text and adds physical detail about its subjects and actions. Faithful rewrites concisely with minimal additions. Images remain grounded in visible/reference content.",
                ),
            ],
            outputs=[io.String.Output("base_prompt"), io.String.Output("inspection")],
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return CONTRACT_VERSION

    @classmethod
    def execute(
        cls,
        upscaler,
        prompt="",
        image=None,
        max_new_tokens=192,
        image_slices=1,
        offload_after=False,
        detail_mode="expanded",
    ):
        from .upscaler.runtime import upscale

        return io.NodeOutput(
            *upscale(upscaler, prompt, image, max_new_tokens, image_slices, offload_after, detail_mode)
        )
