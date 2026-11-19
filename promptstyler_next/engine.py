"""Shared deterministic composition, inspection and metadata recommendations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import lexicon
from . import validation as v
from .adapters import AdapterRegistry, ModelAdapter, Profile
from .catalog import Catalog, Pack, Style, tokens
from .errors import StylerError
from .types import Clause, Composition, Notice, Recipe, Trace

ENGINE_REVISION = "promptstyler-next/2"
_DATA = Path(__file__).parent


@lru_cache(maxsize=1)
def _builtin() -> tuple[Catalog, AdapterRegistry]:
    raw = v.obj(v.read_json(_DATA / "profiles.json"), "profiles", required=("schema_version", "profiles"))
    v.schema_version(raw["schema_version"], "profiles.schema_version")
    registry = AdapterRegistry(
        Profile.from_dict(profile) for profile in v.array(raw["profiles"], "profiles.profiles", maximum=64)
    )
    catalog = Catalog(Pack.load(path) for path in sorted((_DATA / "packs").glob("*.json")))
    if not catalog.styles:
        raise StylerError("empty_catalog", "Builtin style packs are missing.")
    return catalog, registry


class Engine:
    """An isolated catalog and adapter snapshot, safe for concurrent composition.

    `builtin` caches only the small immutable data snapshot. Composition has no mutable
    global state; changed packs are adopted by creating a new Engine, never hot-reloaded.
    """

    def __init__(self, packs: Iterable[Pack], registry: AdapterRegistry) -> None:
        self._catalog = Catalog(packs)
        self._registry = registry
        self._validate_models()

    @classmethod
    def builtin(cls) -> Engine:
        catalog, registry = _builtin()
        return cls(catalog.packs, registry)

    @classmethod
    def from_packs(cls, paths: Iterable[str | Path]) -> Engine:
        """Create a custom-only catalog using the documented builtin model profiles."""
        return cls((Pack.load(Path(path)) for path in paths), _builtin()[1])

    def _validate_models(self) -> None:
        known = {profile["id"] for profile in self.profiles()}
        for style in self._catalog.styles:
            references = set(style.models) | {key for key, _ in style.variants}
            if references - known:
                raise StylerError(
                    "unknown_profile", "Style references an unregistered model profile.", style.id
                )
            for _, variant in style.variants:
                for axis, _identity in style.claims:
                    if axis not in {clause.axis for clause in variant.clauses}:
                        raise StylerError(
                            "invalid_claim",
                            "A variant must retain the axes declared in its claims.",
                            style.id,
                        )
            for axis, _identity in style.claims:
                if axis not in {clause.axis for clause in style.clauses}:
                    raise StylerError(
                        "invalid_claim", "Claims must describe an axis with a clause.", style.id
                    )

    @property
    def catalog_fingerprint(self) -> str:
        return v.digest(
            {
                "packs": self._catalog.fingerprint,
                "adapters": self._registry.fingerprint,
                "engine": ENGINE_REVISION,
            }
        )

    def with_packs(self, paths: Iterable[str | Path]) -> Engine:
        additions = tuple(Pack.load(Path(path)) for path in paths)
        return Engine((*self._catalog.packs, *additions), self._registry)

    def with_adapter(self, profile: Profile, adapter: ModelAdapter) -> Engine:
        return Engine(self._catalog.packs, self._registry.with_adapter(profile, adapter))

    def profiles(self) -> list[dict[str, Any]]:
        return self._registry.profiles()

    def get_style(self, style_id: str) -> dict[str, Any]:
        return self._catalog.get(style_id).to_dict()

    def retired_styles(self) -> dict[str, str]:
        """Retired style IDs mapped to their replacement ("" when skipped)."""
        return dict(self._catalog.retired)

    def list_styles(
        self,
        *,
        query: str = "",
        category: str | None = None,
        model: str | None = None,
        tags: Iterable[str] = (),
        kind: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        resolved = self._registry.resolve(model)[0].id if model is not None else None
        return [
            style.to_dict()
            for style in self._catalog.search(
                query=query,
                category=category,
                model=resolved,
                tags=tags,
                kind=kind,
                limit=limit,
                offset=offset,
            )
        ]

    def recommend(self, *, prompt: str, model: str = "generic", limit: int = 6) -> list[dict[str, Any]]:
        v.string(prompt, "prompt", maximum=32768, empty=True)
        v.integer(limit, "limit", maximum=50)
        profile, _adapter, _unknown = self._registry.resolve(model)
        ignored = tokens("a an the of in on with and or to for is are image picture scene style")
        wanted = tokens(prompt) - ignored
        ranked = []
        for style in self._catalog.styles:
            if style.models and profile.id not in style.models:
                continue
            matched = wanted & self._catalog.index[style.id]
            if not matched:
                continue
            tag_matches = wanted & tokens(" ".join(style.tags))
            score = len(matched) + 2 * len(tag_matches)
            ranked.append((score, style, tuple(sorted(matched))))
        ranked.sort(key=lambda item: (-item[0], item[1].id))
        return [
            {**style.to_dict(), "score": score, "reasons": [f"Metadata matches: {', '.join(matched)}."]}
            for score, style, matched in ranked[:limit]
        ]

    def compose(self, recipe: Mapping[str, object] | Recipe) -> Composition:
        request = recipe if isinstance(recipe, Recipe) else Recipe.from_dict(recipe)
        profile, adapter, unknown = self._registry.resolve(request.model)
        warnings: list[Notice] = []
        trace: list[Trace] = []
        if unknown:
            warnings.append(
                Notice(
                    "unknown_model",
                    "Unknown model: using conservative natural-language formatting and no negative prompt. Choose an explicit profile for model-specific behavior.",
                )
            )
        locked = set(request.locked_axes) | set(adapter.locked_axes(request.prompt))
        layers: list[tuple[Style, float]] = []
        for layer in request.styles:
            style_id = layer.id
            if style_id in self._catalog.retired:
                replacement = self._catalog.retired[style_id]
                if not replacement:
                    message = f"Style {style_id} was retired from the library and is skipped."
                    warnings.append(Notice("style_retired", message))
                    trace.append(Trace(style_id, "style", "retired", "", "Retired from the library."))
                    continue
                warnings.append(Notice("style_replaced", f"Style {style_id} was merged into {replacement}."))
                trace.append(Trace(style_id, "style", "replaced", replacement, "Merged into a live style."))
                style_id = replacement
            if any(style.id == style_id for style, _ in layers):
                continue
            layers.append((self._catalog.get(style_id), layer.intensity))
        # Each candidate owns its style claims. Only conflicting axes are suppressed,
        # so a color grade can replace a palette without erasing the original medium.
        candidates: list[tuple[int, int, Style, Clause]] = []
        suppressed_styles: set[str] = set()
        for layer_index, (style, intensity) in enumerate(layers):
            if style.models and profile.id not in style.models:
                raise StylerError(
                    "unsupported_style", "Style is not supported by this model profile.", style.id
                )
            variant = style.variant(profile.id)
            for clause_index, clause in enumerate(variant.clauses):
                if intensity == 0 or intensity < clause.min_intensity:
                    suppressed_styles.add(style.id)
                    trace.append(
                        Trace(
                            style.id,
                            clause.axis,
                            "skipped",
                            clause.text,
                            "Below this clause's intensity threshold.",
                        )
                    )
                elif clause.axis in locked:
                    suppressed_styles.add(style.id)
                    trace.append(
                        Trace(
                            style.id,
                            clause.axis,
                            "skipped",
                            clause.text,
                            "Axis protected by the recipe or an existing structured-caption field.",
                        )
                    )
                else:
                    candidates.append((layer_index, clause_index, style, clause))
        winners: dict[str, tuple[str, str]] = {}
        for _layer, _index, style, clause in candidates:
            identity = dict(style.claims).get(clause.axis)
            if identity is None:
                continue
            old = winners.get(clause.axis)
            if old is not None and old[0] != identity:
                if request.conflict_policy == "error":
                    raise StylerError(
                        "style_conflict",
                        f"Incompatible declared claims on {clause.axis}; reorder styles, lock this axis, or choose a conflict policy.",
                        clause.axis,
                    )
                if request.conflict_policy == "first_wins":
                    continue
            winners[clause.axis] = (identity, style.id)
        eligible: list[tuple[int, int, Style, Clause]] = []
        seen: set[str] = set()
        for item in candidates:
            _layer, _index, style, clause = item
            identity = dict(style.claims).get(clause.axis)
            winner = winners.get(clause.axis)
            if identity is not None and winner is not None and identity != winner[0]:
                suppressed_styles.add(style.id)
                trace.append(
                    Trace(
                        style.id,
                        clause.axis,
                        "suppressed",
                        clause.text,
                        f"Conflicting claim replaced by {winner[1]} under {request.conflict_policy}.",
                    )
                )
                continue
            rendered = ", ".join(clause.tags or (clause.text,)) if profile.format == "tags" else clause.text
            key = " ".join(rendered.casefold().split()).rstrip(".,")
            if key in seen:
                trace.append(
                    Trace(
                        style.id,
                        clause.axis,
                        "deduplicated",
                        clause.text,
                        "Identical generated clause already included.",
                    )
                )
                continue
            seen.add(key)
            eligible.append(item)

        # Identity first: every layer's core clause, then supporting tiers, then detail.
        def tier(clause: Clause) -> int:
            return sum(clause.min_intensity >= threshold for threshold in v.TIERS[1:])

        eligible.sort(key=lambda item: (tier(item[3]), item[0], v.AXIS_PRIORITY.index(item[3].axis), item[1]))
        unit = "tags" if profile.format == "tags" else "words"
        budget = profile.style_budget
        used = 0
        counted_tags: set[str] = set()
        selected: list[Clause] = []
        active_styles: dict[str, Style] = {}
        for _layer, _index, style, clause in eligible:
            if unit == "tags":
                fresh = [tag for tag in (clause.tags or (clause.text,)) if tag.casefold() not in counted_tags]
                cost = len(fresh)
            else:
                fresh = []
                cost = len(clause.text.split())
            if tier(clause) > 0 and used + cost > budget:
                suppressed_styles.add(style.id)
                trace.append(
                    Trace(
                        style.id,
                        clause.axis,
                        "budget_skipped",
                        clause.text,
                        f"Keeps the added style within {budget} {unit} for this model.",
                    )
                )
                continue
            used += cost
            counted_tags.update(tag.casefold() for tag in fresh)
            selected.append(clause)
            active_styles[style.id] = style
            trace.append(
                Trace(
                    style.id,
                    clause.axis,
                    "applied",
                    clause.text,
                    "Model-specific variant."
                    if profile.id in dict(style.variants)
                    else "Shared clause rendered by the model adapter.",
                )
            )
        prompt = request.prompt
        removed: list[tuple[str, str]] = []
        claimed = {clause.axis for clause in selected if clause.axis in lexicon.AXES}
        if claimed and profile.format != "structured" and not prompt.lstrip().startswith("{"):
            finder = lexicon.find_tags if profile.format == "tags" else lexicon.find_prose
            cleaned, removed = finder(prompt, claimed)
            if removed:
                words = ", ".join(dict.fromkeys(phrase for _axis, phrase in removed))
                if request.prompt_conflicts == "replace":
                    prompt = cleaned
                    warnings.append(
                        Notice(
                            "prompt_style_replaced",
                            f"Removed style words from the prompt so the selected style is followed: {words}.",
                        )
                    )
                    action, reason = "prompt_removed", "The selected style sets this axis."
                else:
                    warnings.append(
                        Notice(
                            "prompt_style_conflict",
                            f"The prompt also sets this style direction and may weaken the selected style: {words}.",
                        )
                    )
                    action, reason = "prompt_conflict", "Kept because prompt_conflicts is keep."
                trace.extend(Trace("prompt", axis, action, phrase, reason) for axis, phrase in removed)
        negative_parts = list(
            dict.fromkeys(
                phrase
                for style in active_styles.values()
                if style.id not in suppressed_styles
                for phrase in style.variant(profile.id).negative
            )
        )
        for style in active_styles.values():
            if style.id in suppressed_styles and style.variant(profile.id).negative:
                warnings.append(
                    Notice(
                        "negative_conflict_omitted",
                        "Unscoped negative clauses were omitted from a partially active style because some directions were suppressed, protected, or below their intensity threshold.",
                    )
                )
                for phrase in style.variant(profile.id).negative:
                    trace.append(
                        Trace(
                            style.id,
                            "negative",
                            "negative_skipped",
                            phrase,
                            "A style direction was suppressed, protected, or below its intensity threshold.",
                        )
                    )
        has_negative = bool(request.negative or negative_parts)
        negative = request.negative
        if profile.negative:
            if negative_parts:
                negative += (", " if negative else "") + ", ".join(negative_parts)
        else:
            negative = ""
            if has_negative:
                warnings.append(
                    Notice(
                        "negative_unsupported",
                        "This profile does not use negative prompts. The supplied negative text is retained in the recipe, but omitted from the encoded output.",
                    )
                )
        positive = adapter.render(prompt, tuple(selected))
        structured = {
            "subject": prompt,
            "format": profile.format,
            "axes": {
                axis: [clause.text for clause in selected if clause.axis == axis]
                for axis in v.AXES
                if any(clause.axis == axis for clause in selected)
            },
            "protected_axes": sorted(locked),
            "style_budget": {"limit": budget, "used": used, "unit": unit},
            "prompt_style_words": [{"axis": axis, "text": phrase} for axis, phrase in removed],
        }
        fingerprint = v.digest(
            {
                "engine": ENGINE_REVISION,
                "catalog": self.catalog_fingerprint,
                "recipe": request.to_dict(),
                "positive": positive,
                "negative": negative,
            }
        )
        return Composition(
            positive=positive,
            negative=negative,
            recipe=request,
            fingerprint=fingerprint,
            catalog_fingerprint=self.catalog_fingerprint,
            profile=profile.id,
            warnings=tuple(warnings),
            trace=tuple(trace),
            structured_json=v.canonical(structured),
        )
