"""V3 nodes for the optional native MiniCPM base-prompt authoring stage."""

from comfy_api.latest import io

from .upscaler import idea_prompts, moss_upsampler
from .upscaler.layout_assist import TASKS as LAYOUT_TASKS
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
            description="Load a local self-contained MiniCPM or LFM3-VL INT8 ConvRot model, or the Qwen3.5 MOSS prompt upsampler. ComfyUI caches this handle and manages its VRAM. Requires the native CUDA/Kitchen backend.",
            search_aliases=["minicpm", "lfm3", "qwen3.5", "upsampler", "vlm", "prompt", "upscale"],
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
                io.Combo.Input(
                    "style_mode",
                    options=list(idea_prompts.STYLE_MODES),
                    default="open",
                    optional=True,
                    advanced=True,
                    tooltip="open lets ideas pick a medium or photo look. neutral describes content only and leaves the look to the image model. match writes content for the look in style and leaves every axis in style_axes to it.",
                ),
                io.String.Input(
                    "style",
                    default="",
                    multiline=True,
                    optional=True,
                    advanced=True,
                    tooltip="match only: the selected style's own prompt text (for example PromptStyler Compose with an empty prompt).",
                ),
                io.String.Input(
                    "style_axes",
                    default="",
                    optional=True,
                    advanced=True,
                    tooltip="match only: axes the style sets, comma-separated (medium, lighting, palette, composition, texture, mood, detail).",
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
        style_mode="open",
        style="",
        style_axes="",
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
                style_mode or "open",
                style or "",
                style_axes or "",
            )
        )


class PSNextMossUpsampler(io.ComfyNode):
    """Expand a short draft with the MOSS-Image prompt-upsampling fine-tune (Qwen3.5-2B)."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        defaults = moss_upsampler.DEFAULT_SAMPLING
        return io.Schema(
            node_id="PSNextMossUpsampler",
            display_name="PromptStyler Next: MOSS Prompt Upsampler",
            category="PromptStyler Next/upscaling",
            description="Expand a short idea into a rich, vivid MOSS-Image prompt with the Qwen3.5 MOSS upsampler fine-tune. Uses the fine-tune's exact training system prompt with thinking off; an optional style is appended to the draft as a short trailing clause; each seed writes a different take. Text only. Review the result: the model invents detail on purpose.",
            search_aliases=["moss", "qwen3.5", "upsample", "enhance", "expand", "prompt"],
            inputs=[
                UPSCALER.Input("upscaler"),
                io.String.Input("prompt", default="", multiline=True, dynamic_prompts=False),
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF, control_after_generate=True),
                io.Float.Input(
                    "temperature",
                    default=defaults["temperature"],
                    min=0.0,
                    max=1.5,
                    step=0.05,
                    tooltip="0 decodes greedily (same output every run). The v2 model card recommends 0.55-0.65; higher is more varied.",
                ),
                io.Float.Input("top_p", default=defaults["top_p"], min=0.0, max=1.0, step=0.01, advanced=True),
                io.Int.Input("top_k", default=defaults["top_k"], min=0, max=1000, advanced=True),
                io.Float.Input("min_p", default=defaults["min_p"], min=0.0, max=1.0, step=0.01, advanced=True),
                io.Float.Input("presence_penalty", default=defaults["presence_penalty"], min=0.0, max=2.0, step=0.05, advanced=True),
                io.Int.Input(
                    "max_new_tokens",
                    default=moss_upsampler.DEFAULT_MAX_NEW_TOKENS,
                    min=64,
                    max=2048,
                    advanced=True,
                    tooltip="Output budget. v2 training prompts reach about 637 tokens; generation stops at the end token, and a cut-off tail is trimmed to the last sentence.",
                ),
                io.Boolean.Input(
                    "offload_after",
                    default=False,
                    advanced=True,
                    tooltip="True releases the model's VRAM after each run. ComfyUI can otherwise offload it when another model needs memory.",
                ),
                io.String.Input(
                    "style",
                    default="",
                    optional=True,
                    dynamic_prompts=False,
                    tooltip="Optional short look (for example a PromptStyler Next style clause). It is appended to the draft as a trailing clause so the upsampler writes the whole prompt in that medium; capped at 30 words.",
                ),
                io.Float.Input(
                    "repetition_penalty",
                    default=moss_upsampler.DEFAULT_REPETITION_PENALTY,
                    min=1.0,
                    max=2.0,
                    step=0.01,
                    optional=True,
                    advanced=True,
                    tooltip="1.05 is the v2 model card setting; 1.0 turns it off.",
                ),
                io.Boolean.Input(
                    "guard",
                    default=True,
                    optional=True,
                    tooltip="Temporary v2 workaround: swaps provenance tokens (trending on artstation, 8k, unreal engine) in the draft, then removes unrequested visible text (watermarks, credit lines, quoted lettering), negation tails and, for black-and-white drafts, color words. Regex-based: unusual wording can slip through.",
                ),
                io.Int.Input(
                    "max_takes",
                    default=1,
                    min=1,
                    max=moss_upsampler.MAX_TAKES,
                    optional=True,
                    advanced=True,
                    tooltip="With the guard on, a sampled run writes another take (seed+1, ...) only when the guard gives up on the last one because cleaning would remove too much. 1 never retries. Greedy runs always write one take.",
                ),
            ],
            outputs=[io.String.Output("prompt"), io.String.Output("inspection")],
        )

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return moss_upsampler.CONTRACT_VERSION

    @classmethod
    def execute(
        cls,
        upscaler,
        prompt="",
        seed=0,
        temperature=moss_upsampler.DEFAULT_SAMPLING["temperature"],
        top_p=moss_upsampler.DEFAULT_SAMPLING["top_p"],
        top_k=moss_upsampler.DEFAULT_SAMPLING["top_k"],
        min_p=0.0,
        presence_penalty=0.0,
        max_new_tokens=moss_upsampler.DEFAULT_MAX_NEW_TOKENS,
        offload_after=False,
        style="",
        repetition_penalty=moss_upsampler.DEFAULT_REPETITION_PENALTY,
        guard=True,
        max_takes=1,
    ):
        from .upscaler.runtime import upsample_moss

        return io.NodeOutput(
            *upsample_moss(
                upscaler,
                prompt,
                seed,
                temperature,
                top_p,
                top_k,
                min_p,
                presence_penalty,
                max_new_tokens,
                offload_after,
                style or "",
                repetition_penalty,
                guard,
                max_takes,
            )
        )


def _lazy(item):
    """Mark an input lazy; core's BoundingBox.Input constructor does not take the flag."""
    item.lazy = True
    return item


class PSNextLayoutAssist(io.ComfyNode):
    """LFM3-VL writes or describes a MOSS layout as JSON; boxes are xyxy on a 0-1000 grid."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="PSNextLayoutAssist",
            display_name="PromptStyler Next: Layout Assist (LFM3-VL)",
            category="PromptStyler Next/upscaling",
            description=(
                "JSON layout work for the MOSS layout builder with LFM3-VL. list_objects names the main things "
                "in an image (wire 'labels' into a detector query; it adds title/text when it sees lettering); "
                "describe_regions keeps the boxes that matter, reads detected lettering, captions the boxes and "
                "writes the caption with a background sentence and style words; text_layout plans a layout from an "
                "idea; edit_layout applies an instruction; image_layout places boxes without a detector. Boxes are "
                "[x1, y1, x2, y2] on a 0-1000 grid. Decodes as one CUDA graph per token."
            ),
            search_aliases=["layout", "moss", "bbox", "lfm3", "json", "describe", "regions"],
            inputs=[
                UPSCALER.Input("upscaler"),
                io.Combo.Input("task", options=list(LAYOUT_TASKS), default="describe_regions"),
                io.String.Input("request", default="", multiline=True, dynamic_prompts=False,
                                tooltip="The idea for text_layout, the instruction for edit_layout, or a scene note."),
                io.String.Input("layout", default="", multiline=True, dynamic_prompts=False, optional=True,
                                tooltip='Optional JSON {"caption", "items": [{"label", "caption", "text", "bbox"}]} (xyxy, 0-1000).'),
                io.Image.Input("image", optional=True),
                io.BoundingBox.Input("objects", optional=True, force_input=True,
                                     tooltip="Detector boxes in pixels of the image (for example WeVisOne-VL Detect)."),
                _lazy(io.BoundingBox.Input("words", optional=True, force_input=True,
                                           tooltip="OCR word boxes; joined into lines of lettering. Evaluated only "
                                           "when needed, so a skipped OCR node never runs.")),
                io.Boolean.Input("read_words", optional=True, force_input=True,
                                 tooltip="Wire list_objects' 'lettering' here: false skips the OCR connected to "
                                 "'words' (it loops on images without text) and drops detected lettering blocks. "
                                 "Unconnected, lettering is read."),
                io.String.Input("scene", optional=True, force_input=True,
                                tooltip="list_objects' layout output: its background nouns join the things that get "
                                "no box, so describe_regions writes them into the background sentence."),
                io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF, control_after_generate=False),
                io.Float.Input("temperature", default=0.0, min=0.0, max=1.2, step=0.05,
                               tooltip="0 decodes greedily: fastest and repeatable."),
            ],
            outputs=[io.String.Output("layout"), io.String.Output("labels"), io.String.Output("inspection"),
                     io.Boolean.Output("lettering", tooltip="list_objects: whether the image shows text. "
                                       "Wire it to a describe step's read_words.")],
        )

    @classmethod
    def check_lazy_status(cls, task="describe_regions", read_words=None, **kwargs):
        # Only a connected, not yet evaluated 'words' is requested (an unconnected one is absent from kwargs).
        if task == "describe_regions" and "words" in kwargs and kwargs["words"] is None and read_words is not False:
            return ["words"]
        return []

    @classmethod
    def execute(cls, upscaler, task, request="", layout="", image=None, objects=None, words=None, seed=0,
                temperature=0.0, read_words=None, scene=""):
        from .upscaler.runtime import layout_assist

        if read_words is False:
            words = None
        return io.NodeOutput(*layout_assist(upscaler, task, image, request, layout or "", objects, words, seed,
                                            temperature, scene or "", lettering=read_words is not False))


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
