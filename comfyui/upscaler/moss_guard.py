"""Temporary output guard for the MOSS upsampler v2 fine-tune (`moss-qwen3.5-2b-upsampler-v2`).

v2 has three known output defects. The guard removes them using only the user's draft for context:

* D1 visible text the user did not ask for (watermarks, signatures, credit lines, quoted titles, lettering);
* D2 negation tails ("with no modern signage"), removed because text-to-image encoders tend to draw
  the thing they name;
* D3 color words when the draft asks for black and white.

`prep` also swaps provenance tokens in the draft ("trending on artstation", "8k", "unreal engine") for
what they mean visually; in training they were the most common source of watermark sentences.

These are regular expressions, so wording the patterns do not list ("a block-letter motif", "glyphs")
still gets through. Remove this module once a retrained model fixes the defects. Pure Python, no Torch.
"""

from __future__ import annotations

import re

# The user asked for on-image text: leave text descriptions alone.
ASK_TEXT = re.compile(
    r"[\"“”]|\b(?:text|says|saying|logo|title|sign|signage|poster|label|typography|typographic|"
    r"lettering|banner|caption|headline|font|book cover|album cover|menu|placard|slogan|quote)\b",
    re.I,
)
TEXTY = re.compile(
    r"\b(?:reads?|reading|saying|says|titled|spells? out|bearing the words|emblazoned with|stamped with)\s*:?\s*[\"“']"
    r"|\bsign(?:age)?\s*[:,]?\s*[\"“']"
    r"|\b(?:lettering|watermark(?:ed)?|caption(?:ed)?|signed by|credit line|typograph\w*|inscription|text overlay|"
    r"title card|wordmark|letterform\w*|lettered|block[- ]letter\w*|monogram|"
    r"(?:uppercase|capital|bold|block|neon|painted|gilded|gold|large|carved) letters)\b"
    r"|\bsignature(?!\s+(?:style|palette|brushwork|look|colou?r|technique|aesthetic|move|lighting|mood))\b",
    re.I,
)
NEG_ASK = re.compile(r"\b(?:no|without|free of)\b", re.I)
NEG_CLAUSE = re.compile(
    r",?\s*\b(?:with no|without any|without|free of|devoid of|absent of|no visible|no sign of|no trace of)\b[^.;,]*",
    re.I,
)
MONO = re.compile(r"\b(?:black[- ]and[- ]white|b\s*&\s*w|monochrome|grayscale|greyscale)\b", re.I)
COLOR = re.compile(
    r"\b(?:red|crimson|scarlet|blue|azure|cobalt|teal|green|emerald|yellow|amber|orange|purple|violet|"
    r"magenta|pink|turquoise)(?:-(?:tinted|toned|colou?red|hued))?\s+(?!hour\b)",
    re.I,
)
IDIOMS = re.compile(r"\b(?:golden|blue) hour\b", re.I)
# One quoted item: double quotes may hold apostrophes ("LADIES' DRESS"); single quotes may not.
_QUOTED = r"(?:[\"“][^\"”]{0,60}[\"”]|'[^']{0,60}')"
# The verb and every quoted item after it ('signs reading "COFFEE" and "CIGARS"' -> 'signs').
QUOTED_PHRASE = re.compile(
    r"\s*\b(?:reads?|reading|saying|says|titled|spells? out|bearing the words|emblazoned with|stamped with)"
    r"\s*:?\s*" + _QUOTED + r"(?:\s*,?\s*(?:and\s+|or\s+)?" + _QUOTED + r")*",
    re.I,
)
SENT = re.compile(r"(?<=[.!?])\s+")
CLAUSE_START = re.compile(r"(?:,\s+|;\s+|\s+and\s+|\s+while\s+|\s+with\s+)")

# Provenance tokens in the draft and the visual meaning that replaces them (artist names and titles stay).
PROVENANCE = (
    (re.compile(r"\btrending on (?:art ?station(?:hq)?|deviantart|behance|cgsociety|pixiv)\b", re.I), "polished concept art"),
    (re.compile(r"\b(?:unreal engine(?: \d)?|octane render)\b", re.I), "crisp high-detail 3D render"),
    (re.compile(r"\b(?:8k|4k|uhd)\b", re.I), "ultra-detailed"),
)

# Cleaning that would remove more than this share of the prompt is refused (resample instead).
MIN_KEEP = 0.7
SKIPPED = "guard skipped: would remove too much, consider resampling"


def prep(user: str) -> str:
    """Replace provenance tokens in the draft with what they mean visually."""
    for pattern, replacement in PROVENANCE:
        user = pattern.sub(replacement, user)
    return user


def _strip_text_clause(sentence: str) -> str:
    """Cut a sentence from the clause that mentions visible text; drop it if that text is its subject."""
    sentence = QUOTED_PHRASE.sub("", sentence)  # 'a firework reads "your name"' -> 'a firework'
    match = TEXTY.search(sentence)
    if not match:
        return sentence
    starts = [c.start() for c in CLAUSE_START.finditer(sentence, 0, match.start())]
    if starts and starts[-1] >= 0.25 * len(sentence):  # keep the main clause
        return sentence[: starts[-1]].rstrip(" ,;") + "."
    return ""


def defects(user: str, text: str) -> int:
    """Count detectable defects in an upsampled prompt (used to pick the best of several takes)."""
    d1 = 0 if ASK_TEXT.search(user) else len(TEXTY.findall(text))
    d2 = 0 if NEG_ASK.search(user) else len(NEG_CLAUSE.findall(text))
    d3 = len(COLOR.findall(IDIOMS.sub("", text))) if MONO.search(user) else 0
    return d1 + d2 + d3


def clean(user: str, text: str, min_keep: float = MIN_KEEP) -> tuple[str, list[str]]:
    """Return (cleaned prompt, report). If cleaning would remove too much, the original comes back."""
    out, report = text.strip(), []
    if not NEG_ASK.search(user):
        count = len(NEG_CLAUSE.findall(out))
        if count:
            out = NEG_CLAUSE.sub("", out)
            report.append(f"removed {count} negation clause(s)")
    if not ASK_TEXT.search(user):
        sentences = SENT.split(out)
        kept = [_strip_text_clause(s) for s in sentences]
        count = sum(a != b for a, b in zip(sentences, kept))
        if count:
            out = " ".join(s for s in kept if s)
            report.append(f"removed text from {count} sentence(s)")
    if MONO.search(user):
        count = len(COLOR.findall(IDIOMS.sub("", out)))
        if count:
            out = COLOR.sub("", out)
            report.append(f"removed {count} color word(s)")
        if not MONO.search(out):
            out = "Black-and-white photograph. " + out
            report.append("prefixed black-and-white")
    out = re.sub(r"\s+([.,;])", r"\1", re.sub(r"\s{2,}", " ", out)).replace("..", ".").strip()
    if len(out) < min_keep * len(text):
        return text, [SKIPPED]
    return out, report
