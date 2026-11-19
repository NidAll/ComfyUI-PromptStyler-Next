"""Deterministic detection of explicit style words inside a prompt.

This is a small curated word list, not semantic inference. It only matches whole
comma/sentence segments (for example ``cinematic lighting`` or ``watercolor (medium)``)
and a few unambiguous openings such as ``A watercolor painting of``. Subject words
inside longer descriptions are never touched.
"""

from __future__ import annotations

import re

_MEDIUM_WORDS = (
    "photo", "photograph", "photography", "raw photo", "cinematic photo", "cinematic photograph",
    "stock photo", "dslr photo", "35mm photo", "35mm photograph", "polaroid photo", "film photo",
    "film photograph", "analog photo", "portrait photo", "portrait photograph", "photorealistic",
    "photorealism", "hyperrealistic", "hyperrealism", "hyper realistic", "ultra realistic", "realistic",
    "realism", "film still", "movie still", "cinematic still", "cinematic film still",
    "anime", "anime style", "anime screenshot", "anime coloring", "anime art", "anime artwork",
    "manga", "manga style", "cartoon", "cartoon style", "comic", "comic style", "comic book style",
    "illustration", "digital illustration", "flat illustration", "vector illustration", "vector art",
    "digital painting", "digital art", "concept art", "painting", "oil painting", "acrylic painting",
    "watercolor", "watercolour", "watercolor painting", "watercolour painting", "gouache",
    "gouache painting", "ink drawing", "ink illustration", "pencil drawing", "pencil sketch",
    "graphite drawing", "charcoal drawing", "pastel drawing", "colored pencil drawing", "sketch",
    "line art", "lineart", "traditional media", "faux traditional media", "3d", "3d render",
    "3d rendering", "3d model", "cgi", "octane render", "unreal engine", "blender render",
    "render", "pixel art", "low poly", "lowpoly", "claymation", "clay render", "cel shading",
    "cel shaded", "cel-shaded", "studio ghibli style", "ukiyo-e", "woodblock print",
)
_PALETTE_WORDS = (
    "black and white", "black-and-white", "b&w", "monochrome", "monochromatic", "greyscale",
    "grayscale", "sepia", "sepia tone", "sepia toned", "desaturated", "muted colors",
    "muted colours", "muted color", "pastel colors", "pastel colours", "pastel palette",
    "vibrant colors", "vibrant colours", "vivid colors", "vivid colours", "neon colors",
    "high saturation", "low saturation", "oversaturated", "teal and orange", "orange and teal",
    "warm tones", "cool tones", "warm color palette", "cool color palette", "warm palette",
    "cool palette", "limited palette", "spot color", "colorful", "colourful", "full color",
)
_LIGHTING_WORDS = (
    "cinematic lighting", "dramatic lighting", "studio lighting", "soft lighting", "soft light",
    "natural lighting", "natural light", "golden hour", "golden hour lighting", "blue hour",
    "rim lighting", "rim light", "backlighting", "backlit", "volumetric lighting",
    "volumetric light", "god rays", "neon lighting", "neon light", "low key lighting",
    "low-key lighting", "high key lighting", "high-key lighting", "chiaroscuro", "hard light",
    "hard lighting", "harsh lighting", "moody lighting", "ambient lighting", "dramatic light",
    "cinematic light", "studio light", "softbox lighting",
)
_TEXTURE_WORDS = (
    "film grain", "grain", "grainy", "noise", "chromatic aberration", "scanlines", "vhs",
    "vhs artifacts", "vhs effect", "jpeg artifacts", "halftone", "dithering", "glitch",
    "glitch effect", "crt", "crt effect",
)

_WORDS = {
    "medium": _MEDIUM_WORDS,
    "palette": _PALETTE_WORDS,
    "lighting": _LIGHTING_WORDS,
    "texture": _TEXTURE_WORDS,
}
# Booru-style tags such as ``watercolor (medium)`` or ``1990s (style)``.
_SUFFIXES = {"medium": re.compile(r"\((?:medium|style)\)\Z")}
_LEADING = re.compile(r"\A(?:an?|the)\s+", re.I)
_TRAILING = re.compile(r"\s+(?:style|aesthetic|look)\Z", re.I)
_MEDIUM_OPENING = re.compile(
    r"\A(?P<lead>\s*)(?:an?|the)\s+(?P<phrase>[a-z0-9&' -]{2,48}?)\s+of\s+(?=\S)", re.I
)
_IN_STYLE = re.compile(
    r"\s*,?\s+in\s+(?:an?\s+|the\s+)?(?:style\s+of\s+(?:an?\s+)?)?(?P<phrase>[a-z0-9&' -]{2,48}?)(?:\s+style)?(?=\s*(?:[,.;!?]|\Z))",
    re.I,
)
AXES = tuple(_WORDS)


def _normal(segment: str) -> str:
    text = segment.replace("\\(", "(").replace("\\)", ")").replace("_", " ")
    text = " ".join(text.casefold().split()).strip(" .;:!?")
    return text


def axis_of(segment: str) -> str | None:
    """Return the style axis a whole prompt segment names, if it names one."""
    text = _normal(segment)
    if not text:
        return None
    for axis, suffix in _SUFFIXES.items():
        if suffix.search(text):
            return axis
    candidates = {text, _LEADING.sub("", text)}
    candidates |= {_TRAILING.sub("", item) for item in tuple(candidates)}
    for axis, words in _WORDS.items():
        if candidates & set(words):
            return axis
    return None


def _drop_opening(text: str, removed: list[tuple[str, str]]) -> str:
    """Remove an opening such as "A watercolor painting of", keeping capitalization."""
    opening = _MEDIUM_OPENING.match(text)
    if not opening or axis_of(opening.group("phrase")) != "medium":
        return text
    lead = opening.group("lead")
    removed.append(("medium", text[len(lead) : opening.end()].strip()))
    rest = text[opening.end() :]
    if text.strip()[:1].isupper():
        rest = rest[:1].upper() + rest[1:]
    return lead + rest


def _split_tags(prompt: str) -> list[str]:
    return prompt.split(",")


def find_tags(prompt: str, axes: set[str]) -> tuple[str, list[tuple[str, str]]]:
    """Remove whole comma-separated tags naming one of ``axes``."""
    kept: list[str] = []
    removed: list[tuple[str, str]] = []
    for part in _split_tags(prompt):
        axis = axis_of(part)
        if axis in axes:
            removed.append((axis, part.strip()))
            continue
        if "medium" in axes:
            part = _drop_opening(part, removed)
        kept.append(part)
    if not removed:
        return prompt, []
    text = ",".join(item for item in kept if item.strip())
    return text.strip(" ,"), removed


_SENTENCE = re.compile(r"([^.!?\n]*)([.!?]+|\n|\Z)")


def find_prose(prompt: str, axes: set[str]) -> tuple[str, list[tuple[str, str]]]:
    """Remove style-only segments and unambiguous medium openings from prose."""
    removed: list[tuple[str, str]] = []
    pieces: list[str] = []
    for match in _SENTENCE.finditer(prompt):
        body, end = match.group(1), match.group(2)
        if not body and not end:
            continue
        if "medium" in axes:
            body = _drop_opening(body, removed)

        def _inline(found: re.Match[str]) -> str:
            axis = axis_of(found.group("phrase"))
            if axis in axes:
                removed.append((axis, found.group(0).strip(" ,")))
                return ""
            return found.group(0)

        body = _IN_STYLE.sub(_inline, body)
        kept = []
        # Only a whole segment that is nothing but a style phrase is removed.
        for segment in body.split(","):
            axis = axis_of(segment)
            if axis in axes:
                removed.append((axis, segment.strip()))
            else:
                kept.append(segment)
        sentence = ",".join(kept).rstrip()
        if sentence.strip():
            pieces.append(sentence + end)
        elif pieces and end.strip() and not pieces[-1].rstrip().endswith((".", "!", "?")):
            pieces[-1] = pieces[-1].rstrip() + end
    if not removed:
        return prompt, []
    text = "".join(pieces)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r"(?<=[.!?])(?=\S)", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    return text, removed
