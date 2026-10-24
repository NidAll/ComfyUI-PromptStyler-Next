from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "promptstyler_next"


def validator(name):
    schema = json.loads((DATA / "schemas" / f"{name}.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def test_schema_generation_is_reproducible():
    before = {path: path.read_bytes() for path in (DATA / "schemas").glob("*.json")}
    subprocess.run([sys.executable, str(ROOT / "scripts" / "write_schemas.py")], check=True)
    assert before == {path: path.read_bytes() for path in before}


def test_every_pack_and_profile_matches_public_schema():
    pack_validator = validator("pack")
    for path in (DATA / "packs").glob("*.json"):
        pack_validator.validate(json.loads(path.read_text()))
    validator("profiles").validate(json.loads((DATA / "profiles.json").read_text()))
    validator("recipe").validate(json.loads((ROOT / "examples" / "recipe.json").read_text()))


def test_documented_custom_pack_is_validated_by_both_contracts():
    from promptstyler_next.catalog import Pack

    doc = (ROOT / "docs" / "packs.md").read_text()
    block = re.search(r"```json\n(.*?)\n```", doc, re.S).group(1)
    value = json.loads(block)
    validator("pack").validate(value)
    assert Pack.from_dict(value).id == "community.botanical"


def test_schema_and_runtime_reject_common_invalid_recipes():
    from promptstyler_next import Recipe, StylerError

    values = [
        {"prompt": 3},
        {"prompt": "x", "styles": [{"id": "x", "intensity": 2}]},
        {"prompt": "x", "locked_axes": ["subject"]},
        {"prompt": "x", "extra": True},
        {"prompt": "x", "schema_version": 2},
    ]
    check = validator("recipe")
    for value in values:
        assert list(check.iter_errors(value))
        with pytest.raises(StylerError):
            Recipe.from_dict(value)
