"""Style adherence: tiers, per-model budgets, prompt style words and retired IDs."""

from __future__ import annotations

import pytest

from promptstyler_next import Engine, lexicon
from promptstyler_next.adapters import escape_tag, style_phrase
from promptstyler_next.types import Clause


@pytest.fixture(scope="module")
def library():
    return Engine.builtin()


def codes(result):
    return {notice.code for notice in result.warnings}


def applied(result):
    return [t for t in result.trace if t.action == "applied"]


def styled(library, prompt, model, *ids, **extra):
    return library.compose({"prompt": prompt, "model": model, "styles": [{"id": i} for i in ids], **extra})


def test_tiers_add_clauses_progressively(library):
    recipe = {"prompt": "a cat", "model": "flux"}
    counts = [
        len(applied(library.compose({**recipe, "styles": [{"id": "anime.cel", "intensity": x}]})))
        for x in (0.25, 0.5, 1.0)
    ]
    assert counts[0] == 1  # Subtle: identity only
    assert counts[0] < counts[1] < counts[2]


def test_natural_output_is_one_compact_phrase(library):
    result = library.compose({"prompt": "A cat on a sofa", "model": "flux", "styles": [{"id": "anime.cel"}]})
    assert result.positive.startswith("A cat on a sofa. Hand-inked anime cel art, ")
    assert result.positive.endswith(".")
    assert result.positive.count(".") == 2


def test_tag_output_escapes_brackets_and_skips_present_tags(library):
    result = library.compose(
        {"prompt": "1girl, anime coloring", "model": "anima", "styles": [{"id": "anime.watercolor"}]}
    )
    assert "watercolor \\(medium\\)" in result.positive
    assert result.positive.count("anime coloring") == 1
    assert escape_tag("ink (medium)") == "ink \\(medium\\)"
    assert escape_tag("ink \\(medium\\)") == "ink \\(medium\\)"


def test_budget_trims_supporting_tiers_but_keeps_every_identity(library):
    styles = [{"id": i} for i in ("anime.cel", "grade.amber-teal", "frame.close", "detail.economy")]
    result = library.compose({"prompt": "1girl", "model": "anima", "styles": styles})
    budget = result.structured["style_budget"]
    assert budget == {"limit": 10, "unit": "tags", "used": 10}
    assert any(t.action == "budget_skipped" for t in result.trace)
    # Every style keeps its core identity; only supporting tiers are trimmed.
    identities = {t.style_id for t in applied(result)}
    assert {"anime.cel", "grade.amber-teal", "frame.close", "detail.economy"} <= identities
    assert "anime coloring" in result.positive and "close-up" in result.positive


def test_prompt_style_words_are_replaced_by_default(library):
    result = library.compose(
        {
            "prompt": "A photo of a cat on a sofa, cinematic lighting, film grain.",
            "model": "flux",
            "styles": [{"id": "anime.cel"}],
        }
    )
    # anime.cel sets medium, lighting and texture, so all three prompt phrases yield to it.
    assert result.positive.startswith("A cat on a sofa. Hand-inked anime cel art")
    assert "cinematic lighting" not in result.positive and "film grain" not in result.positive
    assert "prompt_style_replaced" in codes(result)
    assert result.recipe.prompt.startswith("A photo of")  # the recipe keeps the user's text


def test_tag_prompt_style_words_are_replaced(library):
    result = styled(library, "1girl, realistic, photorealistic, smile", "anima", "anime.cel")
    assert result.positive.startswith("1girl, smile, ")
    assert "realistic" not in result.positive.split(", ")[:2]


def test_keep_reports_conflict_without_editing_prompt(library):
    prompt = "1girl, watercolor \\(medium\\), smile"
    result = library.compose(
        {"prompt": prompt, "model": "anima", "styles": [{"id": "anime.cel"}], "prompt_conflicts": "keep"}
    )
    assert result.positive.startswith(prompt)
    assert "prompt_style_conflict" in codes(result)


def test_unclaimed_axes_leave_prompt_words_alone(library):
    result = library.compose(
        {"prompt": "A cat, film grain", "model": "flux", "styles": [{"id": "light.rim"}]}
    )
    assert result.positive.startswith("A cat, film grain")


def test_retired_ids_resolve_or_skip_with_notice(library):
    merged = styled(library, "a coat", "flux", "textilecraft.chiffon")
    assert "style_replaced" in codes(merged)
    assert any(t.style_id == "textilecraft.organza" for t in applied(merged))
    gone = styled(library, "a coat", "flux", "hierarchy.counter-space")
    assert "style_retired" in codes(gone) and gone.positive == "a coat"


def test_lettering_is_limited_to_text_capable_models(library):
    styles = {s["id"] for s in library.list_styles(model="anima", category="lettering", limit=100)}
    assert not styles
    assert library.list_styles(model="flux", category="lettering", limit=100)


def test_lexicon_matches_whole_segments_only():
    assert lexicon.axis_of("Watercolor \\(medium\\)") == "medium"
    assert lexicon.axis_of("cinematic lighting") == "lighting"
    assert lexicon.axis_of("a cat with a film camera") is None
    text, removed = lexicon.find_prose("A watercolor painting of a fox in anime style.", {"medium"})
    assert text == "A fox." and len(removed) == 2
    assert lexicon.find_tags("black cat, film grain", {"palette"}) == ("black cat, film grain", [])


def test_style_phrase_dedups_and_capitalizes():
    clauses = (
        Clause("medium", "ink wash", ()),
        Clause("texture", "ink wash", ()),
        Clause("palette", "sepia", ()),
    )
    assert style_phrase(clauses) == "Ink wash, sepia"
