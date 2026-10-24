from __future__ import annotations

import json

import pytest
from conftest import make_pack, make_profile, make_style

from promptstyler_next import Engine, StylerError
from promptstyler_next.adapters import AdapterRegistry, FiboAdapter, NaturalAdapter, Profile, TagAdapter
from promptstyler_next.catalog import Pack
from promptstyler_next.types import Clause


def test_exact_variant_is_selected_without_cross_profile_leakage():
    style = make_style(
        variants={
            "anima": {
                "clauses": [
                    {"axis": "medium", "text": "Use clean animated contours", "tags": ["cel shading"]},
                    {"axis": "palette", "text": "Use two ink values", "tags": ["limited palette"]},
                ],
                "negative": ["halftone"],
            }
        }
    )
    engine = Engine(
        [Pack.from_dict(make_pack([style]))],
        AdapterRegistry([make_profile(), make_profile("anima", format="tags", negative=True)]),
    )
    result = engine.compose({"prompt": "bird", "model": "anima", "styles": [{"id": "test.ink"}]})
    assert result.positive == "bird, cel shading, limited palette"
    assert result.negative == "halftone"
    assert all(item.reason == "Model-specific variant." for item in result.trace)
    generic = engine.compose({"prompt": "bird", "styles": [{"id": "test.ink"}]})
    assert "cel shading" not in generic.positive


def test_stale_claims_unknown_profiles_and_alias_collisions_fail():
    registry = AdapterRegistry([make_profile()])
    for style in [
        make_style(models=["missing"]),
        make_style(claims={"lighting": "daylight"}),
        make_style(variants={"generic": {"clauses": [{"axis": "medium", "text": "ink", "tags": []}]}}),
    ]:
        with pytest.raises(StylerError):
            Engine([Pack.from_dict(make_pack([style]))], registry)
    with pytest.raises(StylerError, match="unique"):
        AdapterRegistry([make_profile(), make_profile("other", aliases=["GENERIC"])])


@pytest.mark.parametrize(
    "change",
    [
        {"negative": 1},
        {"weighting": "true"},
        {"format": "chat"},
        {"sources": ["file:///x"]},
        {"conditioning": "guess"},
        {"evidence": "proven"},
        {"name": ""},
    ],
)
def test_profile_validation(change):
    with pytest.raises(StylerError):
        Profile.from_dict({**make_profile().to_dict(), **change})


def test_fibo_omits_unspecified_scene_fields_and_combines_only_style_text():
    adapter = FiboAdapter()
    result = json.loads(
        adapter.render(
            "a kettle",
            (
                Clause("texture", "Dry pigment", ()),
                Clause("detail", "Fine glazing", ()),
                Clause("lighting", "Diffuse side light", ()),
            ),
        )
    )
    assert result == {
        "short_description": "a kettle",
        "artistic_style": "Dry pigment Fine glazing",
        "lighting": {"conditions": "Diffuse side light"},
    }
    assert adapter.locked_axes('{"artistic_style":""}') == ("texture", "detail")


def test_renderers_leave_subject_and_encoder_syntax_untouched():
    prompt = '(cat:1.2) <lora:name:0.7> {literal}\n"exact text"'
    clauses = (Clause("medium", "Render in pastel", ("pastel drawing",)),)
    assert NaturalAdapter().render(prompt, clauses).startswith(prompt)
    assert TagAdapter().render(prompt, clauses) == prompt + ", pastel drawing"
    assert NaturalAdapter().render("", clauses) == "Render in pastel."


@pytest.mark.parametrize(
    "caption",
    [
        {"style_medium": 3},
        {"short_description": []},
        {"artistic_style": False},
        {"lighting": {"conditions": []}},
        {"aesthetics": {"color_scheme": {}}},
    ],
)
def test_known_fibo_style_fields_require_native_string_types(caption):
    with pytest.raises(StylerError):
        FiboAdapter().render(json.dumps(caption), ())
