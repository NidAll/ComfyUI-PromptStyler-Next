"""Real V3 schema/registration checks; model encoding uses an explicit test double.

Run with the ComfyUI source directory on PYTHONPATH and its Python environment.
No server, model downloads, or model loading are involved.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

io = pytest.importorskip(
    "comfy_api.latest", reason="Set PYTHONPATH to a ComfyUI checkout for host integration tests"
).io

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "psnext_host_test", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
)
assert SPEC is not None and SPEC.loader is not None
EXTENSION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = EXTENSION
SPEC.loader.exec_module(EXTENSION)
NODES = asyncio.run(EXTENSION.comfy_entrypoint())
NODE_CLASSES = asyncio.run(NODES.get_node_list())
STYLE, COMPOSE, ENCODE, LOAD_UPSCALER, UPSCALE_BASE, PREVIEW_PROMPT = NODE_CLASSES


def literal_inputs(inputs: dict) -> dict:
    return {
        key: value["__value__"] if isinstance(value, dict) and "__value__" in value else value
        for key, value in inputs.items()
    }


def first_style() -> str:
    return STYLE.define_schema().inputs[1].options[0]


def test_real_v3_registration_and_schema() -> None:
    assert len(NODE_CLASSES) == 6
    assert not hasattr(EXTENSION, "NODE_CLASS_MAPPINGS")
    expected = {
        "PSNextStyle",
        "PSNextCompose",
        "PSNextEncode",
        "PSNextLoadUpscaler",
        "PSNextUpscaleBase",
        "PSNextPreviewPrompt",
    }
    assert {node.define_schema().node_id for node in NODE_CLASSES} == expected
    for node in NODE_CLASSES:
        assert issubclass(node, io.ComfyNode)
        schema = node.define_schema()
        assert schema.inputs and (schema.outputs or schema.is_output_node)
        schema.validate()
        node.VALIDATE_CLASS()
        info = node.GET_NODE_INFO_V1()
        assert info["name"] == schema.node_id
        json.dumps(info, allow_nan=False)


def test_style_picker_metadata_matches_catalog_without_changing_widget_inputs():
    module = sys.modules[STYLE.__module__]
    schema = STYLE.define_schema()
    assert [item.id for item in schema.inputs] == [
        "prompt",
        "style",
        "model",
        "intensity",
        "negative",
        "locked_axes",
    ]
    options = STYLE.GET_NODE_INFO_V1()["input"]["required"]["style"][1]
    categories = options["psnext_categories"]
    assert set(categories) == set(options["options"])
    assert len(categories) > 1000  # Includes the second catalog page.
    assert all(module.get_engine().get_style(key)["category"] == value for key, value in categories.items())
    assert (ROOT / EXTENSION.WEB_DIRECTORY / "promptstyler.js").is_file()


def test_saved_style_id_preserves_composition_and_fingerprint():
    graph = json.loads((ROOT / "examples/comfyui-text-workflow.json").read_text())
    saved = next(node for node in graph["nodes"] if node["type"] == "PSNextStyle")["widgets_values"]
    output = STYLE.execute(*saved)
    inspection = json.loads(output.result[2])
    recipe = COMPOSE.execute(json.dumps(inspection["recipe"]))
    assert recipe.result == output.result
    assert inspection["recipe"]["styles"][0]["id"] == saved[1]
    assert inspection["fingerprint"] == json.loads(recipe.result[2])["fingerprint"]


def test_prompt_preview_returns_two_strings_without_writing_files():
    prompt = 'A red bicycle with a sign reading "雨".'
    inspection = '{"source":"text","warnings":[]}'
    result = PREVIEW_PROMPT.execute(prompt, inspection)
    assert result.result is None
    assert result.ui == {"text": [prompt], "inspection": [inspection]}


def test_prompt_preview_graph_passes_native_validation(monkeypatch):
    from comfy.cli_args import args

    monkeypatch.setattr(args, "cpu", True)
    import execution
    import nodes

    for node in NODE_CLASSES:
        monkeypatch.setitem(nodes.NODE_CLASS_MAPPINGS, node.define_schema().node_id, node)
    graph = {
        "load": {"class_type": "PSNextLoadUpscaler", "inputs": {"model_name": "example.safetensors"}},
        "upscale": {
            "class_type": "PSNextUpscaleBase",
            "inputs": {
                "upscaler": ["load", 0],
                "prompt": "a bicycle",
                "max_new_tokens": 192,
                "image_slices": 1,
                "offload_after": False,
            },
        },
        "preview": {
            "class_type": "PSNextPreviewPrompt",
            "inputs": {"base_prompt": ["upscale", 0], "inspection": ["upscale", 1]},
        },
    }
    # This graph checks structure only; the model name comes from the host's real combo options.
    options = LOAD_UPSCALER.GET_NODE_INFO_V1()["input"]["required"]["model_name"][1]["options"]
    if not options:
        pytest.skip("No local prompt upscaler model is installed")
    graph["load"]["inputs"]["model_name"] = options[0]
    valid, error, outputs, node_errors = asyncio.run(execution.validate_prompt("psnext-preview", graph, None))
    assert valid and error is None and not node_errors
    assert outputs == ["preview"]


def test_simple_node_exactly_matches_shared_engine() -> None:
    module = sys.modules[STYLE.__module__]
    recipe = {
        "schema_version": 1,
        "prompt": 'A blue bowl marked "雨"',
        "negative": "",
        "model": "sdxl",
        "styles": [{"id": first_style(), "intensity": 0.75}],
        "locked_axes": [],
    }
    expected = module.get_engine().compose(recipe).to_dict()
    output = STYLE.execute(recipe["prompt"], first_style(), "sdxl", 0.75)
    assert isinstance(output, io.NodeOutput)
    assert output.result[:2] == (expected["positive"], expected["negative"])
    assert json.loads(output.result[2]) == expected


def test_recipe_node_exactly_matches_simple_node() -> None:
    recipe = {
        "schema_version": 1,
        "prompt": "A ceramic bird",
        "model": "anima",
        "negative": "",
        "styles": [{"id": first_style(), "intensity": 0.5}],
        "locked_axes": ["palette"],
    }
    simple = STYLE.execute(recipe["prompt"], first_style(), "anima", 0.5, locked_axes=["palette"])
    composed = COMPOSE.execute(json.dumps(recipe))
    assert composed.result == simple.result


def test_zero_intensity_keeps_prompt() -> None:
    prompt = "  A red bicycle, rain.\n文字: hello!"
    output = STYLE.execute(prompt, first_style(), "sdxl", 0)
    assert output.result[0] == prompt


@pytest.mark.parametrize(
    "recipe", ['{"prompt":"x","prompt":"y"}', '{"styles":[{"id":"x","intensity":NaN}]}', "[", "[]"]
)
def test_invalid_recipe_fails_at_shared_boundary(recipe: str) -> None:
    with pytest.raises(ValueError):
        COMPOSE.execute(recipe)


@pytest.mark.parametrize("value", [-0.5, 1.5, float("nan"), float("inf")])
def test_untrusted_slider_value_is_validated(value: float) -> None:
    with pytest.raises(ValueError):
        STYLE.execute("bird", first_style(), "sdxl", value)


def test_untrusted_style_id_is_not_a_filesystem_path() -> None:
    with pytest.raises(ValueError):
        STYLE.execute("bird", "../../etc/passwd", "sdxl")


class EncoderDouble:
    """Only verifies delegation contracts; it makes no model-quality claims."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def tokenize(self, text: str) -> tuple[str, str]:
        self.calls.append(("tokenize", text))
        return ("native tokens", text)

    def encode_from_tokens_scheduled(self, tokens: object) -> dict[str, object]:
        self.calls.append(("encode_from_tokens_scheduled", tokens))
        return {"host_conditioning": tokens}


def test_conditioning_delegates_native_scheduled_path() -> None:
    encoder = EncoderDouble()
    result = ENCODE.execute(encoder, "positive", "negative", "sdxl")
    assert result.result == (
        {"host_conditioning": ("native tokens", "positive")},
        {"host_conditioning": ("native tokens", "negative")},
    )
    assert encoder.calls == [
        ("tokenize", "positive"),
        ("encode_from_tokens_scheduled", ("native tokens", "positive")),
        ("tokenize", "negative"),
        ("encode_from_tokens_scheduled", ("native tokens", "negative")),
    ]


@pytest.mark.parametrize("model", ["flux", "qwen-image", "moss-image", "fibo", "arbitrary-model"])
def test_specialized_profiles_cannot_be_encoded_as_generic_clip(model: str) -> None:
    encoder = EncoderDouble()
    with pytest.raises(ValueError, match="model-native"):
        ENCODE.execute(encoder, "subject", "", model)
    assert encoder.calls == []


def test_missing_native_encoder_is_actionable() -> None:
    with pytest.raises(ValueError, match="Connect a native"):
        ENCODE.execute(None, "subject", "", "sdxl")


def test_custom_pack_symlinks_are_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = sys.modules[STYLE.__module__]
    real = tmp_path / "target"
    real.write_text("{}")
    (tmp_path / "escape.json").symlink_to(real)
    monkeypatch.setattr(module, "_CUSTOM_PACKS", tmp_path)
    module.get_engine.cache_clear()
    try:
        with pytest.raises(ValueError, match="symlink"):
            module.get_engine()
    finally:
        module.get_engine.cache_clear()


def test_api_example_references_registered_nodes() -> None:
    graph = json.loads((ROOT / "examples" / "comfyui-text-api.json").read_text())
    assert graph["1"]["class_type"] == "PSNextStyle"
    assert graph["2"]["class_type"] == "PSNextCompose"
    assert graph["3"]["class_type"] == "PreviewAny"
    output = STYLE.execute(**literal_inputs(graph["1"]["inputs"]))
    recipe_output = COMPOSE.execute(**graph["2"]["inputs"])
    assert output.result[0] and recipe_output.result[0]


def test_text_only_workflow_reaches_native_preview_node() -> None:
    from comfy_extras.nodes_preview_any import PreviewAny

    graph = json.loads((ROOT / "examples" / "comfyui-text-api.json").read_text())
    styled = STYLE.execute(**literal_inputs(graph["1"]["inputs"]))
    composed = COMPOSE.execute(**graph["2"]["inputs"])
    positive_preview = PreviewAny().main(styled.result[0])
    inspection_preview = PreviewAny().main(composed.result[2])
    assert positive_preview["ui"]["text"][0] == styled.result[0]
    assert json.loads(inspection_preview["ui"]["text"][0])["fingerprint"]


def test_visual_graph_links_and_widget_contract() -> None:
    graph = json.loads((ROOT / "examples" / "comfyui-text-workflow.json").read_text())
    by_id = {node["id"]: node for node in graph["nodes"]}
    classes = {node.define_schema().node_id: node for node in NODE_CLASSES}
    for link_id, source, output_slot, target, input_slot, value_type in graph["links"]:
        assert by_id[source]["outputs"][output_slot]["type"] == value_type
        assert by_id[target]["inputs"][input_slot]["link"] == link_id
        schema = classes[by_id[source]["type"]].define_schema()
        assert output_slot < len(schema.outputs)
    # Widget order follows V3 schema order in the saved visual graph.
    style_node = by_id[1]
    style_inputs = [item.id for item in STYLE.define_schema().inputs]
    actual = STYLE.execute(**dict(zip(style_inputs, style_node["widgets_values"], strict=True)))
    recipe_output = COMPOSE.execute(by_id[2]["widgets_values"][0])
    assert actual.result[0] and json.loads(recipe_output.result[2])["recipe"]["locked_axes"] == [
        "composition"
    ]


def test_api_graph_passes_real_comfy_prompt_validation(monkeypatch):
    # Native validation imports model-management; keep this test process CPU-only.
    from comfy.cli_args import args

    monkeypatch.setattr(args, "cpu", True)
    import execution
    import nodes
    from comfy_extras.nodes_preview_any import PreviewAny

    for node in NODE_CLASSES:
        monkeypatch.setitem(nodes.NODE_CLASS_MAPPINGS, node.define_schema().node_id, node)
    monkeypatch.setitem(nodes.NODE_CLASS_MAPPINGS, "PreviewAny", PreviewAny)
    graph = json.loads((ROOT / "examples" / "comfyui-text-api.json").read_text())
    valid, error, outputs, node_errors = asyncio.run(execution.validate_prompt("psnext-test", graph, None))
    assert valid and error is None and not node_errors
    assert set(outputs) == {"3", "4"}


def test_raw_array_widget_is_not_a_valid_comfy_api_link(monkeypatch):
    from comfy.cli_args import args

    monkeypatch.setattr(args, "cpu", True)
    import execution
    import nodes
    from comfy_extras.nodes_preview_any import PreviewAny

    for node in NODE_CLASSES:
        monkeypatch.setitem(nodes.NODE_CLASS_MAPPINGS, node.define_schema().node_id, node)
    monkeypatch.setitem(nodes.NODE_CLASS_MAPPINGS, "PreviewAny", PreviewAny)
    graph = json.loads((ROOT / "examples" / "comfyui-text-api.json").read_text())
    graph["1"]["inputs"]["locked_axes"] = []
    result = asyncio.run(execution.validate_prompt("psnext-test-raw-array", graph, None))
    assert result[3]["1"]["errors"][0]["type"] == "bad_linked_input"


def test_recipe_node_styles_native_generated_text_input():
    request = {
        "prompt": "placeholder",
        "model": "anima-turbo",
        "styles": [{"id": "cinema.noir", "intensity": 0.75}],
    }
    output = COMPOSE.execute(json.dumps(request), prompt="An image-derived bird beside a lake")
    assert output.result[0].startswith("An image-derived bird beside a lake")
    inspection = json.loads(output.result[2])
    assert inspection["recipe"]["prompt"] == "An image-derived bird beside a lake"
    assert "placeholder" not in output.result[0]


def test_upscaler_schema_exposes_optional_image_and_advanced_speed_controls():
    schema = UPSCALE_BASE.define_schema()
    inputs = {item.id: item for item in schema.inputs}
    assert inputs["image"].optional
    assert inputs["prompt"].default == ""
    assert inputs["upscaler"].io_type == LOAD_UPSCALER.define_schema().outputs[0].io_type
    for name in ("max_new_tokens", "image_slices", "offload_after"):
        assert inputs[name].advanced


@pytest.fixture
def runtime(monkeypatch):
    import importlib

    from comfy.cli_args import args

    monkeypatch.setattr(args, "cpu", True)
    return importlib.import_module(f"{SPEC.name}.comfyui.upscaler.runtime")


@pytest.fixture
def model_double(runtime, monkeypatch):
    from types import SimpleNamespace

    import torch

    calls = []

    class Tokenizer:
        eos_token_id = 99

        def encode(self, text, **kwargs):
            return [198] if text == "\n" else [271]

        def decode(self, tokens, **kwargs):
            values = list(tokens)
            if values == [271]:
                return "\n\n"
            if values == [198]:
                return "\n"
            return "Two foxes share a yellow umbrella."

    class Batch(dict):
        def to(self, *args, **kwargs):
            return self

    class Processor:
        tokenizer = Tokenizer()

        def apply_chat_template(self, messages, **kwargs):
            calls.append(("messages", messages, kwargs))
            return "prepared chat"

        def __call__(self, **kwargs):
            calls.append(("processor", kwargs))
            return Batch(input_ids=torch.tensor([[2, 3]]))

    def generate(**kwargs):
        calls.append(("generate", kwargs))
        return torch.tensor([[2, 3, 42, 99]])

    owner = SimpleNamespace(
        load_device="cpu",
        model=SimpleNamespace(
            generate=generate, network=SimpleNamespace(generation_config=SimpleNamespace(eos_token_id=[99]))
        ),
    )
    handle = runtime.UpscalerHandle(owner, Processor(), 137, ("/models/model.safetensors", 123, 456, 1), 0.1)
    monkeypatch.setattr(runtime.mm, "load_models_gpu", lambda *a, **k: calls.append(("placement", k)))
    monkeypatch.setattr(runtime.mm, "unload_model_and_clones", lambda *a: calls.append(("unload",)))
    monkeypatch.setattr(runtime.mm, "throw_exception_if_processing_interrupted", lambda: None)
    return handle, calls


@pytest.mark.parametrize("text,use_image", [("two foxes", False), ("", True), ("two foxes", True)])
def test_upscaler_runtime_modes_and_native_placement(runtime, model_double, text, use_image):
    import torch

    handle, calls = model_double
    image = torch.zeros((1, 32, 32, 3)) if use_image else None
    result, inspection = runtime.upscale(handle, text, image)
    info = json.loads(inspection)
    assert result == ("two foxes. " if text and not use_image else "") + "Two foxes share a yellow umbrella."
    assert info["native_int8_layers"] == 137
    assert info["mode"] == ("text+image" if text and use_image else "image" if use_image else "text")
    assert not info["warnings"] or info["warnings"] == [
        "Little scene detail was added; inspect the result or increase the output budget"
    ]
    assert info["source_preserved"] == bool(text and not use_image)
    generations = [call[1] for call in calls if call[0] == "generate"]
    assert len(generations) == (2 if text and use_image else 1)
    assert all(item["use_cache"] and not item["do_sample"] for item in generations)
    assert not any(call[0] == "unload" for call in calls)
    assert not handle.lock.locked()
    # Native placement is called; the load node's handle is reused without reconstruction.
    runtime.upscale(handle, "foxes", offload_after=True)
    assert sum(call[0] == "unload" for call in calls) == 1


@pytest.mark.parametrize("target", ["moss_image_base", "anima"])
@pytest.mark.parametrize("use_image", [False, True])
def test_lfm_rewrites_with_target_and_separate_image_grounding(runtime, model_double, target, use_image):
    from types import SimpleNamespace

    import torch

    handle, calls = model_double
    handle.model_family = "lfm3_vl"
    handle.processor.tokenizer.pad_token_id = 0
    handle.owner.model.network.config = SimpleNamespace(
        text_config=SimpleNamespace(max_position_embeddings=128000)
    )
    image = torch.zeros((1, 32, 32, 3)) if use_image else None
    text, inspection = runtime.upscale(handle, "two foxes", image, image_slices=2, target_model=target)
    info = json.loads(inspection)
    assert text == "Two foxes share a yellow umbrella."
    assert info["authoring"] == "complete_rewrite" and info["target_model"] == target
    assert "source_preserved" not in info
    assert len([call for call in calls if call[0] == "generate"]) == (2 if use_image else 1)
    prepared = next(call[1] for call in calls if call[0] == "processor")
    assert prepared["text"] == ["prepared chat"]  # No copied assistant premise.
    if use_image:
        assert prepared["images_kwargs"]["size"]["longest_edge"] == 512 * 512 * 2
    assert not handle.lock.locked()


def test_lfm_excludes_other_image_models_before_placing_weights(runtime, model_double):
    handle, calls = model_double
    handle.model_family = "lfm3_vl"
    with pytest.raises(ValueError, match="target_model"):
        runtime.upscale(handle, "fox", target_model="fibo2")
    assert not calls and not handle.lock.locked()


def test_lfm_repairs_at_most_once_and_reports_unresolved_detail(runtime, model_double):
    from types import SimpleNamespace

    handle, calls = model_double
    handle.model_family = "lfm3_vl"
    handle.processor.tokenizer.pad_token_id = 0
    handle.owner.model.network.config = SimpleNamespace(
        text_config=SimpleNamespace(max_position_embeddings=128000)
    )
    _, inspection = runtime.upscale(handle, "Two foxes beside the window.", offload_after=True)
    info = json.loads(inspection)
    assert [p["stage"] for p in info["passes"]] == ["rewrite", "repair"]
    assert "window" in info["fidelity"]["missing_relation_details"] and info["warnings"]
    assert sum(call[0] == "generate" for call in calls) == 2
    assert sum(call[0] == "unload" for call in calls) == 1
    assert not handle.lock.locked()


@pytest.mark.parametrize(
    "repaired,accepted",
    [
        ("Two blue birds beside a red box.", True),
        ("Two red birds beside a red box.", False),
        ("Two blue birds.", False),
    ],
)
def test_lfm_repair_cannot_lose_previously_satisfied_constraints(
    runtime, model_double, monkeypatch, repaired, accepted
):
    handle, _ = model_double
    handle.model_family = "lfm3_vl"
    drafts = iter(["Two blue birds.", repaired])

    def generate(*args):
        return (
            next(drafts),
            False,
            {
                "input_tokens": 10,
                "generated_tokens": 10,
                "prepare_seconds": 0,
                "placement_seconds": 0,
                "generate_seconds": 0,
            },
        )

    monkeypatch.setattr(runtime, "_generate_lfm3", generate)
    result, inspection = runtime.upscale(handle, "Two blue birds beside a red box.")
    info = json.loads(inspection)
    assert info["repair_accepted"] is accepted
    assert result == (repaired if accepted else "Two blue birds.")
    assert [p["stage"] for p in info["passes"]] == ["rewrite", "repair"]
    assert not handle.lock.locked()


@pytest.mark.parametrize(
    "options",
    [
        {"prompt": "x" * 6001},
        {"max_new_tokens": 0},
        {"max_new_tokens": True},
        {"max_new_tokens": 2049},
        {"image_slices": 0},
        {"image_slices": 5},
    ],
)
def test_lfm_api_uses_node_input_limits_before_loading(runtime, model_double, options):
    handle, calls = model_double
    handle.model_family = "lfm3_vl"
    with pytest.raises(ValueError):
        runtime.upscale(handle, **({"prompt": "fox"} | options))
    assert not calls and not handle.lock.locked()


def test_upscaler_releases_lock_and_gpu_after_failure(runtime, model_double):
    handle, calls = model_double

    def fail(**kwargs):
        raise RuntimeError("decode failure")

    handle.owner.model.generate = fail
    with pytest.raises(RuntimeError, match="decode failure"):
        runtime.upscale(handle, "fox")
    assert not handle.lock.locked()
    assert calls[-1][0] == "unload"


@pytest.mark.parametrize("shape", [(2, 8, 8, 3), (1, 8, 8, 4), (8, 8, 3)])
def test_upscaler_rejects_batches_and_non_rgb_images(runtime, shape):
    import torch

    with pytest.raises(ValueError, match="one RGB"):
        runtime.pil_image(torch.zeros(shape))


def test_upscaler_rejects_nonfinite_pixels(runtime):
    import torch

    with pytest.raises(ValueError, match="non-finite"):
        runtime.pil_image(torch.full((1, 8, 8, 3), float("nan")))


def test_paragraph_stop_matches_merged_and_separate_newlines_on_device(runtime, model_double):
    import torch

    handle, _ = model_double
    stop = runtime.ParagraphComplete(handle.processor.tokenizer, 2, "cpu")
    assert not stop(torch.tensor([[2, 3, 42]]), None).item()
    assert stop(torch.tensor([[2, 3, 42, 271]]), None).item()
    assert stop(torch.tensor([[2, 3, 42, 198, 198]]), None).item()


def test_model_resolver_guards_containment_and_invalidates_file_changes(tmp_path, monkeypatch):
    import importlib

    models = importlib.import_module(f"{SPEC.name}.comfyui.upscaler.models")
    monkeypatch.setattr(models, "_roots", lambda: [tmp_path])
    path = tmp_path / "model.safetensors"
    path.write_bytes(b"original")
    before = models.bundle_fingerprint(path.name)
    path.write_bytes(b"changed contents")
    assert models.bundle_fingerprint(path.name) != before
    for name in ("../escape.safetensors", "/absolute.safetensors", "bad\\name.safetensors", "bad.pt"):
        with pytest.raises(ValueError):
            models.resolve_bundle(name)
    outside = tmp_path.parent / "escaped.safetensors"
    outside.write_bytes(b"x")
    (tmp_path / "link.safetensors").symlink_to(outside)
    with pytest.raises(FileNotFoundError):
        models.resolve_bundle("link.safetensors")


def test_upscaler_lock_releases_even_when_offload_fails(runtime, model_double, monkeypatch):
    handle, _ = model_double

    def fail(*args):
        raise RuntimeError("offload failure")

    monkeypatch.setattr(runtime.mm, "unload_model_and_clones", fail)
    with pytest.raises(RuntimeError, match="offload failure"):
        runtime.upscale(handle, "fox", offload_after=True)
    assert not handle.lock.locked()


def test_upscaler_api_graph_passes_native_prompt_validation(monkeypatch):
    from comfy.cli_args import args

    monkeypatch.setattr(args, "cpu", True)
    import execution
    import nodes
    from comfy_extras.nodes_preview_any import PreviewAny

    for node in NODE_CLASSES:
        monkeypatch.setitem(nodes.NODE_CLASS_MAPPINGS, node.define_schema().node_id, node)
    monkeypatch.setitem(nodes.NODE_CLASS_MAPPINGS, "PreviewAny", PreviewAny)
    graph = json.loads((ROOT / "examples" / "comfyui-upscaler-api.json").read_text())
    valid, error, outputs, node_errors = asyncio.run(
        execution.validate_prompt("psnext-upscaler", graph, None)
    )
    assert valid and error is None and not node_errors
    assert set(outputs) == {"4", "5"}


@pytest.mark.parametrize("target", ["moss_image_base", "anima"])
def test_lfm_examples_include_valid_style_and_base_previews(monkeypatch, tmp_path, target):
    from comfy.cli_args import args

    monkeypatch.setattr(args, "cpu", True)
    import execution
    import nodes
    import torch
    from safetensors.torch import save_file

    models = sys.modules[f"{SPEC.name}.comfyui.upscaler.models"]
    name = "lfm3-vl-2b-int8-convrot.safetensors"
    # Exercise real artifact discovery without requiring installed model weights.
    save_file(
        {"fixture": torch.zeros(1)},
        str(tmp_path / name),
        metadata={"lfm3_vl": json.dumps({"kind": "lfm3_vl", "version": 1})},
    )
    monkeypatch.setattr(models, "_roots", lambda: [tmp_path])
    filenames = models.folder_paths.get_filename_list
    monkeypatch.setattr(
        models.folder_paths,
        "get_filename_list",
        lambda kind: [name] if kind == models.MODEL_KIND else filenames(kind),
    )
    assert models.model_choices() == [name]

    for node in NODE_CLASSES:
        monkeypatch.setitem(nodes.NODE_CLASS_MAPPINGS, node.define_schema().node_id, node)
    graph = json.loads((ROOT / f"examples/comfyui-lfm3-{target}-api.json").read_text())
    valid, error, outputs, node_errors = asyncio.run(execution.validate_prompt("lfm-example", graph, None))
    assert valid and error is None and not node_errors
    assert set(outputs) == {"3", "5"}
    assert graph["4"]["inputs"]["prompt"] == ["2", 0]
    assert graph["2"]["inputs"]["target_model"] == target


def test_upscaler_visual_graph_has_valid_sockets_and_widgets():
    graph = json.loads((ROOT / "examples" / "comfyui-upscaler-workflow.json").read_text())
    by_id = {node["id"]: node for node in graph["nodes"]}
    classes = {node.define_schema().node_id: node for node in NODE_CLASSES}
    for link_id, source, output_slot, target, input_slot, value_type in graph["links"]:
        assert by_id[source]["outputs"][output_slot]["type"] == value_type
        assert by_id[target]["inputs"][input_slot]["link"] == link_id
        if by_id[source]["type"] in classes:
            schema = classes[by_id[source]["type"]].define_schema()
            assert schema.outputs[output_slot].io_type == value_type
    assert by_id[2]["widgets_values"] == ["two foxes sharing a yellow umbrella", 192, 1, False, "expanded"]
    assert next(item for item in by_id[2]["inputs"] if item["name"] == "image")["link"] is None


@pytest.mark.parametrize("mode", ["expanded", "faithful"])
def test_upscaler_selected_mode_reaches_prompt_policy_and_inspection(runtime, model_double, mode):
    handle, calls = model_double
    _, inspection = runtime.upscale(handle, "a robot reading", detail_mode=mode)
    assert json.loads(inspection)["settings"]["detail_mode"] == mode
    system = next(call[1][0]["content"] for call in calls if call[0] == "messages")
    assert ("without inventing" in system) == (mode == "faithful")
    assert ("Make the idea more visually specific" in system) == (mode == "expanded")


def test_invalid_detail_mode_cannot_place_or_run_a_model(runtime, model_double):
    handle, calls = model_double
    with pytest.raises(ValueError, match="detail_mode"):
        runtime.upscale(handle, "a robot", detail_mode="unsupported")
    assert calls == [] and not handle.lock.locked()


def test_new_detail_widget_keeps_the_existing_widget_prefix():
    inputs = UPSCALE_BASE.define_schema().inputs
    widgets = [item.id for item in inputs if item.id not in ("upscaler", "image")]
    assert widgets == [
        "prompt",
        "max_new_tokens",
        "image_slices",
        "offload_after",
        "detail_mode",
        "target_model",
    ]
    target = next(item for item in inputs if item.id == "target_model")
    assert target.optional and target.default == "moss_image_base"
    mode = next(item for item in inputs if item.id == "detail_mode")
    assert mode.optional and mode.default == "expanded"
    contracts = UPSCALE_BASE.fingerprint_inputs()
    assert contracts[0] == "semantic-base-2" and contracts[1] == "lfm-semantic-depth-1"


def test_existing_api_graph_without_detail_mode_still_validates(monkeypatch):
    from comfy.cli_args import args

    monkeypatch.setattr(args, "cpu", True)
    import execution
    import nodes
    from comfy_extras.nodes_preview_any import PreviewAny

    for node in NODE_CLASSES:
        monkeypatch.setitem(nodes.NODE_CLASS_MAPPINGS, node.define_schema().node_id, node)
    monkeypatch.setitem(nodes.NODE_CLASS_MAPPINGS, "PreviewAny", PreviewAny)
    graph = json.loads((ROOT / "examples/comfyui-upscaler-api.json").read_text())
    graph["2"]["inputs"].pop("detail_mode")
    graph["2"]["inputs"]["max_new_tokens"] = 128
    valid, error, _, node_errors = asyncio.run(execution.validate_prompt("old-upscaler-api", graph, None))
    assert valid and error is None and not node_errors


def test_expanded_generation_prefills_all_user_constraints(runtime, model_double):
    handle, calls = model_double
    source = 'A wizard folding the ocean into a perfect cube using gravity. A sign reads "雨".'
    # The model double adds a sentence; the literal text already belongs to its prefix.
    base, inspection = runtime.upscale(handle, source)
    assert base.startswith(source + " ")
    info = json.loads(inspection)
    assert info["source_preserved"] is True and info["added_words"] == 6
    prepared = next(call[1]["text"][0] for call in calls if call[0] == "processor")
    assert prepared.endswith(source + " ")


def test_source_paragraphs_do_not_hide_a_truncated_continuation(runtime, model_double):
    import torch

    handle, _ = model_double
    handle.owner.model.generate = lambda **kwargs: torch.tensor([[2, 3] + [42] * 32])
    source = "A wizard.\n\nThe ocean folds into a cube."
    _, inspection = runtime.upscale(handle, source, max_new_tokens=32)
    info = json.loads(inspection)
    assert info["generated_tokens"] == 32
    assert any(warning.startswith("Token limit reached") for warning in info["warnings"])
