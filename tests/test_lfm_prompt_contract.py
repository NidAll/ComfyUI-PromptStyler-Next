"""Model-free checks of the LFM scene rewrite contract."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "lfm_prompts", Path(__file__).resolve().parents[1] / "comfyui/upscaler/lfm_prompts.py"
)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


@pytest.mark.parametrize("target", contract.TARGET_MODELS)
def test_expanded_rewrite_keeps_literal_requirements_and_neutral_depth_contract(target):
    prompt = 'Two blue birds left of a sign marked "雨"; no trees.'
    chat = contract.messages(prompt, False, target)
    assert [item["role"] for item in chat] == ["system", "user"]
    assert prompt in chat[-1]["content"][0]["text"]
    assert "original action" in chat[-1]["content"][0]["text"]
    assert "pose, visible shape, contact" in chat[-1]["content"][0]["text"]
    assert "separate styling engine" in chat[0]["content"]
    assert "Keep surreal or impossible actions literal" in chat[0]["content"]
    assert "spelling and punctuation" in chat[0]["content"]


def test_detailed_requests_are_preserved_without_a_word_count_branch():
    prompt = "A small dragon sits beside an open window with a map on its knees. " * 5
    request = contract.messages(prompt, False, "anima")[-1]["content"][0]["text"]
    assert prompt in request
    assert "minimally" not in request and "original action" in request
    assert contract.CONTRACT_VERSION == "lfm-semantic-depth-1"


def test_faithful_example_and_image_grounding_do_not_ask_for_additions():
    chat = contract.messages("Three pears without leaves.", False, "anima", "faithful")
    assert [item["role"] for item in chat] == ["system", "user", "assistant", "user"]
    assert "has no stamp" in chat[2]["content"]
    assert "no inferred background" in chat[-1]["content"][0]["text"]
    image = contract.messages("", True, "anima")
    assert [item["role"] for item in image] == ["system", "user"]
    assert image[-1]["content"][0] == {"type": "image"}
    assert image[-1]["content"][1]["text"].startswith("Describe the visible scene.")
    assert "no inferred background" in image[-1]["content"][1]["text"]
    assert "text requirements take priority" in image[0]["content"]


def test_target_and_mode_restrictions_are_explicit():
    with pytest.raises(ValueError, match="target_model"):
        contract.messages("robot", False, "other")
    with pytest.raises(ValueError, match="detail_mode"):
        contract.messages("robot", False, "anima", "other")
    with pytest.raises(ValueError, match="target_model"):
        contract.inspect_output("robot", "robot", False, "other")


def test_style_diagnostics_exclude_exact_display_text():
    _, warnings, info = contract.inspect_output(
        "A red rope, watercolor with cinematic lighting.", "A red rope.", False, "anima"
    )
    assert info["style_terms"] == ["cinematic lighting", "watercolor"] and warnings
    assert "separate styling engine: cinematic lighting; watercolor" in contract.repair_request(
        "A red rope.", "A red rope, watercolor.", info
    )
    _, warnings, info = contract.inspect_output(
        'A sign reads "watercolor".', 'A sign reads "watercolor".', False, "anima"
    )
    assert not info["style_terms"] and not warnings


def test_explicit_absence_clauses_survive_without_an_extra_generation():
    text, restored = contract.restore_exclusions(
        "Two birds stand beside a box.", "Two birds. No trees; no other characters."
    )
    assert text == "Two birds stand beside a box. No trees. no other characters."
    assert restored == ["No trees", "no other characters"]
    assert contract.restore_exclusions(text, "No trees.")[1] == []
    assert contract.restore_exclusions("A green bowl.", "Replace the red bowl with a green bowl.") == (
        "A green bowl.",
        [],
    )


def test_only_pure_style_clauses_are_removed_without_changing_scene_or_labels():
    text, removed = contract.remove_style_clauses(
        "A red umbrella lies on a step, watercolor with cinematic lighting."
    )
    assert text == "A red umbrella lies on a step."
    assert removed == ["watercolor with cinematic lighting"]
    for scene in [
        'A sign reads "RAIN, watercolor".',
        "A box, with watercolor tubes inside.",
        "An umbrella, with blue fabric.",
        "A painting, oil painting on the wall.",
    ]:
        assert contract.remove_style_clauses(scene) == (scene, [])


def test_repeating_requested_display_text_is_not_new_display_wording():
    _, warnings, info = contract.inspect_output(
        'A sign reads "雨". The word "雨" is on the sign.', 'A sign reads "雨".', False, "anima"
    )
    assert not info["unexpected_quoted_text"] and not warnings


def test_exact_multilingual_quotes_and_repetition_are_checked_without_failing():
    original = 'Signs read “雨”, «مرحبا!» and "OPEN\nNOW", plus another "雨".'
    raw = 'Signs read "雨", «مرحبا!» and "OPEN NOW".'
    text, warnings, info = contract.inspect_output(raw, original, False, "moss_image_base")
    assert text == raw
    assert info["missing_quoted_text"] == ["雨", "OPEN\nNOW"]
    assert any("quoted text" in warning for warning in warnings)
    assert contract.inspect_output('A sign reads "OPEN NOW".', 'A sign reads "OPEN".', False, "anima")[2][
        "missing_quoted_text"
    ] == ["OPEN"]


def test_lexical_diagnostics_do_not_claim_semantic_fidelity():
    original = 'Two red birds left of a blue box without trees; a sign reads "RED".'
    raw = 'A blue box stands beside two birds and a sign reading "RED".'
    text, warnings, info = contract.inspect_output(raw, original, True, "anima")
    assert text == raw
    assert info["missing_lexical_cues"] == {
        "counts": [],
        "colors": ["red"],
        "relations": ["left"],
        "negations": ["absence"],
    }
    assert "do not establish fidelity" in info["note"]
    assert len(warnings) >= 2
    assert "source_preserved" not in info


@pytest.mark.parametrize("raw", ["", "  ", "<think>reasoning</think>", "<|im_start|>assistant", "cat\x00"])
def test_empty_and_control_outputs_fail(raw):
    with pytest.raises(RuntimeError):
        contract.inspect_output(raw, "cat", False, "anima")


def test_edit_instruction_is_returned_with_warning():
    text, warnings, _ = contract.inspect_output("Replace the box.", "box", False, "anima")
    assert text == "Replace the box."
    assert any("edit instruction" in warning for warning in warnings)


def test_spatial_object_omissions_are_exposed_to_the_repair_stage():
    original = "A dragon sits on a seat beside the window."
    candidate = "A dragon sits on a seat."
    _, _, info = contract.inspect_output(candidate, original, False, "anima")
    assert "window" in info["missing_relation_details"]
    assert "beside the window" in info["missing_relation_phrases"]
    assert "Restore these source relationships explicitly: beside the window" in contract.repair_request(
        original, candidate, info
    )


def test_replacement_source_color_is_not_a_required_final_attribute():
    _, warnings, info = contract.inspect_output(
        "A green triangle is left of a blue circle.",
        "Replace the red square with a green triangle. Keep the blue circle.",
        False,
        "anima",
    )
    assert not warnings and not info["missing_lexical_cues"]["colors"]


def test_new_display_text_is_reported_but_image_ocr_can_add_observed_text():
    raw = 'Two foxes hold an umbrella printed with "YELLOW".'
    _, warnings, info = contract.inspect_output(raw, "Two foxes hold an umbrella.", False, "anima")
    assert info["unexpected_quoted_text"] == ["YELLOW"] and warnings
    assert (
        contract.inspect_output(raw, "", False, "anima", allow_reference_text=True)[2][
            "unexpected_quoted_text"
        ]
        == []
    )


def test_common_lexical_paraphrases_do_not_trigger_a_repair():
    _, warnings, _ = contract.inspect_output(
        "2 gray birds stand next to a box.", "Two grey birds stand beside a box.", False, "anima"
    )
    assert not warnings


def test_no_leaves_is_accepted_as_a_paraphrase_of_without_leaves():
    _, warnings, info = contract.inspect_output(
        "A dragon sits inside a glass bowl with no leaves.",
        "A dragon sits inside a glass bowl without leaves.",
        False,
        "anima",
    )
    assert not warnings
    assert info["missing_lexical_cues"]["negations"] == []
    assert info["missing_relation_details"] == []
