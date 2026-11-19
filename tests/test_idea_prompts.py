"""Model-free checks of the prompt-idea exploration contract."""

import importlib.util
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "idea_prompts", Path(__file__).resolve().parents[1] / "comfyui/upscaler/idea_prompts.py"
)
idea = importlib.util.module_from_spec(spec)
# Dataclasses resolve their module through sys.modules.
sys.modules[spec.name] = idea
spec.loader.exec_module(idea)


def text_of(chat):
    return chat[-1]["content"][0]["text"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"prompt": " "},
        {"prompt": "x" * 6001},
        {"exploration": "faithful"},
        {"detail": "huge"},
        {"target_model": "sdxl"},
        {"lens": "nope"},
        {"structure": "nope"},
        {"temperature": 2.0},
        {"avoid": "x" * 8001},
        {"recent": "x" * 601},
        {"max_new_tokens": 10},
    ],
)
def test_validation_refuses_out_of_contract_inputs(arguments):
    with pytest.raises(ValueError):
        idea.validate(**{"prompt": "a fox", **arguments})


def test_validation_trims_and_accepts_defaults():
    assert idea.validate("  a fox  ") == "a fox"
    assert idea.validate("a fox", "wild", "detailed", "krea2", "light", "layered", 0.0, "", "", 256) == "a fox"


def test_plan_is_seeded_and_skips_recent_keys():
    first = idea.plan(7, "explore", "balanced")
    assert first["lenses"] == idea.plan(7, "explore", "balanced")["lenses"]
    recent = ",".join(lens.key for lens in idea.LENSES[:-2]) + "," + ",".join(s.key for s in idea.STRUCTURES[:-1])
    for seed in range(40):
        chosen = idea.plan(seed, "explore", "balanced", recent=recent)
        assert [lens.key for lens in chosen["lenses"]] == [idea.LENSES[-2].key]
        assert chosen["structure"].key == idea.STRUCTURES[-1].key


def test_explore_uses_one_scene_lens_and_wild_combines_a_bold_lens():
    for seed in range(60):
        explore = idea.plan(seed, "explore", "balanced")
        wild = idea.plan(seed, "wild", "balanced")
        assert len(explore["lenses"]) == 1 and explore["lenses"][0].key != "medium"
        assert [lens.bold for lens in wild["lenses"]] == [True, False]
        assert len(wild["sparks"]) == 6 and wild["concepts"] == 4
    assert {idea.plan(seed, "explore", "balanced")["lenses"][0].key for seed in range(200)} >= {"setting", "light", "viewpoint"}


def test_explicit_lens_and_structure_are_honoured():
    chosen = idea.plan(3, "explore", "concise", lens="palette", structure="photo_brief")
    assert chosen["lenses"][0].key == "palette" and chosen["structure"].key == "photo_brief"
    assert set(chosen["sparks"]) <= set(idea.LENS_BY_KEY["palette"].sparks)


def test_brainstorm_request_carries_draft_lens_sparks_and_earlier_ideas():
    chosen = idea.plan(1, "explore", "balanced", lens="light")
    chat = idea.brainstorm_messages('A cat on a sign reading "OPEN"', "explore", chosen, ["a cat under neon"])
    request = text_of(chat)
    assert 'Draft: A cat on a sign reading "OPEN"' in request
    assert idea.LENS_BY_KEY["light"].instruction in request
    assert all(spark in request for spark in chosen["sparks"])
    assert "- a cat under neon" in request and "Number them 1 to 3" in request


def test_develop_request_sets_structure_length_target_and_keeps_constraints():
    chosen = idea.plan(1, "wild", "detailed", structure="layered")
    request = text_of(idea.develop_messages("two owls, no moon", "wild", "detailed", "moss_image", chosen, "owls in a library"))
    system = idea.develop_messages("two owls", "wild", "detailed", "moss_image", chosen, "x")[0]["content"]
    assert "Concept: owls in a library" in request and idea.STRUCTURE_BY_KEY["layered"].instruction in request
    assert "6 to 9 sentences, 130 to 180 words" in request and "their number" in request
    assert "MOSS Image" in system and "Output only the prompt" in system
    fallback = text_of(idea.develop_messages("two owls", "wild", "detailed", "general", chosen, ""))
    assert "Concept:" not in fallback and "Explore:" in fallback


def test_long_drafts_get_room_instead_of_being_cut_down():
    long = " ".join(["word"] * 150)
    assert idea.words_for("concise", long) == (150, 190)
    assert idea.token_budget("concise", long) > idea.token_budget("concise", "a fox")
    assert idea.token_budget("balanced", "a fox", 512) == 512


def test_concepts_are_parsed_from_numbered_or_bulleted_lines():
    raw = "Here are ideas:\n1. A fox naps in a greenhouse full of tomatoes.\n2) **Concept:** A fox reads by lamplight in a barn\n- short one\n3 - A fox crosses a frozen harbor at dawn."
    assert idea.parse_concepts(raw) == [
        "A fox naps in a greenhouse full of tomatoes.",
        "A fox reads by lamplight in a barn",
        "A fox crosses a frozen harbor at dawn.",
    ]


def test_novelty_ignores_the_draft_words_every_idea_keeps():
    draft = "a red fox in a snowy forest"
    earlier = ["a red fox naps beside a frozen waterfall under aurora light"]
    assert idea.novelty("a red fox runs through a snowy forest at dawn", earlier, draft) == 1.0
    assert idea.novelty("a red fox sleeps near the frozen waterfall under the aurora", earlier, draft) <= 0.4


def test_concept_ranking_prefers_kept_subject_then_novelty():
    draft = "a lighthouse keeper feeding a whale"
    concepts = [
        "A lighthouse keeper feeds a whale beside a frozen waterfall at dawn.",
        "A dragon sleeps on a mountain of gold coins in a cave.",
        "A lighthouse keeper feeds a whale from a rowboat under paper lanterns.",
    ]
    ranked = idea.rank_concepts(concepts, ["keeper feeds whale beside a frozen waterfall at dawn"], draft, "explore", 5)
    assert [item[0] for item in ranked] == [concepts[2], concepts[0], concepts[1]]


def test_cleaning_strips_labels_markup_quality_tags_and_cut_endings():
    raw = '**Final prompt:** "A fox sleeps in moss, masterpiece, 8k.\nGolden light falls on its fur. It dreams of'
    text, warnings = idea.clean_idea(raw, truncated=True)
    assert text == "A fox sleeps in moss. Golden light falls on its fur."
    assert warnings == []
    assert idea.clean_idea("Prompt: A fox", False)[0] == "A fox"
    with pytest.raises(RuntimeError):
        idea.clean_idea("A fox <|im_end|>", False)


def test_missing_quoted_text_is_restored_verbatim():
    text, missing = idea.restore_quotes("A shop at night.", 'A shop with a sign "OPEN 24/7"')
    assert missing == ["OPEN 24/7"] and text.endswith('The words "OPEN 24/7" are clearly visible.')
    kept, none = idea.restore_quotes("A sign says “OPEN 24/7”.", 'A shop with a sign "OPEN 24/7"')
    assert none == [] and kept == "A sign says “OPEN 24/7”."


def test_assessment_flags_drift_shortness_and_repeats_and_reports_invented_text():
    draft = "portrait of an old woman"
    good = idea.assess("An elderly woman sits for a portrait by a window, " * 8, draft, "explore", "balanced", [])
    assert good["issues"] == [] and good["coverage"] == 1.0
    drift = idea.assess("A dragon flies over a burning castle at night. " * 10, draft, "explore", "balanced", [])
    assert "lost_subject" in drift["issues"]
    assert "too_short" in idea.assess("An old woman.", draft, "explore", "balanced", [])["issues"]
    earlier = ["old woman knitting a red scarf beside a crackling fireplace with a sleeping cat"]
    repeat = idea.assess("Portrait of an old woman knitting a red scarf by a crackling fireplace, a cat sleeping. " * 4,
                         draft, "explore", "balanced", earlier)
    assert "repeat" in repeat["issues"]
    assert idea.assess('An old woman holds a sign "HELLO".', draft, "wild", "concise", [])["invented_text"] == ["HELLO"]


def test_bias_words_are_recurring_additions_not_draft_or_stock_words():
    avoid = ["a keeper in a navy coat on a cliff", "the keeper wears a navy cap near a cliff", "weathered keeper, weathered pier"]
    words = idea.bias_words(avoid, "a lighthouse keeper")
    assert "navy" in words and "cliff" in words
    assert "keeper" not in words and "weathered" not in words and "coat" not in words


def test_earlier_ideas_are_listed_without_their_quoted_words_and_subject_swaps_are_ruled_out():
    chosen = idea.plan(2, "explore", "balanced")
    earlier = ['The keeper feeds the whale at dusk, murmuring "Home finds us."']
    request = text_of(idea.brainstorm_messages("a lighthouse keeper feeding a whale", "explore", chosen, earlier))
    assert "Home finds us" not in request and "- The keeper feeds the whale at dusk" in request
    assert "same main subject" in request and "no dialogue" in request
    # A concept that swaps the whale for a dolphin ranks below one that keeps it.
    ranked = idea.rank_concepts(["A keeper serves a dolphin at a cliffside lighthouse under the moon.",
                                 "A keeper feeds a whale from a lighthouse balcony under the moon."],
                                [], "a lighthouse keeper feeding a whale", "explore", 1)
    assert "whale" in ranked[0][0]
    assert idea.validate("a fox", earlier="x" * 100) == "a fox"
    with pytest.raises(ValueError):
        idea.validate("a fox", earlier="x" * 12001)
