"""Properties over arbitrary Unicode and layer combinations, not just golden strings."""

from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from promptstyler_next import Layer, Recipe  # noqa: E402

text = st.text(alphabet=st.characters(blacklist_categories=("Cs", "Cc")), max_size=400)


@settings(max_examples=160, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(prompt=text, intensity=st.floats(min_value=0, max_value=1, allow_nan=False))
def test_preservation_determinism_and_roundtrip(engine, prompt, intensity):
    recipe = Recipe(prompt, styles=(Layer("test.ink", intensity),))
    result = engine.compose(recipe)
    assert result.positive.startswith(prompt)
    assert engine.compose(recipe).to_dict() == result.to_dict()
    assert engine.compose(result.recipe.to_dict()).fingerprint == result.fingerprint


@settings(max_examples=80, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(prompt=text, axes=st.lists(st.sampled_from(["medium", "palette", "texture"]), unique=True))
def test_locked_axes_are_never_emitted(engine, prompt, axes):
    result = engine.compose(Recipe(prompt, styles=(Layer("test.ink"),), locked_axes=tuple(axes)))
    assert not set(result.structured["axes"]) & set(axes)


@settings(max_examples=80, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(prompt=text)
def test_zero_strength_is_an_exact_identity(engine, prompt):
    result = engine.compose(Recipe(prompt, styles=(Layer("test.ink", 0),)))
    assert result.positive == prompt
