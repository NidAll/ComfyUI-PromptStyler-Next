"""Strict, immutable style-pack snapshots and indexed discovery."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from . import validation as v
from .errors import StylerError
from .types import Clause


def tokens(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE))


@dataclass(frozen=True, slots=True)
class Variant:
    clauses: tuple[Clause, ...]
    negative: tuple[str, ...]


def _clauses(value: object, path: str) -> tuple[Clause, ...]:
    clauses = tuple(
        Clause.from_dict(item, f"{path}[{i}]") for i, item in enumerate(v.array(value, path, maximum=32))
    )
    if not clauses:
        raise StylerError("empty_style", "A style needs at least one clause.", path)
    return clauses


@dataclass(frozen=True, slots=True)
class Style:
    id: str
    name: str
    description: str
    category: str
    kind: str
    tags: tuple[str, ...]
    claims: tuple[tuple[str, str], ...]
    clauses: tuple[Clause, ...]
    negative: tuple[str, ...]
    models: tuple[str, ...]
    variants: tuple[tuple[str, Variant], ...]
    preview: tuple[tuple[str, str], ...]
    pack_id: str
    pack_version: str

    @classmethod
    def from_dict(cls, value: object, path: str, pack_id: str, pack_version: str) -> Style:
        data = v.obj(
            value,
            path,
            required=("id", "name", "description", "category", "kind", "tags", "claims", "clauses"),
            optional=("negative", "models", "variants", "preview"),
        )
        claims = data["claims"]
        if not isinstance(claims, dict):
            raise StylerError("invalid_type", "Claims must map an axis to an identity.", f"{path}.claims")
        checked_claims = tuple(
            sorted(
                (v.choice(axis, v.AXES, f"{path}.claims"), v.identifier(identity, f"{path}.claims.{axis}"))
                for axis, identity in claims.items()
            )
        )
        category = v.string(data["category"], f"{path}.category", maximum=128)
        for component in category.split("/"):
            v.identifier(component, f"{path}.category")
        variants_raw = data.get("variants", {})
        if not isinstance(variants_raw, dict) or len(variants_raw) > 32:
            raise StylerError("invalid_variants", "Expected up to 32 model variants.", f"{path}.variants")
        variants = []
        for model_id, raw in sorted(variants_raw.items()):
            v.identifier(model_id, f"{path}.variants")
            variant = v.obj(raw, f"{path}.variants.{model_id}", required=("clauses",), optional=("negative",))
            variants.append(
                (
                    model_id,
                    Variant(
                        _clauses(variant["clauses"], f"{path}.variants.{model_id}.clauses"),
                        v.strings(
                            variant.get("negative", []), f"{path}.variants.{model_id}.negative", length=512
                        ),
                    ),
                )
            )
        preview: tuple[tuple[str, str], ...] = ()
        if "preview" in data:
            raw_preview = v.obj(data["preview"], f"{path}.preview", required=("path", "alt", "kind"))
            asset = v.string(raw_preview["path"], f"{path}.preview.path", maximum=256)
            parts = PurePosixPath(asset)
            if (
                parts.is_absolute()
                or ".." in parts.parts
                or ":" in asset
                or "\\" in asset
                or parts.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".avif")
            ):
                raise StylerError(
                    "unsafe_preview",
                    "Use a relative raster asset path without traversal.",
                    f"{path}.preview.path",
                )
            preview = (
                ("path", asset),
                ("alt", v.string(raw_preview["alt"], f"{path}.preview.alt")),
                (
                    "kind",
                    v.choice(
                        raw_preview["kind"], ("reference", "generated", "swatch"), f"{path}.preview.kind"
                    ),
                ),
            )
        return cls(
            v.identifier(data["id"], f"{path}.id"),
            v.string(data["name"], f"{path}.name", maximum=128),
            v.string(data["description"], f"{path}.description", maximum=2048),
            category,
            v.choice(data["kind"], ("style", "grade", "modifier"), f"{path}.kind"),
            v.strings(data["tags"], f"{path}.tags"),
            checked_claims,
            _clauses(data["clauses"], f"{path}.clauses"),
            v.strings(data.get("negative", []), f"{path}.negative", length=512),
            tuple(
                v.identifier(model, f"{path}.models")
                for model in v.strings(data.get("models", []), f"{path}.models")
            ),
            tuple(variants),
            preview,
            pack_id,
            pack_version,
        )

    def variant(self, profile: str) -> Variant:
        return dict(self.variants).get(profile, Variant(self.clauses, self.negative))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "kind": self.kind,
            "tags": list(self.tags),
            "claims": dict(self.claims),
            "clauses": [clause.to_dict() for clause in self.clauses],
            "negative": list(self.negative),
            "models": list(self.models),
            "variants": {
                key: {
                    "clauses": [clause.to_dict() for clause in variant.clauses],
                    "negative": list(variant.negative),
                }
                for key, variant in self.variants
            },
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
        }
        if self.preview:
            result["preview"] = dict(self.preview)
        return result


@dataclass(frozen=True, slots=True)
class Pack:
    id: str
    version: str
    name: str
    description: str
    license: str
    author: str
    styles: tuple[Style, ...]

    @classmethod
    def from_dict(cls, value: object) -> Pack:
        data = v.obj(
            value,
            "pack",
            required=(
                "schema_version",
                "id",
                "version",
                "name",
                "description",
                "license",
                "author",
                "styles",
            ),
        )
        v.schema_version(data["schema_version"], "pack.schema_version")
        pack_id = v.identifier(data["id"], "pack.id")
        pack_version = v.version(data["version"], "pack.version")
        styles = tuple(
            Style.from_dict(item, f"styles[{i}]", pack_id, pack_version)
            for i, item in enumerate(v.array(data["styles"], "styles", maximum=2048))
        )
        if not styles:
            raise StylerError("empty_pack", "A pack needs at least one style.", "pack.styles")
        return cls(
            pack_id,
            pack_version,
            v.string(data["name"], "pack.name", maximum=128),
            v.string(data["description"], "pack.description", maximum=2048),
            v.string(data["license"], "pack.license", maximum=128),
            v.string(data["author"], "pack.author", maximum=128),
            styles,
        )

    @classmethod
    def load(cls, path: Path) -> Pack:
        return cls.from_dict(v.read_json(path))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "id": self.id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "license": self.license,
            "author": self.author,
            "styles": [
                {
                    key: value
                    for key, value in style.to_dict().items()
                    if key not in ("pack_id", "pack_version")
                }
                for style in self.styles
            ],
        }


class Catalog:
    """Content-addressed snapshot; adding packs returns a new catalog."""

    def __init__(self, packs: Iterable[Pack]) -> None:
        self.packs = tuple(sorted(packs, key=lambda item: item.id))
        if len(self.packs) > 64:
            raise StylerError("too_many_packs", "A catalog supports up to 64 packs.")
        if len({pack.id for pack in self.packs}) != len(self.packs):
            raise StylerError(
                "duplicate_pack", "Pack IDs must be unique; replacements require a new catalog."
            )
        styles = sorted(
            (style for pack in self.packs for style in pack.styles),
            key=lambda item: (item.category, item.name.casefold(), item.id),
        )
        if len(styles) > 8192:
            raise StylerError("too_many_styles", "A catalog supports up to 8192 styles.")
        by_id = {style.id: style for style in styles}
        if len(by_id) != len(styles):
            raise StylerError("duplicate_style", "Style IDs must be unique across packs.")
        self.styles = tuple(styles)
        self.by_id: Mapping[str, Style] = MappingProxyType(by_id)
        self.index: Mapping[str, frozenset[str]] = MappingProxyType(
            {
                style.id: tokens(
                    " ".join((style.id, style.name, style.description, style.category, *style.tags))
                )
                for style in styles
            }
        )
        self.fingerprint = v.digest([pack.to_dict() for pack in self.packs])

    def get(self, style_id: str) -> Style:
        v.identifier(style_id, "style_id")
        try:
            return self.by_id[style_id]
        except KeyError as exc:
            raise StylerError("unknown_style", "No style has this identifier.", style_id) from exc

    def search(
        self,
        *,
        query: str = "",
        category: str | None = None,
        model: str | None = None,
        tags: Iterable[str] = (),
        kind: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Style]:
        v.string(query, "query", maximum=512, empty=True)
        v.integer(limit, "limit", maximum=1000)
        v.integer(offset, "offset", maximum=8192)
        requested_tags = v.strings(tuple(tags), "tags")
        if kind is not None:
            v.choice(kind, ("style", "grade", "modifier"), "kind")
        if category is not None:
            v.string(category, "category", maximum=128)
        wanted = tokens(query)
        found = [
            style
            for style in self.styles
            if wanted <= self.index[style.id]
            and (category is None or style.category == category or style.category.startswith(category + "/"))
            and (model is None or not style.models or model in style.models)
            and (kind is None or style.kind == kind)
            and set(requested_tags) <= set(style.tags)
        ]
        return found[offset : offset + limit]
