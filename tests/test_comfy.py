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
STYLE, COMPOSE, ENCODE, LOAD_UPSCALER, UPSCALE_BASE = NODE_CLASSES


def literal_inputs(inputs: dict) -> dict:
    return {
        key: value["__value__"] if isinstance(value, dict) and "__value__" in value else value
        for key, value in inputs.items()
    }


def first_style() -> str:
    return STYLE.define_schema().inputs[1].options[0]


def test_real_v3_registration_and_schema() -> None:
    assert len(NODE_CLASSES) == 5
    assert not hasattr(EXTENSION, "NODE_CLASS_MAPPINGS")
    expected = {"PSNextStyle", "PSNextCompose", "PSNextEncode", "PSNextLoadUpscaler", "PSNextUpscaleBase"}
    assert {node.define_schema().node_id for node in NODE_CLASSES} == expected
    for node in NODE_CLASSES:
        assert issubclass(node, io.ComfyNode)
        schema = node.define_schema()
        assert schema.inputs and schema.outputs
        schema.validate()
        node.VALIDATE_CLASS()
        info = node.GET_NODE_INFO_V1()
        assert info["name"] == schema.node_id
        json.dumps(info, allow_nan=False)


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
    assert result == "Two foxes share a yellow umbrella."
    assert info["native_int8_layers"] == 137
    assert info["mode"] == ("text+image" if text and use_image else "image" if use_image else "text")
    assert info["warnings"] == []
    generations = [call[1] for call in calls if call[0] == "generate"]
    assert len(generations) == (2 if text and use_image else 1)
    assert all(item["use_cache"] and not item["do_sample"] for item in generations)
    assert not any(call[0] == "unload" for call in calls)
    assert not handle.lock.locked()
    # Native placement is called; the load node's handle is reused without reconstruction.
    runtime.upscale(handle, "foxes", offload_after=True)
    assert sum(call[0] == "unload" for call in calls) == 1


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
    assert by_id[2]["widgets_values"] == ["two foxes sharing a yellow umbrella", 128, 1, False]
    assert next(item for item in by_id[2]["inputs"] if item["name"] == "image")["link"] is None
