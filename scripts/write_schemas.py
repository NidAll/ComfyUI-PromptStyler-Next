"""Generate editor-facing JSON Schema contracts; runtime validation has no dependencies."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "promptstyler_next" / "schemas"
AXES = ["medium", "lighting", "palette", "composition", "texture", "mood", "detail"]
IDENTIFIER = {"type": "string", "maxLength": 96, "pattern": "^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"}
TEXT = {"type": "string", "minLength": 1, "maxLength": 512}
UNIT = {"type": "number", "minimum": 0, "maximum": 1}


def strings(length=96, maximum=32):
    return {
        "type": "array",
        "items": {"type": "string", "minLength": 1, "maxLength": length},
        "uniqueItems": True,
        "maxItems": maximum,
    }


def obj(properties, required):
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


clause = obj(
    {
        "axis": {"enum": AXES},
        "text": {"type": "string", "minLength": 1, "maxLength": 1024},
        "tags": strings(192, 24),
        "min_intensity": UNIT,
    },
    ["axis", "text", "tags"],
)
clauses = {"type": "array", "items": clause, "minItems": 1, "maxItems": 32}
variant = obj({"clauses": clauses, "negative": strings(512)}, ["clauses"])
style = obj(
    {
        "id": IDENTIFIER,
        "name": {**TEXT, "maxLength": 128},
        "description": {**TEXT, "maxLength": 2048},
        "category": {
            "type": "string",
            "maxLength": 128,
            "pattern": "^[a-z][a-z0-9._-]*(?:/[a-z][a-z0-9._-]*)*$",
        },
        "kind": {"enum": ["style", "grade", "modifier"]},
        "tags": strings(),
        "claims": {"type": "object", "propertyNames": {"enum": AXES}, "additionalProperties": IDENTIFIER},
        "clauses": clauses,
        "negative": strings(512),
        "models": {"type": "array", "items": IDENTIFIER, "uniqueItems": True, "maxItems": 32},
        "variants": {
            "type": "object",
            "maxProperties": 32,
            "propertyNames": IDENTIFIER,
            "additionalProperties": variant,
        },
        "preview": obj(
            {
                "path": {
                    "type": "string",
                    "maxLength": 256,
                    "pattern": r"^(?!/)(?!.*(?:\.\.|:|\\)).+\.(?:png|jpg|jpeg|webp|avif)$",
                },
                "alt": TEXT,
                "kind": {"enum": ["reference", "generated", "swatch"]},
            },
            ["path", "alt", "kind"],
        ),
    },
    ["id", "name", "description", "category", "kind", "tags", "claims", "clauses"],
)
pack = obj(
    {
        "schema_version": {"const": 1, "type": "integer"},
        "id": IDENTIFIER,
        "version": {"type": "string", "maxLength": 64, "pattern": r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$"},
        "name": {**TEXT, "maxLength": 128},
        "description": {**TEXT, "maxLength": 2048},
        "license": {**TEXT, "maxLength": 128},
        "author": {**TEXT, "maxLength": 128},
        "styles": {"type": "array", "minItems": 1, "maxItems": 2048, "items": style},
    },
    ["schema_version", "id", "version", "name", "description", "license", "author", "styles"],
)
recipe = obj(
    {
        "schema_version": {"const": 1, "type": "integer"},
        "prompt": {"type": "string", "maxLength": 32768},
        "negative": {"type": "string", "maxLength": 32768},
        "model": {**TEXT, "maxLength": 128},
        "styles": {
            "type": "array",
            "maxItems": 16,
            "items": obj({"id": IDENTIFIER, "intensity": UNIT}, ["id"]),
        },
        "conflict_policy": {"enum": ["last_wins", "first_wins", "error"]},
        "locked_axes": {"type": "array", "items": {"enum": AXES}, "uniqueItems": True, "maxItems": len(AXES)},
    },
    ["prompt"],
)
profile = obj(
    {
        "id": IDENTIFIER,
        "name": {**TEXT, "maxLength": 128},
        "format": {"enum": ["natural", "tags", "structured"]},
        "negative": {"type": "boolean"},
        "weighting": {"type": "boolean"},
        "conditioning": {"enum": ["clip", "specialized"]},
        "guidance": {**TEXT, "maxLength": 4096},
        "sources": {**strings(512), "items": {"type": "string", "maxLength": 512, "pattern": "^https://"}},
        "evidence": {"enum": ["documented", "conservative"]},
        "aliases": strings(128),
    },
    ["id", "name", "format", "negative", "weighting", "conditioning", "guidance", "sources", "evidence"],
)
profiles = obj(
    {
        "schema_version": {"const": 1, "type": "integer"},
        "profiles": {"type": "array", "maxItems": 64, "items": profile},
    },
    ["schema_version", "profiles"],
)
for name, schema in [("pack", pack), ("recipe", recipe), ("profiles", profiles)]:
    ROOT.mkdir(exist_ok=True)
    (ROOT / f"{name}.schema.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": f"urn:promptstyler-next:{name}:1",
                **schema,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
