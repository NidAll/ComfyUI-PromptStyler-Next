"""Immutable domain records and recipe contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import validation as v
from .errors import StylerError


@dataclass(frozen=True, slots=True)
class Layer:
    id: str
    intensity: float = 1.0

    def __post_init__(self) -> None:
        v.identifier(self.id, "styles.id")
        v.unit_float(self.intensity, "styles.intensity")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "intensity": float(self.intensity)}


@dataclass(frozen=True, slots=True)
class Recipe:
    prompt: str
    negative: str = ""
    model: str = "generic"
    styles: tuple[Layer, ...] = ()
    conflict_policy: str = "last_wins"
    locked_axes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        v.string(self.prompt, "prompt", maximum=32768, empty=True)
        v.string(self.negative, "negative", maximum=32768, empty=True)
        v.string(self.model, "model", maximum=128)
        v.choice(self.conflict_policy, ("last_wins", "first_wins", "error"), "conflict_policy")
        for axis in v.strings(self.locked_axes, "locked_axes", maximum=len(v.AXES)):
            v.choice(axis, v.AXES, "locked_axes")
        v.array(self.styles, "styles", maximum=16)
        if not isinstance(self.styles, tuple) or any(not isinstance(layer, Layer) for layer in self.styles):
            raise StylerError("invalid_type", "Use a tuple of Layer records.", "styles")
        if not isinstance(self.locked_axes, tuple):
            raise StylerError("invalid_type", "Use a tuple of axis names.", "locked_axes")
        if len({layer.id for layer in self.styles}) != len(self.styles):
            raise StylerError("duplicate_style", "A style may appear only once in a recipe.", "styles")

    @classmethod
    def from_dict(cls, value: object) -> Recipe:
        data = v.obj(
            value,
            "recipe",
            required=("prompt",),
            optional=("schema_version", "negative", "model", "styles", "conflict_policy", "locked_axes"),
        )
        v.schema_version(data.get("schema_version", 1), "recipe.schema_version")
        layers = []
        for i, raw in enumerate(v.array(data.get("styles", []), "styles", maximum=16)):
            item = v.obj(raw, f"styles[{i}]", required=("id",), optional=("intensity",))
            layers.append(
                Layer(
                    v.identifier(item["id"], f"styles[{i}].id"),
                    v.unit_float(item.get("intensity", 1), f"styles[{i}].intensity"),
                )
            )
        return cls(
            prompt=data["prompt"],
            negative=data.get("negative", ""),
            model=data.get("model", "generic"),
            styles=tuple(layers),
            conflict_policy=data.get("conflict_policy", "last_wins"),
            locked_axes=v.strings(data.get("locked_axes", []), "locked_axes", maximum=len(v.AXES)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "prompt": self.prompt,
            "negative": self.negative,
            "model": self.model,
            "styles": [layer.to_dict() for layer in self.styles],
            "conflict_policy": self.conflict_policy,
            "locked_axes": list(self.locked_axes),
        }


@dataclass(frozen=True, slots=True)
class Clause:
    axis: str
    text: str
    tags: tuple[str, ...]
    min_intensity: float = 0.0

    @classmethod
    def from_dict(cls, value: object, path: str) -> Clause:
        data = v.obj(value, path, required=("axis", "text", "tags"), optional=("min_intensity",))
        return cls(
            v.choice(data["axis"], v.AXES, f"{path}.axis"),
            v.string(data["text"], f"{path}.text", maximum=1024),
            v.strings(data["tags"], f"{path}.tags", maximum=24, length=192),
            v.unit_float(data.get("min_intensity", 0), f"{path}.min_intensity"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "axis": self.axis,
            "text": self.text,
            "tags": list(self.tags),
            "min_intensity": self.min_intensity,
        }


@dataclass(frozen=True, slots=True)
class Notice:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class Trace:
    style_id: str
    axis: str
    action: str
    text: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "style_id": self.style_id,
            "axis": self.axis,
            "action": self.action,
            "text": self.text,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class Composition:
    positive: str
    negative: str
    recipe: Recipe
    fingerprint: str
    catalog_fingerprint: str
    profile: str
    warnings: tuple[Notice, ...]
    trace: tuple[Trace, ...]
    # Canonical JSON provides a deeply immutable snapshot, decoded only at the boundary.
    structured_json: str

    @property
    def structured(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self.structured_json)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "positive": self.positive,
            "negative": self.negative,
            "structured": self.structured,
            "recipe": self.recipe.to_dict(),
            "fingerprint": self.fingerprint,
            "catalog_fingerprint": self.catalog_fingerprint,
            "profile": self.profile,
            "warnings": [item.to_dict() for item in self.warnings],
            "trace": [item.to_dict() for item in self.trace],
        }
