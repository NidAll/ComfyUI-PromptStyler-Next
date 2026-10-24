"""Regressions from independent public-contract and semantic-layering review."""

from __future__ import annotations

import pytest

from promptstyler_next import Engine, StylerError
from promptstyler_next.adapters import AdapterRegistry, Profile
from promptstyler_next.catalog import Pack
from promptstyler_next.validation import parse_json


@pytest.mark.parametrize("digits", [4000, 5000])
def test_large_integer_intensity_is_a_domain_error(digits: int) -> None:
    payload = '{"prompt":"bird","styles":[{"id":"cinema.noir","intensity":' + "9" * digits + "}]}"
    with pytest.raises(StylerError):
        Engine.builtin().compose(parse_json(payload))


def test_direct_python_huge_integer_intensity_is_a_domain_error() -> None:
    with pytest.raises(StylerError) as failure:
        Engine.builtin().compose({"prompt": "bird", "styles": [{"id": "cinema.noir", "intensity": 10**4000}]})
    assert failure.value.code == "invalid_intensity"


@pytest.mark.parametrize("scenario", ["conflict", "locked", "intensity"])
def test_partial_style_conflict_cannot_leave_contradictory_unscoped_negatives(scenario: str) -> None:
    pack = Pack.from_dict(
        {
            "schema_version": 1,
            "id": "review.pack",
            "version": "1.0.0",
            "name": "Review fixture",
            "description": "Palette conflict with a style-wide exclusion.",
            "license": "CC0-1.0",
            "author": "Review",
            "styles": [
                {
                    "id": "review.monochrome",
                    "name": "Monochrome photograph",
                    "description": "Photographic monochrome.",
                    "category": "review/photo",
                    "kind": "style",
                    "tags": ["photo"],
                    "claims": {"medium": "photography", "palette": "monochrome"},
                    "clauses": [
                        {"axis": "medium", "text": "Photographic rendering", "tags": ["photograph"]},
                        {
                            "axis": "palette",
                            "text": "Use black and white",
                            "tags": ["monochrome"],
                            "min_intensity": 0.5,
                        },
                    ],
                    "negative": ["color"],
                },
                {
                    "id": "review.amber",
                    "name": "Amber palette",
                    "description": "An amber color grade.",
                    "category": "review/grade",
                    "kind": "grade",
                    "tags": ["amber"],
                    "claims": {"palette": "amber"},
                    "clauses": [
                        {"axis": "palette", "text": "Use an amber color palette", "tags": ["amber palette"]}
                    ],
                },
            ],
        }
    )

    def profile(profile_id: str, negative: bool) -> Profile:
        return Profile.from_dict(
            {
                "id": profile_id,
                "name": profile_id,
                "format": "natural",
                "negative": negative,
                "weighting": False,
                "conditioning": "clip",
                "guidance": "Test profile.",
                "sources": [],
                "evidence": "conservative",
            }
        )

    engine = Engine([pack], AdapterRegistry([profile("generic", False), profile("sdxl", True)]))
    result = engine.compose(
        {
            "prompt": "A blue bird",
            "negative": "cropped wings",
            "model": "sdxl",
            "styles": [{"id": "review.monochrome", "intensity": 0.1}]
            if scenario == "intensity"
            else [{"id": "review.monochrome"}]
            if scenario == "locked"
            else [{"id": "review.monochrome"}, {"id": "review.amber"}],
            "locked_axes": ["palette"] if scenario == "locked" else [],
        }
    )
    assert "Photographic rendering" in result.positive
    if scenario == "conflict":
        assert "amber color palette" in result.positive
    else:
        assert result.positive.startswith("A blue bird")
    assert "black and white" not in result.positive
    assert result.negative == "cropped wings"
    assert any(notice.code == "negative_conflict_omitted" for notice in result.warnings)
    assert any(
        item.style_id == "review.monochrome" and item.action == "negative_skipped" for item in result.trace
    )
