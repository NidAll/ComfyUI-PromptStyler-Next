"""Model-owned formatting. No model loading, prompt rewrites, or hidden LLM calls."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from . import validation as v
from .errors import StylerError
from .types import Clause


@dataclass(frozen=True, slots=True)
class Profile:
    id: str
    name: str
    format: str
    negative: bool
    weighting: bool
    conditioning: str
    guidance: str
    sources: tuple[str, ...]
    evidence: str
    aliases: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: object) -> Profile:
        data = v.obj(
            value,
            "profile",
            required=(
                "id",
                "name",
                "format",
                "negative",
                "weighting",
                "conditioning",
                "guidance",
                "sources",
                "evidence",
            ),
            optional=("aliases",),
        )
        for key in ("negative", "weighting"):
            if type(data[key]) is not bool:
                raise StylerError("invalid_type", "Expected a boolean.", f"profile.{key}")
        sources = v.strings(data["sources"], "profile.sources", length=512)
        if any(not source.startswith("https://") for source in sources):
            raise StylerError("invalid_source", "Source citations must use HTTPS.", "profile.sources")
        return cls(
            v.identifier(data["id"], "profile.id"),
            v.string(data["name"], "profile.name", maximum=128),
            v.choice(data["format"], ("natural", "tags", "structured"), "profile.format"),
            data["negative"],
            data["weighting"],
            v.choice(data["conditioning"], ("clip", "specialized"), "profile.conditioning"),
            v.string(data["guidance"], "profile.guidance", maximum=4096),
            sources,
            v.choice(data["evidence"], ("documented", "conservative"), "profile.evidence"),
            v.strings(data.get("aliases", []), "profile.aliases", maximum=32, length=128),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "format": self.format,
            "negative": self.negative,
            "weighting": self.weighting,
            "conditioning": self.conditioning,
            "guidance": self.guidance,
            "sources": list(self.sources),
            "evidence": self.evidence,
            "aliases": list(self.aliases),
        }


class ModelAdapter(Protocol):
    """An explicitly registered, trusted code extension; never imported from a pack."""

    @property
    def revision(self) -> str: ...

    def locked_axes(self, prompt: str) -> tuple[str, ...]: ...

    def render(self, prompt: str, clauses: tuple[Clause, ...]) -> str: ...


@dataclass(frozen=True, slots=True)
class NaturalAdapter:
    revision: str = "natural/1"

    def locked_axes(self, prompt: str) -> tuple[str, ...]:
        return ()

    def render(self, prompt: str, clauses: tuple[Clause, ...]) -> str:
        additions = " ".join(clause.text.rstrip(" .") + "." for clause in clauses)
        if not additions:
            return prompt
        separator = " " if prompt.rstrip().endswith((".", "!", "?")) else ". "
        return prompt + (separator if prompt else "") + additions


@dataclass(frozen=True, slots=True)
class TagAdapter:
    revision: str = "tags/1"

    def locked_axes(self, prompt: str) -> tuple[str, ...]:
        return ()

    def render(self, prompt: str, clauses: tuple[Clause, ...]) -> str:
        additions = list(dict.fromkeys(tag for clause in clauses for tag in (clause.tags or (clause.text,))))
        if not additions:
            return prompt
        return prompt + (", " if prompt else "") + ", ".join(additions)


_FIBO_PATHS = {
    "medium": ("style_medium",),
    "lighting": ("lighting", "conditions"),
    "palette": ("aesthetics", "color_scheme"),
    "composition": ("aesthetics", "composition"),
    "mood": ("aesthetics", "mood_atmosphere"),
    "texture": ("artistic_style",),
    "detail": ("artistic_style",),
}


def _fibo_caption(prompt: str) -> dict[str, Any]:
    if not prompt.lstrip().startswith("{"):
        return {"short_description": prompt}
    value = v.parse_json(prompt)
    if not isinstance(value, dict):
        raise StylerError("invalid_caption", "A structured caption must be an object.", "prompt")
    for parent in ("lighting", "aesthetics"):
        if parent in value and not isinstance(value[parent], dict):
            raise StylerError("invalid_caption", f"Caption field {parent} must be an object.", "prompt")
    for field in ("short_description", "style_medium", "artistic_style"):
        if field in value:
            v.string(value[field], f"prompt.{field}", maximum=32768, empty=True)
    for parent, fields in (
        ("lighting", ("conditions",)),
        ("aesthetics", ("composition", "color_scheme", "mood_atmosphere")),
    ):
        container = value.get(parent, {})
        for field in fields:
            if field in container:
                v.string(container[field], f"prompt.{parent}.{field}", maximum=32768, empty=True)
    return value


@dataclass(frozen=True, slots=True)
class FiboAdapter:
    """Map declared style axes into published Fibo caption fields, never invent scene objects."""

    revision: str = "fibo-caption/1"

    def locked_axes(self, prompt: str) -> tuple[str, ...]:
        caption = _fibo_caption(prompt)
        locked = []
        for axis, path in _FIBO_PATHS.items():
            current: Any = caption
            for field in path:
                if not isinstance(current, dict) or field not in current:
                    break
                current = current[field]
            else:
                locked.append(axis)
        return tuple(locked)

    def render(self, prompt: str, clauses: tuple[Clause, ...]) -> str:
        caption = _fibo_caption(prompt)
        additions: dict[tuple[str, ...], list[str]] = {}
        for clause in clauses:
            additions.setdefault(_FIBO_PATHS[clause.axis], []).append(clause.text)
        for path, text in additions.items():
            parent = caption
            for field in path[:-1]:
                parent = parent.setdefault(field, {})
            # Existing user-specified fields always win, even empty strings.
            if path[-1] not in parent:
                parent[path[-1]] = " ".join(text)
        return v.canonical(caption)


@dataclass(frozen=True, slots=True)
class FiboEditAdapter:
    """Keep free-form edit instructions intact; style structured captions in place."""

    revision: str = "fibo-edit/1"

    def locked_axes(self, prompt: str) -> tuple[str, ...]:
        if not prompt.lstrip().startswith("{"):
            return ()
        caption = _fibo_caption(prompt)
        if "structured_caption" in caption:
            nested = caption["structured_caption"]
            if not isinstance(nested, (str, dict)):
                raise StylerError(
                    "invalid_caption",
                    "Structured caption must be text or an object.",
                    "prompt.structured_caption",
                )
            return FiboAdapter().locked_axes(v.canonical(nested) if isinstance(nested, dict) else nested)
        return FiboAdapter().locked_axes(prompt)

    def render(self, prompt: str, clauses: tuple[Clause, ...]) -> str:
        if not prompt.lstrip().startswith("{"):
            return NaturalAdapter().render(prompt, clauses)
        caption = _fibo_caption(prompt)
        if "structured_caption" not in caption:
            return FiboAdapter().render(prompt, clauses)
        nested = caption["structured_caption"]
        if not isinstance(nested, (str, dict)):
            raise StylerError(
                "invalid_caption",
                "Structured caption must be text or an object.",
                "prompt.structured_caption",
            )
        styled = FiboAdapter().render(v.canonical(nested) if isinstance(nested, dict) else nested, clauses)
        return v.canonical({**caption, "structured_caption": v.parse_json(styled)})


class AdapterRegistry:
    def __init__(self, profiles: Iterable[Profile], adapters: dict[str, ModelAdapter] | None = None) -> None:
        self._profiles = tuple(sorted(profiles, key=lambda profile: profile.id))
        self._by_id = {profile.id: profile for profile in self._profiles}
        if len(self._by_id) != len(self._profiles) or "generic" not in self._by_id:
            raise StylerError("invalid_profiles", "Profiles require unique IDs and a generic fallback.")
        self._names: dict[str, str] = {}
        for profile in self._profiles:
            for name in (profile.id, *profile.aliases):
                key = name.casefold()
                if key in self._names:
                    raise StylerError("ambiguous_profile", "Profile IDs and aliases must be unique.", name)
                self._names[key] = profile.id
        supplied = adapters or {}
        self._adapters: dict[str, ModelAdapter] = {}
        for profile in self._profiles:
            default: ModelAdapter = (
                FiboEditAdapter()
                if profile.id == "fibo-edit"
                else FiboAdapter()
                if profile.id == "fibo"
                else TagAdapter()
                if profile.format == "tags"
                else NaturalAdapter()
            )
            self._adapters[profile.id] = supplied.get(profile.id, default)
        self.fingerprint = v.digest(
            [
                {"profile": profile.to_dict(), "adapter": self._adapters[profile.id].revision}
                for profile in self._profiles
            ]
        )

    def resolve(self, model: str) -> tuple[Profile, ModelAdapter, bool]:
        v.string(model, "model", maximum=128)
        profile_id = self._names.get(model.casefold(), "generic")
        return self._by_id[profile_id], self._adapters[profile_id], model.casefold() not in self._names

    def profiles(self) -> list[dict[str, Any]]:
        return [profile.to_dict() for profile in self._profiles]

    def with_adapter(self, profile: Profile, adapter: ModelAdapter) -> AdapterRegistry:
        # Validate direct dataclass construction at the trusted registration boundary.
        checked = Profile.from_dict(profile.to_dict())
        v.string(adapter.revision, "adapter.revision", maximum=128)
        profiles = [item for item in self._profiles if item.id != checked.id] + [checked]
        return AdapterRegistry(profiles, {**self._adapters, checked.id: adapter})
