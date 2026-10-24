"""Model-free validation of the optional semantic-base inference boundary."""

import hashlib
import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest

DIRECTORY = Path(__file__).resolve().parents[1] / "comfyui" / "upscaler"


def module(name):
    spec = importlib.util.spec_from_file_location(f"psnext_contract_{name}", DIRECTORY / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


prompts = module("prompts")
artifact = module("artifact")


@pytest.mark.parametrize("has_image", [False, True])
def test_text_request_is_trimmed_and_bounds_checked(has_image):
    assert prompts.validate_request(" fox ", has_image, 128, 1) == "fox"
    assert "fox" in prompts.user_request("fox", has_image)


def test_image_only_is_valid_and_missing_both_is_actionable():
    assert prompts.validate_request("", True, 128, 1) == ""
    assert "visible" in prompts.user_request("", True)
    with pytest.raises(ValueError, match="Enter a scene"):
        prompts.validate_request(" ", False, 128, 1)


@pytest.mark.parametrize(
    "prompt,budget,slices",
    [
        (None, 128, 1),
        ("a" * 6001, 128, 1),
        ("a", True, 1),
        ("a", 31, 1),
        ("a", 385, 1),
        ("a", 128, False),
        ("a", 128, 5),
    ],
)
def test_request_limits(prompt, budget, slices):
    with pytest.raises(ValueError):
        prompts.validate_request(prompt, False, budget, slices)


def test_required_unicode_text_is_preserved_or_rejected():
    assert prompts.clean_output('A bowl marked "雨".', 'Bowl marked "雨"', False) == (
        'A bowl marked "雨".',
        [],
    )
    with pytest.raises(RuntimeError, match="required quoted text"):
        prompts.clean_output("A bowl.", "Bowl marked “雨”", False)


@pytest.mark.parametrize("raw", ["", " ", "<think>Reasoning</think> A cat.", "<|im_start|>assistant"])
def test_empty_and_reasoning_outputs_are_not_published(raw):
    with pytest.raises(RuntimeError):
        prompts.clean_output(raw, "cat", False)


def test_truncation_and_edit_language_are_reported_without_silent_semantic_rewrites():
    result, warnings = prompts.clean_output("Replace the bird", "bird", True)
    assert result == "Replace the bird" and len(warnings) == 2


def archive(entries=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as writer:
        for name in entries if entries is not None else artifact.FILES:
            writer.writestr(name, "{}")
    return buffer.getvalue()


def test_asset_archive_is_data_only_and_digest_checked():
    data = archive()
    assert set(artifact.unpack_assets(data, hashlib.sha256(data).hexdigest())) == artifact.FILES
    with pytest.raises(ValueError, match="integrity"):
        artifact.unpack_assets(data, "0" * 64)


@pytest.mark.parametrize("names", [list(artifact.FILES) + ["../evil.py"], list(artifact.FILES)[:-1]])
def test_asset_archive_rejects_extra_or_missing_members(names):
    data = archive(names)
    with pytest.raises(ValueError, match="Unexpected"):
        artifact.unpack_assets(data, hashlib.sha256(data).hexdigest())


def test_duplicate_archive_members_are_rejected():
    with pytest.warns(UserWarning, match="Duplicate"):
        data = archive([*artifact.FILES, "config.json"])
    with pytest.raises(ValueError, match="Unexpected"):
        artifact.unpack_assets(data, hashlib.sha256(data).hexdigest())


def test_unknown_model_config_is_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        artifact.validate_config({"model_type": "arbitrary_remote_code"})


def test_possible_style_leakage_is_reported_but_quoted_display_text_is_preserved():
    _, warnings = prompts.clean_output("A bicycle, cinematic oil painting.", "bicycle", False)
    assert len(warnings) == 1 and "style language" in warnings[0]
    assert prompts.clean_output('A sign reading "CINEMATIC".', 'Sign "CINEMATIC"', False)[1] == []


def test_exact_multiline_quoted_text_is_checked():
    text = 'A sign reading "Hello\nWorld".'
    assert prompts.clean_output(text, text, False)[0] == text
    with pytest.raises(RuntimeError, match="quoted text"):
        prompts.clean_output('A sign reading "Hello World".', text, False)


def test_example_upscaler_graph_feeds_semantic_base_into_style():
    root = DIRECTORY.parents[1]
    graph = json.loads((root / "examples" / "comfyui-upscaler-api.json").read_text())
    assert graph["1"]["class_type"] == "PSNextLoadUpscaler"
    assert graph["2"]["class_type"] == "PSNextUpscaleBase"
    assert graph["2"]["inputs"]["upscaler"] == ["1", 0]
    assert graph["3"]["inputs"]["prompt"] == ["2", 0]
