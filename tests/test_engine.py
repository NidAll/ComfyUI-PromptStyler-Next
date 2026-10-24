from __future__ import annotations

import dataclasses
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from promptstyler_next import Layer, Recipe, StylerError
from promptstyler_next.adapters import NaturalAdapter


def recipe(**changes):
    return {
        "prompt": 'A botanist with a sign reading "ROOF 7"\nunder rain',
        "styles": [{"id": "test.ink"}],
        **changes,
    }


def test_user_prompt_is_preserved_verbatim(engine):
    request = recipe()
    result = engine.compose(request)
    assert result.positive.startswith(request["prompt"])
    assert result.recipe.prompt == request["prompt"]
    assert len(result.fingerprint) == 64
    assert result.to_dict()["structured"]["subject"] == request["prompt"]


def test_zero_and_empty_are_exact_bypasses(engine):
    prompt = "  A  cat\n (soft:1.2) <lora:mine:0.8>  "
    assert engine.compose({"prompt": prompt}).positive == prompt
    assert (
        engine.compose(recipe(prompt=prompt, styles=[{"id": "test.ink", "intensity": 0}])).positive == prompt
    )


def test_intensity_is_clause_gating_not_fake_token_weighting(engine):
    outputs = [
        engine.compose(recipe(styles=[{"id": "test.ink", "intensity": x}])).positive for x in (0.1, 0.5, 1)
    ]
    assert "monochrome" not in outputs[0]
    assert "monochrome" in outputs[1]
    assert "paper fibers" not in outputs[1]
    assert "paper fibers" in outputs[2]


@pytest.mark.parametrize(
    "policy,retained,suppressed",
    [("first_wins", "monochrome", "amber"), ("last_wins", "amber", "monochrome")],
)
def test_conflict_is_axis_local(engine, policy, retained, suppressed):
    result = engine.compose(recipe(conflict_policy=policy, styles=[{"id": "test.ink"}, {"id": "test.warm"}]))
    assert retained in result.positive
    assert suppressed not in result.positive
    assert "ink contours" in result.positive
    assert "paper fibers" in result.positive
    assert any(item.action == "suppressed" for item in result.trace)


def test_conflict_error_and_locked_axis(engine):
    data = recipe(conflict_policy="error", styles=[{"id": "test.ink"}, {"id": "test.warm"}])
    with pytest.raises(StylerError, match="palette") as failure:
        engine.compose(data)
    assert failure.value.code == "style_conflict"
    result = engine.compose({**data, "locked_axes": ["palette"]})
    assert "amber" not in result.positive
    assert "monochrome" not in result.positive


def test_inactive_claim_does_not_suppress_active_palette(engine):
    result = engine.compose(recipe(styles=[{"id": "test.warm"}, {"id": "test.ink", "intensity": 0.1}]))
    assert "amber" in result.positive


def test_tag_adapter_never_rewrites_subject(engine):
    result = engine.compose(recipe(model="anima"))
    assert result.positive.startswith(recipe()["prompt"] + ", ")
    assert "ink drawing" in result.positive
    assert "Use carved" not in result.positive


def test_generic_and_unknown_profiles_explicitly_omit_negatives(engine):
    result = engine.compose(recipe(model="my-unknown-checkpoint", negative="people"))
    assert result.profile == "generic"
    assert result.negative == ""
    assert result.recipe.negative == "people"
    assert {item.code for item in result.warnings} == {"unknown_model", "negative_unsupported"}


def test_profile_alias_and_restricted_styles(engine):
    result = engine.compose(recipe(model="XL", negative="text", styles=[{"id": "test.sdxl"}]))
    assert result.profile == "sdxl"
    assert result.negative == "text, blur"
    with pytest.raises(StylerError) as failure:
        engine.compose(recipe(styles=[{"id": "test.sdxl"}]))
    assert failure.value.code == "unsupported_style"


def test_deduplication_is_explained(engine):
    result = engine.compose(recipe(styles=[{"id": "test.ink"}, {"id": "test.duplicate"}]))
    assert result.positive.count("paper fibers") == 1
    assert any(item.action == "deduplicated" for item in result.trace)


def test_fibo_emits_native_caption_mapping_without_invented_objects(engine):
    result = engine.compose(recipe(model="fibo"))
    caption = json.loads(result.positive)
    assert caption["short_description"] == recipe()["prompt"]
    assert caption["style_medium"] == "Use carved ink contours"
    assert caption["aesthetics"]["color_scheme"] == "Keep the palette monochrome"
    assert "objects" not in caption
    assert "text_render" not in caption


def test_existing_fibo_fields_are_automatically_protected(engine):
    caption = {
        "short_description": "An orchid",
        "style_medium": "oil on canvas",
        "aesthetics": {"color_scheme": "green"},
        "objects": [{"description": "A vase", "location": "center"}],
        "text_render": [],
    }
    result = engine.compose(recipe(prompt=json.dumps(caption), model="fibo"))
    styled = json.loads(result.positive)
    assert all(styled[key] == value for key, value in caption.items())
    assert set(result.structured["protected_axes"]) == {"medium", "palette"}


def test_malformed_fibo_objects_fail_actionably(engine):
    with pytest.raises(StylerError, match="lighting"):
        engine.compose({"prompt": '{"lighting":"side"}', "model": "fibo"})


def test_replay_and_thread_safety(engine):
    data = recipe()
    first = engine.compose(data)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: engine.compose(data).to_dict(), range(64)))
    assert all(value == first.to_dict() for value in results)
    assert engine.compose(first.recipe).to_dict() == first.to_dict()
    changed = engine.compose(recipe(styles=[{"id": "test.ink", "intensity": 0.7}]))
    assert changed.fingerprint != first.fingerprint


def test_public_results_are_independent_copies(engine):
    result = engine.compose(recipe())
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.positive = "mutation"
    snapshot = result.to_dict()
    snapshot["recipe"]["styles"].clear()
    snapshot["structured"]["axes"].clear()
    assert result.recipe.styles
    assert result.structured["axes"]
    meta = engine.get_style("test.ink")
    meta["clauses"].clear()
    assert engine.get_style("test.ink")["clauses"]


def test_registration_changes_catalog_identity_without_core_edits(engine):
    from conftest import make_profile

    profile = make_profile("my-model", aliases=["mine"])
    extended = engine.with_adapter(profile, NaturalAdapter(revision="custom/2"))
    assert extended.catalog_fingerprint != engine.catalog_fingerprint
    assert extended.compose(recipe(model="mine")).profile == "my-model"
    assert engine.compose(recipe(model="mine")).profile == "generic"


def test_discovery_uses_tokens_and_all_filters(engine):
    result = engine.list_styles(
        query="ink botanical", category="illustration", model="generic", tags=["ink"], kind="style"
    )
    assert [style["id"] for style in result] == ["test.ink"]
    assert not engine.list_styles(query="missing-word")
    assert len(engine.list_styles(limit=1, offset=1)) == 1
    assert len(engine.list_styles(model="XL")) == 4
    assert len(engine.list_styles(model="generic")) == 3


def test_recommendation_is_reproducible_and_explains_metadata(engine):
    result = engine.recommend(prompt="botanical ink", limit=2)
    assert result == engine.recommend(prompt="botanical ink", limit=2)
    assert len(result) == 2
    assert result[0]["score"] > 0
    assert "Metadata matches" in result[0]["reasons"][0]
    assert engine.recommend(prompt="") == []


@pytest.mark.parametrize(
    "changes",
    [
        {"prompt": 3},
        {"negative": []},
        {"model": ""},
        {"conflict_policy": "magic"},
        {"styles": [{"id": "test.ink", "intensity": True}]},
        {"styles": [{"id": "test.ink", "intensity": float("nan")}]},
        {"styles": [{"id": "test.ink", "intensity": 1.1}]},
        {"styles": [{"id": "test.ink"}] * 2},
        {"styles": [{"id": "missing.style"}]},
        {"locked_axes": ["subject"]},
        {"schema_version": True},
        {"extra": "unexpected"},
    ],
)
def test_bad_recipes_are_rejected(engine, changes):
    with pytest.raises(StylerError):
        engine.compose(recipe(**changes))


def test_dataclass_contract_validates_direct_callers(engine):
    assert engine.compose(Recipe("Cat", styles=(Layer("test.ink", 0.5),))).positive.startswith("Cat")
    with pytest.raises(StylerError):
        Recipe("Cat", styles=[])
    with pytest.raises(StylerError):
        Layer("../escape")
