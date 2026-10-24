"""Semantic handoff regressions; generated pixels and LLM behavior are not asserted."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from promptstyler_next import Engine

ROOT = Path(__file__).resolve().parents[1]
SCENES = json.loads((ROOT / "llm-prompts/examples/base-scenes.json").read_text(encoding="utf-8"))["scenes"]


@pytest.fixture(scope="module")
def engine():
    return Engine.builtin()


def all_styles(engine, model=None):
    result = []
    offset = 0
    while True:
        page = engine.list_styles(model=model, limit=1000, offset=offset)
        result.extend(page)
        if len(page) < 1000:
            return result
        offset += len(page)


@pytest.mark.parametrize("model", ["flux", "anima", "fibo"])
def test_semantic_corpus_survives_every_eligible_style(engine, model):
    for index, scene in enumerate(SCENES):
        base = scene["base_prompt"]
        intensity = (0.35, 0.75, 1.0)[index % 3]
        for style in all_styles(engine, model):
            result = engine.compose(
                {
                    "prompt": base,
                    "model": model,
                    "styles": [{"id": style["id"], "intensity": intensity}],
                    "locked_axes": scene["optional_locks"],
                }
            )
            assert result.recipe.prompt == base
            if model == "fibo":
                assert json.loads(result.positive)["short_description"] == base
            else:
                assert result.positive.startswith(base)
            assert not any(
                item.action == "applied" and item.axis in scene["optional_locks"] for item in result.trace
            )


def test_all_bundled_axes_are_declared(engine):
    for style in all_styles(engine):
        versions = [style["clauses"], *(v["clauses"] for v in style["variants"].values())]
        for clauses in versions:
            assert {clause["axis"] for clause in clauses} <= set(style["claims"]), style["id"]


@pytest.mark.parametrize(
    "style_id,removed_content",
    [
        ("liminal.school-hallway", "empty school corridor"),
        ("liminal.office-maze", "empty corporate office"),
        ("liminal.hotel-transition", "empty hotel landing"),
        ("weirdcore.empty-audience", "empty performance documentation"),
        ("dreamcore.mirror-sleep", "repeat existing forms within mirrors"),
        ("netculture.net-art-collage", "mismatched rectangular windows"),
    ],
)
@pytest.mark.parametrize("model", ["flux", "anima"])
def test_reviewed_scene_injection_does_not_return(engine, style_id, removed_content, model):
    result = engine.compose(
        {"prompt": SCENES[0]["base_prompt"], "model": model, "styles": [{"id": style_id}]}
    )
    assert removed_content not in result.positive.lower()


def test_community_palette_can_be_replaced_without_losing_medium(engine):
    result = engine.compose(
        {
            "prompt": SCENES[1]["base_prompt"],
            "model": "flux",
            "styles": [{"id": "netculture.vaporwave-plaza"}, {"id": "grade.sage"}],
        }
    )
    assert any(
        t.style_id == "netculture.vaporwave-plaza" and t.axis == "palette" and t.action == "suppressed"
        for t in result.trace
    )
    assert any(
        t.style_id == "netculture.vaporwave-plaza" and t.axis == "medium" and t.action == "applied"
        for t in result.trace
    )


def test_recipe_examples_are_real_engine_inputs(engine):
    for path in sorted((ROOT / "llm-prompts/examples").glob("recipe-*.json")):
        recipe = json.loads(path.read_text(encoding="utf-8"))
        first = engine.compose(recipe)
        assert first.recipe.prompt == recipe["prompt"]
        assert engine.compose(first.recipe).fingerprint == first.fingerprint


def test_builtin_authoring_audit(engine):
    spec = importlib.util.spec_from_file_location("audit_library", ROOT / "scripts/audit_library.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.audit(engine)
    assert report["entries"] == 1164
    assert report["packs"] == 52
    assert report["authoring_errors"] == []
