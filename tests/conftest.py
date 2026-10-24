from __future__ import annotations

import pytest

from promptstyler_next import Engine
from promptstyler_next.adapters import AdapterRegistry, Profile
from promptstyler_next.catalog import Pack


def make_style(style_id="test.ink", **changes):
    style = {
        "id": style_id,
        "name": "Ink study",
        "description": "Crisp ink illustration with restrained color.",
        "category": "illustration/ink",
        "kind": "style",
        "tags": ["ink", "botanical"],
        "claims": {"medium": "ink", "palette": "monochrome"},
        "clauses": [
            {
                "axis": "medium",
                "text": "Use carved ink contours",
                "tags": ["ink drawing"],
                "min_intensity": 0,
            },
            {
                "axis": "palette",
                "text": "Keep the palette monochrome",
                "tags": ["monochrome"],
                "min_intensity": 0.4,
            },
            {
                "axis": "texture",
                "text": "Reveal paper fibers",
                "tags": ["paper texture"],
                "min_intensity": 0.8,
            },
        ],
    }
    return {**style, **changes}


def make_pack(styles=None, **changes):
    return {
        "schema_version": 1,
        "id": "test.pack",
        "version": "1.0.0",
        "name": "Test library",
        "description": "A deliberately small test fixture.",
        "license": "CC0-1.0",
        "author": "Test author",
        "styles": [make_style()] if styles is None else styles,
        **changes,
    }


def make_profile(profile_id="generic", **changes):
    return Profile.from_dict(
        {
            "id": profile_id,
            "name": profile_id.title(),
            "format": "natural",
            "negative": False,
            "weighting": False,
            "conditioning": "specialized",
            "guidance": "Test policy only.",
            "sources": [],
            "evidence": "conservative",
            "aliases": [],
            **changes,
        }
    )


@pytest.fixture
def engine():
    warm = make_style(
        "test.warm",
        name="Amber grade",
        kind="grade",
        claims={"palette": "amber"},
        clauses=[{"axis": "palette", "text": "Use amber highlights", "tags": ["amber palette"]}],
        tags=["amber", "warm"],
    )
    duplicate = make_style(
        "test.duplicate",
        name="Paper texture",
        kind="modifier",
        claims={},
        clauses=[{"axis": "texture", "text": "Reveal paper fibers", "tags": ["paper texture"]}],
    )
    restricted = make_style("test.sdxl", name="SDXL only", models=["sdxl"], negative=["blur"])
    profiles = [
        make_profile(),
        make_profile("sdxl", negative=True, conditioning="clip", aliases=["XL"]),
        make_profile("anima", format="tags"),
        make_profile("fibo", format="structured"),
    ]
    return Engine(
        [Pack.from_dict(make_pack([make_style(), warm, duplicate, restricted]))], AdapterRegistry(profiles)
    )
