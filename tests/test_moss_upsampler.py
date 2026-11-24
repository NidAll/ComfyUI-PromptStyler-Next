"""MOSS upsampler prompt contract, without Torch or model weights."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
# A bare package around comfyui/upscaler lets the module's relative guard import resolve without ComfyUI.
PACKAGE = types.ModuleType("psn_upscaler")
PACKAGE.__path__ = [str(ROOT / "comfyui" / "upscaler")]
sys.modules["psn_upscaler"] = PACKAGE
SPEC = importlib.util.spec_from_file_location("psn_upscaler.moss_upsampler", ROOT / "comfyui" / "upscaler" / "moss_upsampler.py")
moss = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = moss
SPEC.loader.exec_module(moss)

IM_END, EOT = 248046, 248044


class FakeClip:
    """Records what the node sends to ComfyUI's CLIP tokenize/generate."""

    def __init__(self, ids, text):
        self.ids, self.text, self.calls = ids, text, {}
        vocab = {"<|im_end|>": IM_END, "<|endoftext|>": EOT}
        inner = SimpleNamespace(tokenizer=SimpleNamespace(get_vocab=lambda: vocab))
        self.tokenizer = SimpleNamespace(clip="qwen35_2b", qwen35_2b=inner)

    def tokenize(self, text, **kwargs):
        self.calls["tokenize"] = (text, kwargs)
        return {"qwen35_2b": [[(1, 1.0)] * 12]}

    def generate(self, tokens, **kwargs):
        self.calls["generate"] = kwargs
        return list(self.ids)

    def decode(self, ids):
        return self.text


def test_uses_the_exact_sft_system_prompt_with_thinking_off():
    assert moss.SYSTEM_PROMPT == (
        "Expand the user prompt into a rich, vivid image generation prompt. Output only the final prompt."
    )
    clip = FakeClip([5, 6, IM_END], "A purple cat sits on a grey sofa.")
    text, info = moss.upsample(clip, "  photo of a purple cat ", seed=7)
    draft, kwargs = clip.calls["tokenize"]
    assert draft == "photo of a purple cat"
    assert kwargs["system_prompt"] == moss.SYSTEM_PROMPT and kwargs["thinking"] is False
    sent = clip.calls["generate"]
    assert sent["do_sample"] is True and sent["temperature"] == 0.6 and sent["top_p"] == 0.9 and sent["top_k"] == 20
    assert sent["seed"] == 7 and sent["mtp"] is False and sent["max_length"] == 700 and sent["repetition_penalty"] == 1.05
    assert text == "A purple cat sits on a grey sofa."
    assert info["upsample"]["truncated"] is False and info["model_family"] == "qwen35_upsampler"
    assert info["upsample"]["prompt_tokens"] == 12 and not info["warnings"]


def test_zero_temperature_is_greedy():
    clip = FakeClip([5, EOT], "Text.")
    moss.upsample(clip, "korean tofu soup", temperature=0)
    assert clip.calls["generate"]["do_sample"] is False


def test_cut_off_output_is_trimmed_to_a_sentence_and_flagged():
    long = "First sentence about the cat. Second sentence about the sofa. Third sentence that stops mid"
    clip = FakeClip([5] * 64, long)
    text, info = moss.upsample(clip, "cat", max_new_tokens=64)
    assert text == "First sentence about the cat. Second sentence about the sofa."
    assert info["upsample"]["truncated"] is True and info["warnings"]


def test_cleaning_removes_reasoning_quotes_and_line_breaks():
    text, warnings = moss.clean_output('<think>\nplan\n</think>\n\n"A red fox.\n\nIt sleeps."', False)
    assert text == "A red fox. It sleeps." and not warnings


@pytest.mark.parametrize("prompt", ["", "   ", "x" * 6001, None])
def test_invalid_prompts_are_refused(prompt):
    with pytest.raises(ValueError):
        moss.validate_prompt(prompt)


def test_header_detection_needs_the_qwen35_hybrid_layout():
    assert moss.is_upsampler_header(
        {moss._HEADER_KEY, moss._NORM_KEY, "model.language_model.embed_tokens.weight"}
    )
    assert not moss.is_upsampler_header({"model.language_model.layers.0.self_attn.q_proj.weight"})


def test_style_rides_along_as_a_trailing_clause_of_the_draft():
    clip = FakeClip([5, IM_END], "Art Nouveau illustration of a fox.")
    _, info = moss.upsample(
        clip, "a red fox sleeping in a greenhouse.", style="  Art Nouveau illustration,  flowing contours. "
    )
    sent, kwargs = clip.calls["tokenize"]
    assert sent == "a red fox sleeping in a greenhouse, Art Nouveau illustration, flowing contours"
    assert kwargs["system_prompt"] == moss.SYSTEM_PROMPT
    assert info["user_text"] == sent and info["style"] == "Art Nouveau illustration, flowing contours"


def test_without_a_style_the_draft_is_the_only_user_text():
    clip = FakeClip([5, IM_END], "A fox.")
    _, info = moss.upsample(clip, "a red fox", style="  ")
    assert clip.calls["tokenize"][0] == "a red fox" and info["style"] == "" and info["user_text"] == "a red fox"


def test_long_styles_are_capped():
    text, style = moss.compose_draft("a fox", " ".join(f"w{i}" for i in range(50)))
    assert len(style.split()) == moss.MAX_STYLE_WORDS and text == f"a fox, {style}"


def test_a_checkpoint_with_an_mtp_head_decodes_speculatively():
    clip = FakeClip([5, IM_END], "A fox.")
    _, info = moss.upsample(clip, "a red fox", speculative=True)
    assert clip.calls["generate"]["mtp"] is True and info["upsample"]["speculative"] is True
    _, info = moss.upsample(clip, "a red fox")
    assert clip.calls["generate"]["mtp"] is False and info["upsample"]["speculative"] is False
