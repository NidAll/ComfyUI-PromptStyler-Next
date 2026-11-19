"""Audit bundled authoring contracts; content flags are review hints, not NLP verdicts.

Style text is read by image text encoders, not by an instruction-following model:
clauses are short descriptive phrases, tags are short and model-recognizable, and no
clause negates, instructs, conditions or refers to "the scene". ``--vocab`` accepts a
local newline or JSON tag vocabulary (for example a booru tagger's tag list) and
requires each tag-profile look to carry at least one recognized core tag.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from promptstyler_next import Engine
from promptstyler_next import validation as v

HARD_PALETTE = re.compile(r"\b(monochrome|black[- ]and[- ]white|grayscale|greyscale)\b", re.I)
CONTENT_HINT = re.compile(
    r"\b(?:empty|unoccupied|deserted|vacant) (?:school|hotel|office|corridor|hospital|stage|playground)\b"
    r"|\b(?:add|insert) (?:a|an) (?:timecode|timestamp|caption|person|figure|door|window)\b"
    r"|\b(?:replace|remove) (?:the )?(?:people|person|subject|objects)\b",
    re.I,
)
COMMANDS = frozenset(
    """use keep let treat favor favour render give make preserve reveal separate build balance retain
    translate allow combine emphasize emphasise present hold organize organise describe frame apply
    arrange interpret add show place set push limit reserve ensure introduce align reduce restrict
    soften lower raise shift mark replace convert turn depict style compose suggest maintain create
    invite express concentrate imply anchor position diffuse flatten illuminate route open leave
    draw paint print carve rework reimagine recast transform give avoid include employ prefer""".split()
)
# Also adjectives or nouns ("open planes", "diffuse light", "frame edges"): an instruction
# only when a determiner follows.
AMBIGUOUS = frozenset("open frame diffuse paint print draw carve mark set place limit shift route show style turn".split())
DETERMINERS = frozenset("the a an each every all its this these those any".split())
META = re.compile(
    r"\b(?:the (?:scene|subject|image|picture|frame|prompt|base|user)|existing|supplied|requested|"
    r"original|user's|already|retain(?:ing|s)?|preserv(?:e|es|ing))\b",
    re.I,
)
NEGATION = re.compile(r"\b(?:without|no|not|never|avoid|instead of|rather than|free of|don't|unlike)\b", re.I)
CONDITIONAL = re.compile(r"\b(?:if|otherwise|unless|where the|when the)\b", re.I)
LIMITS = {"core_words": 8, "clause_words": 12, "look_words": 26, "tag_words": 4, "tags": 3}


def _vocabulary(path: Path | None) -> frozenset[str] | None:
    if path is None:
        return None
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
        items = data.get("tags", data) if isinstance(data, dict) else data
    except ValueError:
        items = raw.splitlines()
    return frozenset(str(item).replace("_", " ").strip().casefold() for item in items if str(item).strip())


def _lint_clause(clause: dict[str, Any], tier: int) -> list[str]:
    reasons = []
    text = clause["text"]
    words = text.split()
    first = words[0].casefold().strip(",") if words else ""
    following = words[1].casefold() if len(words) > 1 else ""
    if first in COMMANDS and (first not in AMBIGUOUS or following in DETERMINERS):
        reasons.append("Clause starts with an instruction; describe the visual result instead.")
    if META.search(text):
        reasons.append("Clause refers to the prompt or scene; describe only the visual treatment.")
    for value in (text, *clause["tags"]):
        if NEGATION.search(value):
            reasons.append("Negation reaches the encoder as the negated words; phrase it positively.")
            break
    if CONDITIONAL.search(text):
        reasons.append("Conditional wording cannot be followed by an image encoder.")
    if any(mark in text for mark in "()[]{}:;"):
        reasons.append("Brackets or colons in clause text read as prompt syntax.")
    if len(words) > (LIMITS["core_words"] if tier == 0 else LIMITS["clause_words"]):
        reasons.append("Clause is too long for its tier.")
    if not 1 <= len(clause["tags"]) <= LIMITS["tags"]:
        reasons.append(f"Use 1-{LIMITS['tags']} tags per clause.")
    for tag in clause["tags"]:
        if len(tag.split()) > LIMITS["tag_words"]:
            reasons.append("A tag is too long; tags are short labels.")
            break
    if clause["min_intensity"] not in v.TIERS:
        reasons.append(f"Use a standard tier threshold {v.TIERS}.")
    if clause["axis"] == "mood":
        reasons.append("Mood is not directly visible; express it through light, palette or composition.")
    return reasons


def audit(engine: Engine | None = None, vocabulary: frozenset[str] | None = None) -> dict[str, Any]:
    engine = engine or Engine.builtin()
    styles = []
    offset = 0
    while True:
        page = engine.list_styles(limit=1000, offset=offset)
        styles.extend(page)
        if len(page) < 1000:
            break
        offset += len(page)
    errors: list[dict[str, str]] = []
    candidates: list[dict[str, str]] = []
    tag_stats = Counter()
    clause_count = 0
    tag_profiles = {profile["id"] for profile in engine.profiles() if profile["format"] == "tags"}
    # The vocabulary check targets booru-trained tag models; SDXL reads plain tags.
    vocab_profiles = {profile for profile in tag_profiles if profile.startswith("anima")}
    for style in styles:
        versions = [("base", style["clauses"])] + [
            (model, variant["clauses"]) for model, variant in style["variants"].items()
        ]
        for axis, identity in style["claims"].items():
            if identity != style["id"]:
                errors.append({"id": style["id"], "variant": "base", "axis": axis, "reason": "Claim identity must be the style ID."})
        expected = {"grade": "grades", "modifier": "effects"}.get(style["kind"])
        if expected and style["category"].split("/")[0] != expected:
            errors.append({"id": style["id"], "variant": "base", "axis": "", "reason": f"{style['kind']} category must start with {expected}/."})
        for variant_name, clauses in versions:
            tiers = [sum(c["min_intensity"] >= t for t in v.TIERS[1:]) for c in clauses]
            total = sum(len(c["text"].split()) for c in clauses)
            if style["kind"] == "style" and total > LIMITS["look_words"]:
                errors.append({"id": style["id"], "variant": variant_name, "axis": "", "reason": "Look adds too many words at full strength."})
            if not clauses or tiers[0] != 0:
                errors.append({"id": style["id"], "variant": variant_name, "axis": "", "reason": "The first clause must be the core tier."})
            if style["kind"] == "style" and clauses and clauses[0]["axis"] != "medium":
                errors.append({"id": style["id"], "variant": variant_name, "axis": "", "reason": "A look starts with its medium."})
            tag_variant = variant_name in vocab_profiles or (
                variant_name == "base" and not (set(style["variants"]) >= vocab_profiles)
            )
            eligible_for_tags = not style["models"] or set(style["models"]) & vocab_profiles
            if vocabulary is not None and tag_variant and eligible_for_tags and style["kind"] == "style":
                core = [tag.casefold() for c, t in zip(clauses, tiers) if t == 0 for tag in c["tags"]]
                known = [tag for clause in clauses for tag in clause["tags"] if tag.casefold() in vocabulary]
                tag_stats["tags"] += sum(len(clause["tags"]) for clause in clauses)
                tag_stats["known"] += len(known)
                tag_stats["looks"] += 1
                tag_stats["core_known"] += any(tag in vocabulary for tag in core)
                if not known:
                    errors.append({"id": style["id"], "variant": variant_name, "axis": "medium", "reason": "No recognized tag for tag models."})
            for clause, tier in zip(clauses, tiers):
                clause_count += 1
                location = {"id": style["id"], "variant": variant_name, "axis": clause["axis"]}
                if clause["axis"] not in style["claims"]:
                    errors.append({**location, "reason": "Unclaimed bundled clause axis."})
                rendered = [clause["text"], *clause["tags"]]
                if clause["axis"] != "palette" and any(HARD_PALETTE.search(s) for s in rendered):
                    errors.append({**location, "reason": "Hard palette wording outside palette axis."})
                for reason in _lint_clause(clause, tier):
                    errors.append({**location, "reason": reason})
                for text in rendered:
                    if CONTENT_HINT.search(text):
                        candidates.append({**location, "text": text})
    return {
        "schema_version": 1,
        "catalog_fingerprint": engine.catalog_fingerprint,
        "entries": len(styles),
        "packs": len({style["pack_id"] for style in styles}),
        "profiles": len(engine.profiles()),
        "kinds": dict(sorted(Counter(style["kind"] for style in styles).items())),
        "clauses_including_variants": clause_count,
        "error_reasons": dict(Counter(error["reason"] for error in errors).most_common()),
        "known_tag_share": round(tag_stats["known"] / tag_stats["tags"], 3) if tag_stats["tags"] else None,
        "looks_with_known_core_tag": round(tag_stats["core_known"] / tag_stats["looks"], 3) if tag_stats["looks"] else None,
        "authoring_errors": errors,
        "content_review_candidates": candidates,
        "limits": "Content hints are incomplete heuristics. No image quality or semantic fidelity is inferred.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on bundled authoring contract errors.")
    parser.add_argument("--summary", action="store_true", help="Omit the per-clause error list.")
    parser.add_argument("--vocab", type=Path, help="Local tag vocabulary for tag-model checks.")
    args = parser.parse_args()
    result = audit(vocabulary=_vocabulary(args.vocab))
    if args.summary:
        result = {key: value for key, value in result.items() if key != "authoring_errors"}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if args.check and result.get("error_reasons") else 0


if __name__ == "__main__":
    raise SystemExit(main())
