from __future__ import annotations

import json
from collections import Counter
from importlib.resources import files

import pytest

from promptstyler_next import Engine


@pytest.fixture(scope="module")
def library_engine():
    return Engine.builtin()


def all_styles(engine, **filters):
    result = []
    offset = 0
    while True:
        page = engine.list_styles(**filters, limit=1000, offset=offset)
        result.extend(page)
        if len(page) < 1000:
            return result
        offset += len(page)


def test_library_has_distinct_identities_and_meaningful_growth(library_engine):
    styles = all_styles(library_engine)
    assert len(styles) == 1164
    for key in ("id", "name", "description"):
        counts = Counter(style[key] for style in styles)
        assert not [value for value, count in counts.items() if count > 1], key
    primary_texts = [library_engine.get_style(style["id"])["clauses"][0]["text"] for style in styles]
    assert len(primary_texts) == len(set(primary_texts))
    assert Counter(style["kind"] for style in styles) == {"style": 1017, "grade": 69, "modifier": 78}


def test_library_clauses_have_progressive_authored_detail(library_engine):
    forbidden = ("masterpiece", "best quality", "ultra detailed", "award winning", "8k", "16k")
    for metadata in all_styles(library_engine):
        style = library_engine.get_style(metadata["id"])
        clauses = style["clauses"]
        assert len(clauses) >= 2, style["id"]
        assert all(clause["tags"] for clause in clauses), style["id"]
        assert len({clause["min_intensity"] for clause in clauses}) >= 2, style["id"]
        text = " ".join(clause["text"] for clause in clauses).casefold()
        assert not any(term in text for term in forbidden), style["id"]
        assert not style["negative"], style["id"]


def test_profile_capabilities_are_explicit(library_engine):
    profiles = {profile["id"]: profile for profile in library_engine.profiles()}
    assert set(profiles) == {
        "generic",
        "sdxl",
        "flux",
        "qwen-image",
        "qwen-image-2.1",
        "moss-image",
        "moss-image-dmd",
        "anima",
        "anima-turbo",
        "fibo",
        "fibo-edit",
    }
    for profile in profiles.values():
        if profile["id"] != "generic":
            assert profile["sources"]
        assert profile["evidence"] in {"documented", "conservative"}
    for profile_id in ("flux", "generic", "qwen-image-2.1", "moss-image-dmd", "anima-turbo", "fibo"):
        assert profiles[profile_id]["negative"] is False
    assert profiles["anima"]["format"] == "tags"
    assert profiles["anima"]["weighting"] is False
    assert profiles["fibo"]["format"] == "structured"


@pytest.mark.parametrize(
    "model",
    [
        "generic",
        "sdxl",
        "flux",
        "qwen-image",
        "qwen-image-2.1",
        "moss-image",
        "moss-image-dmd",
        "anima",
        "anima-turbo",
        "fibo",
        "fibo-edit",
    ],
)
def test_every_eligible_style_composes_without_losing_the_subject(library_engine, model):
    prompt = 'A blue ceramic teapot with the exact lettering "TEA 7"\non a plain shelf'
    for style in all_styles(library_engine, model=model):
        result = library_engine.compose({"prompt": prompt, "model": model, "styles": [{"id": style["id"]}]})
        if model == "fibo":
            assert json.loads(result.positive)["short_description"] == prompt
        else:
            assert result.positive.startswith(prompt)
        assert result.recipe.prompt == prompt
        assert len(result.fingerprint) == 64


def test_photographic_packs_do_not_claim_anima_realism(library_engine):
    for model in ("anima", "anima-turbo"):
        styles = all_styles(library_engine, model=model)
        assert not any(style["id"].startswith(("photo.", "documentary.")) for style in styles)
        assert any(style["id"] == "cinema.noir" for style in styles)
    noir = library_engine.get_style("cinema.noir")
    assert set(noir["variants"]) == {"anima", "anima-turbo"}
    result = library_engine.compose(
        {"prompt": "A teapot", "model": "anima", "styles": [{"id": "cinema.noir"}]}
    )
    assert "anime keyframe" in result.positive
    assert "film still" not in result.positive


def test_builtin_license_metadata_is_consistent():
    for path in files("promptstyler_next").joinpath("packs").iterdir():
        if path.name.endswith(".json"):
            pack = json.loads(path.read_text(encoding="utf-8"))
            assert pack["license"] == "CC0-1.0"
            assert pack["schema_version"] == 1


def test_real_monochrome_look_can_accept_a_color_grade(library_engine):
    for model in ("flux", "anima"):
        result = library_engine.compose(
            {"prompt": "A teapot", "model": model, "styles": [{"id": "cinema.noir"}, {"id": "grade.sage"}]}
        )
        assert not any(
            item.action == "applied" and item.style_id == "cinema.noir" and item.axis == "palette"
            for item in result.trace
        )
        assert any(
            item.action == "applied" and item.style_id == "cinema.noir" and item.axis == "medium"
            for item in result.trace
        )
        assert "black-and-white" not in result.positive
        assert "black and white" not in result.positive


def test_full_looks_cannot_silently_keep_incompatible_materials(library_engine):
    result = library_engine.compose(
        {
            "prompt": "A bird",
            "model": "flux",
            "styles": [{"id": "material.embroidery"}, {"id": "material.tapestry"}],
        }
    )
    assert any(
        item.style_id == "material.embroidery" and item.axis == "medium" and item.action == "suppressed"
        for item in result.trace
    )
    assert any(
        item.style_id == "material.embroidery" and item.axis == "texture" and item.action == "suppressed"
        for item in result.trace
    )
    assert any(
        item.style_id == "material.tapestry" and item.axis == "medium" and item.action == "applied"
        for item in result.trace
    )


def test_builtin_hard_palette_constraints_have_their_own_axis(library_engine):
    import re

    for style in all_styles(library_engine):
        for clause in style["clauses"]:
            if re.search(r"\b(monochrome|black[- ]and[- ]white|grayscale|greyscale)\b", clause["text"], re.I):
                assert clause["axis"] == "palette", (style["id"], clause)
