"""Audit bundled authoring contracts; content flags are review hints, not NLP verdicts."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from typing import Any

from promptstyler_next import Engine

HARD_PALETTE = re.compile(r"\b(monochrome|black[- ]and[- ]white|grayscale|greyscale)\b", re.I)
CONTENT_HINT = re.compile(
    r"\b(?:empty|unoccupied|deserted|vacant) (?:school|hotel|office|corridor|hospital|stage|playground)\b"
    r"|\b(?:add|insert) (?:a|an) (?:timecode|timestamp|caption|person|figure|door|window)\b"
    r"|\b(?:replace|remove) (?:the )?(?:people|person|subject|objects)\b",
    re.I,
)


def audit(engine: Engine | None = None) -> dict[str, Any]:
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
    clause_count = 0
    for style in styles:
        versions = [("base", style["clauses"])] + [
            (model, variant["clauses"]) for model, variant in style["variants"].items()
        ]
        for variant_name, clauses in versions:
            for clause in clauses:
                clause_count += 1
                location = {"id": style["id"], "variant": variant_name, "axis": clause["axis"]}
                if clause["axis"] not in style["claims"]:
                    errors.append({**location, "reason": "Unclaimed bundled clause axis."})
                rendered = [clause["text"], *clause["tags"]]
                if clause["axis"] != "palette" and any(HARD_PALETTE.search(s) for s in rendered):
                    errors.append({**location, "reason": "Hard palette wording outside palette axis."})
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
        "authoring_errors": errors,
        "content_review_candidates": candidates,
        "limits": "Content hints are incomplete heuristics. No image quality or semantic fidelity is inferred.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on bundled authoring contract errors.")
    args = parser.parse_args()
    result = audit()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if args.check and result["authoring_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
