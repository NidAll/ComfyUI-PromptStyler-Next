"""V3 nodes for the optional native MiniCPM base-prompt authoring stage."""

from comfy_api.latest import io

from .upscaler import idea_prompts
from .upscaler.lfm_prompts import CONTRACT_VERSION as LFM_CONTRACT_VERSION
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
            description="Load a local self-contained MiniCPM or LFM3-VL INT8 ConvRot model. ComfyUI caches this handle and manages its VRAM. Requires the native CUDA/Kitchen backend.",
            search_aliases=["minicpm", "lfm3", "vlm", "prompt", "upscale"],
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
                    max=2048,
                    advanced=True,
                    tooltip="Maximum output budget. The 192-token default is fast; larger budgets allow longer descriptions. Decoding stops at EOS or a blank paragraph.",
                ),
                io.Int.Input(
                    "image_slices",
                    default=1,
                    min=1,
                    max=4,
                    advanced=True,
                    tooltip="MiniCPM: image slices. LFM3-VL: each unit allows up to 512×512 pixels while retaining aspect ratio. More detail uses more time and VRAM.",
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
                    tooltip="Expanded develops visible physical details; Faithful clarifies with minimal additions. LFM3-VL rewrites the complete scene. MiniCPM retains its continuation behavior. Images stay grounded in reference content.",
                ),
                io.Combo.Input(
                    "target_model",
                    options=["moss_image_base", "anima"],
                    default="moss_image_base",
                    optional=True,
                    tooltip="LFM3-VL rewrites the complete caption for this image model. Apply Style/Compose after this stage. MiniCPM retains its existing semantic-base behavior.",
                ),
            ],
            outputs=[io.String.Output("base_prompt"), io.String.Output("inspection")],
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return CONTRACT_VERSION, LFM_CONTRACT_VERSION

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
        target_model="moss_image_base",
    ):
        from .upscaler.runtime import upscale

        return io.NodeOutput(
            *upscale(
                upscaler,
                prompt,
                image,
                max_new_tokens,
                image_slices,
                offload_after,
                detail_mode,
                target_model,
            )
        )


class PSNextPromptIdea(io.ComfyNode):
    """Each run turns a draft into a new prompt idea; vary the seed for another one."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PSNextPromptIdea",
            display_name="PromptStyler Next: Prompt Idea",
            category="PromptStyler Next/upscaling",
            description="Turn a draft into a new, fully written prompt idea. Each seed explores a different element (setting, light, viewpoint, moment, color...) in a different prompt structure while keeping your subject and explicit details. LFM3-VL only. Unlike Upscale Base Prompt it invents on purpose: review the result.",
            search_aliases=["idea", "brainstorm", "explore", "variation", "creative prompt", "enhance"],
            inputs=[
                UPSCALER.Input("upscaler"),
                io.String.Input("prompt", default="", multiline=True, dynamic_prompts=False),
                io.Combo.Input(
                    "exploration",
                    options=list(idea_prompts.EXPLORATIONS),
                    default="explore",
                    tooltip="Explore keeps your subject, action and explicit details and develops one new element. Wild keeps only the subject, quoted text and exclusions and combines a bold element with another one.",
                ),
                io.Combo.Input("detail", options=list(idea_prompts.DETAILS), default="balanced"),
                io.Combo.Input(
                    "target_model",
                    options=list(idea_prompts.TARGETS),
                    default="general",
                    tooltip="Adjusts the writing for the image model that reads the prompt.",
                ),
                io.Combo.Input(
                    "lens",
                    options=["auto", *idea_prompts.LENS_BY_KEY],
                    default="auto",
                    advanced=True,
                    tooltip="What to explore. Auto picks one by seed, skipping those listed in recent.",
                ),
                io.Combo.Input(
                    "structure",
                    options=["auto", *idea_prompts.STRUCTURE_BY_KEY],
                    default="auto",
                    advanced=True,
                    tooltip="How the prompt is organised. Auto picks one by seed, skipping those listed in recent.",
                ),
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF, control_after_generate=True),
                io.Float.Input(
                    "temperature",
                    default=0.85,
                    min=0.0,
                    max=1.5,
                    step=0.05,
                    tooltip="0 is repeatable greedy writing; higher values give more varied ideas. Brainstorming runs 0.2 hotter.",
                ),
                io.String.Input(
                    "avoid",
                    default="",
                    multiline=True,
                    optional=True,
                    advanced=True,
                    tooltip="Earlier ideas, one per line. New concepts that repeat their additions are avoided.",
                ),
                io.String.Input(
                    "earlier",
                    default="",
                    multiline=True,
                    optional=True,
                    advanced=True,
                    tooltip="Earlier full prompts, one per line. Wording they keep repeating is discouraged.",
                ),
                io.String.Input(
                    "recent",
                    default="",
                    optional=True,
                    advanced=True,
                    tooltip="Lens and structure keys used recently (comma-separated); auto skips them while others remain.",
                ),
                io.Int.Input(
                    "max_new_tokens",
                    default=0,
                    min=0,
                    max=1024,
                    advanced=True,
                    tooltip="0 sizes the budget from detail and draft length.",
                ),
            ],
            outputs=[io.String.Output("prompt"), io.String.Output("inspection")],
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return idea_prompts.CONTRACT_VERSION

    @classmethod
    def execute(
        cls,
        upscaler,
        prompt="",
        exploration="explore",
        detail="balanced",
        target_model="general",
        lens="auto",
        structure="auto",
        seed=0,
        temperature=0.85,
        avoid="",
        earlier="",
        recent="",
        max_new_tokens=0,
    ):
        from .upscaler.runtime import ideate

        return io.NodeOutput(
            *ideate(
                upscaler,
                prompt,
                exploration,
                detail,
                target_model,
                lens,
                structure,
                seed,
                temperature,
                avoid or "",
                recent or "",
                max_new_tokens,
                earlier or "",
            )
        )


class PSNextPreviewPrompt(io.ComfyNode):
    """Return both upscaler results through ComfyUI's normal output/history path."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PSNextPreviewPrompt",
            display_name="PromptStyler Next: Preview Base Prompt",
            category="PromptStyler Next/upscaling",
            description="Preview a base prompt and its inspection without writing a file.",
            is_output_node=True,
            inputs=[
                io.String.Input("base_prompt", force_input=True),
                io.String.Input("inspection", force_input=True),
            ],
            outputs=[],
        )

    @classmethod
    def execute(cls, base_prompt, inspection):
        return io.NodeOutput(ui={"text": [base_prompt], "inspection": [inspection]})
