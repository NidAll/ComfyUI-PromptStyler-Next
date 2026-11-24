"""LFM3-VL layout assistant: the JSON half of the MOSS layout pipeline.

Boxes travel as ``[x1, y1, x2, y2]`` on a 0-1000 grid (left, top, right, bottom). That is the
order LFM3 writes on its own; asked for ``yxyx`` it mixes the two orders, so the model only ever
sees and writes ``xyxy`` and the MOSS converter turns it into centred pixels. Detector boxes
(WeVisOne-VL) arrive in pixels and are normalized here. Model answers are repaired leniently
(fences, stray closing brackets, repeated keys) instead of retried.

An image layout boxes only what matters: the subject, a few other things and the lettering. The
setting, scenery and repeated patterns (shelves, roses, a crowd, fog) get no box; they are named
to the describe step, which writes them into the summary caption as the background. Lettering is
found by the detector as "title"/"text" blocks in the same call as the objects, and LFM3 reads the
words while it captions, so no separate OCR pass runs.

Pure helpers import without Torch so they can be unit-tested.
"""

from __future__ import annotations

import json
import re

TASKS = ("describe_regions", "list_objects", "text_layout", "edit_layout", "image_layout")
GRID = "Boxes are [x1, y1, x2, y2] = [left, top, right, bottom] on a 0-1000 grid; the origin is the top left."
SYSTEM = (
    "You are the layout assistant of an image generator. Reply with exactly one JSON object and nothing else: "
    "no prose, no code fence."
)
# Layouts the user drew keep up to this many boxes when they are described.
MAX_REGIONS = 12
MAX_TEXT_LINES = 6
# An image layout: a few boxes on the things that matter.
MAX_THINGS = 6  # object and character boxes
MAX_TEXT = 3  # lettering blocks
MAX_SUBJECT = 5  # instances of the subject that keep their own box (the people of a group shot)
MAX_PER_LABEL = 2  # instances of any other label
MAX_OBJECTS = 4  # detector labels besides the subject; each label adds detector tokens
TEXT_QUERY = ("title", "text")  # asked of the detector when the list saw lettering
MAX_LABELS = 1 + MAX_OBJECTS + len(TEXT_QUERY)
MIN_AREA = 0.004  # of the image; smaller detections are noise for a layout
MAX_COVER = 0.9  # a detection this big is the backdrop: the summary caption already describes it
BACKDROP = 0.25  # a box this big that touches two frame edges is the setting, not a thing
SIMILAR = 0.2  # an instance under this share of its label's largest one is a minor repeat
GROUP_AREA = 0.4  # minor repeats this compact share one group box; spread wider they are background
GROUP_MIN = 3  # fewer minor repeats than this are simply dropped
PATTERN = (4, 0.3)  # a label found this often over this share of the frame is a pattern: background
CONTENTS = 0.25  # a box inside another kept thing and this much smaller is its contents (jars in a cart)
SAME = 0.75  # boxes overlapping this much (IoU) are one thing found under two names

# The setting and scenery: described as the background, never boxed (unless it is the subject itself).
STUFF = re.compile(
    r"\b(background|backdrop|scenery|landscape|setting|scene|environment|sky|skies|clouds?|fog|mist|haze|smoke|steam|"
    r"sparks?|stars|light rays|bokeh|water|sea|ocean|lake|pond|river|waves|rain|snow|grass|lawn|field|meadow|ground|"
    r"floor|carpet|rug|road|street|path|pavement|cobblestones?|wall|walls|ceiling|forest|woods|jungle|trees|foliage|"
    r"leaves|bushes|plants|flowers|petals|vines|ivy|crowd|audience|shelf|shelves|aisle|fence|city|cityscape|skyline|"
    r"buildings|mountains?|hills|horizon|sunset|sunrise|pattern|texture|wallpaper|table|tabletop|desk|counter|booth|"
    r"garden|flower ?beds?|curtains?|drapes|stage)\b",
    re.I)
# Parts and clothing of something already boxed are described in that box's caption, not boxed again.
PARTS = re.compile(r"\b(armou?r|suit|belt|boots?|shoes?|hair|clothing|clothes|outfit|shirt|t-shirt|top|skirt|dress|"
                   r"jacket|coat|pants|trousers|jeans|sleeves?|collar|gloves?|hands?|arms?|legs?|feet|foot|face|eyes?|"
                   r"head|helmet|mouth|spires?|roof|windows?|doors?|wheels?|handle|lid|label|petals?|wings?|tail)\b", re.I)
TEXT_LABELS = {"text", "title", "headline", "lettering", "caption text", "logo text", "sign text", "words"}
LETTERING = re.compile(r"\b(text|title|lettering|letters|words|headline|caption|typography|logo text)\b", re.I)


# -- JSON -----------------------------------------------------------------------------------------
def _balance(text: str) -> str:
    """Drops closing brackets that close nothing, or the wrong kind ("[1, 2]]}" -> "[1, 2]}"), outside strings."""
    out, stack, in_string, escaped = [], [], False, False
    for char in text:
        if in_string:
            escaped = not escaped and char == "\\"
            in_string = escaped or char != '"'
        elif char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]":
            if not stack or stack[-1] != char:
                continue
            stack.pop()
        out.append(char)
    return "".join(out)


def repair_json(text: str):
    """First balanced JSON object or array in ``text``; tolerates fences and trailing junk."""
    try:
        return _repair(text)
    except (ValueError, json.JSONDecodeError):
        balanced = _balance((text or "").strip())
        if balanced == (text or "").strip():
            raise
        return _repair(balanced)


def _repair(text: str):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("The model did not write JSON.")
    start = min(starts)
    depth, in_string, escaped = 0, False, False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0:
                candidate = text[start:index + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # a missing comma or a trailing comma: one cheap textual fix, then give up
                    fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
                    fixed = re.sub(r'"\s*\n\s*"', '",\n"', fixed)
                    return json.loads(fixed)
    # cut off mid-answer: close what is open so the finished part survives
    tail = text[start:]
    if in_string:
        tail += '"'
    closers = []
    for char in tail:
        if char in "{[":
            closers.append("}" if char == "{" else "]")
        elif char in "}]" and closers:
            closers.pop()
    tail = re.sub(r",\s*$", "", tail.rstrip())
    return json.loads(tail + "".join(reversed(closers)))


# -- geometry -------------------------------------------------------------------------------------
def _clamp(value) -> int:
    return max(0, min(1000, int(round(float(value)))))


def clean_box(box):
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        x1, y1, x2, y2 = (_clamp(v) for v in box)
    except (TypeError, ValueError):
        return None
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    return [x1, y1, x2, y2]


def _inside(box, outer) -> float:
    """Share of ``box`` that lies inside ``outer``."""
    w = min(box[2], outer[2]) - max(box[0], outer[0])
    h = min(box[3], outer[3]) - max(box[1], outer[1])
    return max(0.0, w) * max(0.0, h) / max(1e-9, (box[2] - box[0]) * (box[3] - box[1]))


def _area(box) -> float:
    return (box[2] - box[0]) * (box[3] - box[1]) / 1_000_000


def _iou(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    inter = max(0, w) * max(0, h) / 1_000_000
    return inter / max(1e-9, _area(a) + _area(b) - inter)


def _union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _edges(box, margin=15) -> int:
    """How many frame edges a box touches."""
    return sum((box[0] <= margin, box[1] <= margin, box[2] >= 1000 - margin, box[3] >= 1000 - margin))


def is_text_label(label: str) -> bool:
    label = str(label or "").strip().lower()
    return label in TEXT_LABELS or bool(LETTERING.search(label))


def _detections(boxes, width: int, height: int):
    """Detector boxes in pixels ({x, y, width, height, label}) -> [{label, bbox, rank}] on the 0-1000 grid.
    ``rank`` is the label's order of first appearance, which is the order of the detector query."""
    found, ranks = [], {}
    for box in boxes or []:
        if not isinstance(box, dict):
            continue
        try:
            x, y, w, h = (float(box[k]) for k in ("x", "y", "width", "height"))
        except (KeyError, TypeError, ValueError):
            continue
        cleaned = clean_box([x / width * 1000, y / height * 1000, (x + w) / width * 1000, (y + h) / height * 1000])
        label = str(box.get("label") or "object").strip()[:60] or "object"
        key = label.lower()
        ranks.setdefault(key, len(ranks))
        if cleaned is None or _area(cleaned) < MIN_AREA:
            continue
        found.append({"label": label, "bbox": cleaned, "rank": ranks[key]})
    return found


def _text_blocks(found, things):
    """Detector lettering boxes -> at most MAX_TEXT blocks: overlapping boxes join, a "text" box inside a
    "title" box is part of it, and a block that is mostly inside an object box (a label on a jar) stays only
    when it is big."""
    blocks = []
    for item in sorted(found, key=lambda f: (f["rank"], -_area(f["bbox"]))):
        box = item["bbox"]
        merged = False
        for block in blocks:
            if _inside(box, block["bbox"]) >= 0.6 or _iou(box, block["bbox"]) >= 0.3:
                if _inside(box, block["bbox"]) < 0.6:
                    block["bbox"] = _union([block["bbox"], box])
                merged = True
                break
        if not merged:
            blocks.append({"label": "text", "bbox": list(box), "read": True})
    blocks = [b for b in blocks if not any(_inside(b["bbox"], t["bbox"]) >= 0.9 and _area(b["bbox"]) < 0.01 for t in things)]
    blocks.sort(key=lambda b: _area(b["bbox"]), reverse=True)
    blocks = blocks[:MAX_TEXT]
    blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))  # reading order
    return blocks


def select_regions(boxes, width: int, height: int):
    """Detector boxes in pixels -> (regions back to front, background notes).

    Kept: the subject (the first label asked; up to MAX_SUBJECT instances), up to MAX_PER_LABEL instances of
    every other label, and the lettering. Instances much smaller than their label's largest join one group box
    when they sit together, else they become background. Setting and scenery (STUFF, or a big box touching two
    frame edges), full-frame boxes, parts of a boxed thing and duplicates under a second name are dropped; their
    names come back as notes so the describe step can put them in the background sentence.
    """
    found = _detections(boxes, width, height)
    notes = []
    note = lambda label: notes.append(label) if label.lower() not in (n.lower() for n in notes) else None  # noqa: E731
    text = [f for f in found if is_text_label(f["label"])]
    things = [f for f in found if not is_text_label(f["label"])]
    if len(things) > 1:
        for f in things:
            if _area(f["bbox"]) >= MAX_COVER:
                note(f["label"])
        things = [f for f in things if _area(f["bbox"]) < MAX_COVER] or things[:1]
    subject = min((f["rank"] for f in things), default=0)  # the first label asked that is not the backdrop
    candidates = []
    for f in things:
        lead = f["rank"] == subject
        if not lead and (STUFF.search(f["label"]) or (_area(f["bbox"]) >= BACKDROP and _edges(f["bbox"]) >= 2)):
            note(f["label"])
            continue
        candidates.append(f)
    selected, groups, leftovers = [], [], []
    for rank in sorted({f["rank"] for f in candidates}):
        group = sorted((f for f in candidates if f["rank"] == rank), key=lambda f: _area(f["bbox"]), reverse=True)
        if rank != subject and len(group) >= PATTERN[0] and _area(_union([f["bbox"] for f in group])) >= PATTERN[1]:
            note(group[0]["label"])  # trees of a forest, roses all over, the buildings of a city
            continue
        largest = _area(group[0]["bbox"])
        keep = [f for f in group if _area(f["bbox"]) >= SIMILAR * largest][:MAX_SUBJECT if rank == subject else MAX_PER_LABEL]
        rest = [f for f in group if f not in keep]
        if len(rest) >= GROUP_MIN and _area(_union([f["bbox"] for f in rest])) <= GROUP_AREA:
            groups.append({"label": group[0]["label"], "bbox": _union([f["bbox"] for f in rest]), "rank": rank + 0.5,
                           "count": len(rest)})
        elif rest and not PARTS.search(group[0]["label"]):
            leftovers.extend(rest)
        selected.extend(keep)

    # parts or clothing inside another kept box (armour on a knight, the spires of a cathedral) go first; then
    # the small contents of a kept object that ranks before them (jars in a cart). What the subject holds stays.
    # Neither is background: the caption of the box that holds them covers them.
    selected = [s for s in selected if s["rank"] == subject or not PARTS.search(s["label"]) or not any(
        o is not s and o["rank"] != s["rank"] and _inside(s["bbox"], o["bbox"]) >= 0.8 for o in selected)]
    kept = [s for s in selected if s["rank"] == subject or not any(
        subject != o["rank"] < s["rank"] and _inside(s["bbox"], o["bbox"]) >= 0.8
        and _area(s["bbox"]) <= CONTENTS * _area(o["bbox"]) for o in selected)]
    selected = kept + [g for g in groups if not any(_inside(g["bbox"], k["bbox"]) >= 0.6 for k in kept)]
    final = []
    for s in sorted(selected, key=lambda s: (s["rank"], -_area(s["bbox"]))):
        if any(_iou(s["bbox"], k["bbox"]) >= SAME for k in final):
            continue  # "vase" after "flower vase"
        if len(final) >= MAX_THINGS:
            note(s["label"])
            continue
        final.append(s)
    for f in leftovers:  # a spare instance is background unless a kept box holds it (jars in the cart)
        if not any(_inside(f["bbox"], k["bbox"]) >= 0.8 for k in final):
            note(f["label"])
    regions = [{"label": s["label"], "bbox": s["bbox"], **({"count": s["count"]} if s.get("count") else {})}
               for s in sorted(final, key=lambda s: _area(s["bbox"]), reverse=True)]
    return regions + _text_blocks(text, final), notes


def normalize_detections(boxes, width: int, height: int):
    """Detector boxes -> kept regions (see ``select_regions``), text blocks included."""
    return select_regions(boxes, width, height)[0]


def merge_regions(detections, lines):
    """Detector regions plus OCR lines; detector lettering gives way to the exact lines it holds, so the
    words are boxed once."""
    lines = list(lines)
    if not lines:
        return list(detections)
    kept = [d for d in detections
            if not ((d.get("read") or LETTERING.search(d["label"]))
                    and any(_inside(line["bbox"], d["bbox"]) >= 0.6 for line in lines))]
    return kept + lines


def text_lines(words, width: int, height: int):
    """OCR word boxes -> text regions, one per line of lettering (reading order)."""
    items = []
    for word in words or []:
        if not isinstance(word, dict):
            continue
        label = str(word.get("label") or "").strip()
        try:
            x, y, w, h = (float(word[k]) for k in ("x", "y", "width", "height"))
        except (KeyError, TypeError, ValueError):
            continue
        if not label or w <= 0 or h <= 0:
            continue
        items.append({"text": label, "x1": x, "y1": y, "x2": x + w, "y2": y + h})
    # Left to right, so a word joins the line it continues; lines are then read top to bottom.
    items.sort(key=lambda i: i["x1"])
    lines = []
    for item in items:
        cy, h = (item["y1"] + item["y2"]) / 2, item["y2"] - item["y1"]
        for line in lines:
            lh = line["y2"] - line["y1"]
            gap = item["x1"] - line["x2"]
            if abs(cy - (line["y1"] + line["y2"]) / 2) < 0.5 * max(h, lh) and -0.5 * h < gap < 1.5 * max(h, lh):
                line["words"].append(item["text"])
                line["x2"] = max(line["x2"], item["x2"])
                line["y1"], line["y2"] = min(line["y1"], item["y1"]), max(line["y2"], item["y2"])
                break
        else:
            lines.append({**item, "words": [item["text"]]})
    lines.sort(key=lambda line: (line["y1"], line["x1"]))
    regions = []
    for line in lines[:MAX_TEXT_LINES]:
        box = clean_box([line["x1"] / width * 1000, line["y1"] / height * 1000,
                         line["x2"] / width * 1000, line["y2"] / height * 1000])
        if box is not None:
            regions.append({"label": "text", "text": " ".join(line["words"]), "bbox": box})
    return regions


# -- prompts --------------------------------------------------------------------------------------
def _listing(regions):
    rows = []
    for index, region in enumerate(regions, 1):
        if region.get("text"):
            what = f'text "{region["text"]}"'
        elif region.get("read"):
            what = "text (lettering: read its words)"
        else:
            what = region.get("label", "object")
        if region.get("count"):
            what += f" (a group of {region['count']})"
        hint = f' (now: {region["hint"]})' if region.get("hint") else ""
        rows.append(f"{index}. {what}{hint} {region['bbox']}")
    return "\n".join(rows)


def _key(index: int, region) -> str:
    # No quotes or backslashes: the model copies keys back verbatim, and an escaped quote comes back bare.
    what = f'text {region["text"]}' if region.get("text") else region.get("label", "object")
    return re.sub(r'["\\\s]+', " ", f"{index} {what}").strip()[:48]


PLACES = {"top left": (0, 0), "top": (None, 0), "top right": (2, 0), "left": (0, None), "center": (1, 1),
          "right": (2, None), "bottom left": (0, 2), "bottom": (None, 2), "bottom right": (2, 2)}
NUDGE = {"higher": (0, -150), "lower": (0, 150), "more left": (-150, 0), "more right": (150, 0)}
SIZES = {"small": 0.06, "medium": 0.14, "large": 0.3}  # share of the canvas a new box covers
MARGIN = 40
WHERE = re.compile(  # "in the lower left corner", "across the top of the poster": stale once a box moves
    r"[,;]?\s*\b(?:across|at|in|on|along|near|to(?:wards?)?)\s+the\s+(?:very\s+)?(?:top|bottom|left|right|upper|lower|"
    r"middle|center|centre)(?:\s+(?:left|right|center|centre|middle))?(?:\s+(?:side|corner|edge|half|part|third))?"
    r"(?:\s+of\s+the\s+(?:poster|image|picture|frame|canvas|page|scene|cover))?(?!\s+of\b)", re.I)
# What an instruction asks for. A 2B model restates or invents changes ("size": "smaller" for a coat colour),
# so a change only applies when the instruction asks for that kind of change.
ASKS = {
    "place": re.compile(r"\b(move|put|place|shift|left|right|top|bottom|cent(?:er|re)|middle|corner|up|down|higher|"
                        r"lower|swap|side|above|below|position|edge)\b", re.I),
    "size": re.compile(r"\b(bigger|larger|smaller|tiny|huge|enormous|grow|shrink|enlarge|scale|size|resize|wider|"
                       r"narrower|taller|shorter)\b", re.I),  # not "small": "add a small lamp" sizes the lamp only
    "remove": re.compile(r"\b(remove|delete|drop|without|erase|rid|take out|no more|lose|hide|get rid)\b", re.I),
    "add": re.compile(r"\b(add|put|place|include|insert|give|draw|new|another|plus|show|with|and an?)\b", re.I),
    "text": re.compile(r"\b(say|says|read|reads|title|text|words?|lettering|rename|write|spell|sign|headline|logo)\b"
                       r"|[\"'“‘][^\"'”’]+[\"'”’]|\b[A-Z]{2,}\b"),
}
CHANGE_NOTE = re.compile(r"^\s*(?:it\s+|is\s+)?(?:moved|now\b(?!\s+wear)|changed|unchanged|no change|same|removed|added|"
                         r"resized|made|placed|stays)\b|\bmoved to\b", re.I)
APPEND = re.compile(r"^(?:now\s+)?(wearing|with|holding|in|on|under|carrying|dressed|under|beside|lit|covered|"
                    r"soaked|surrounded)\b", re.I)
# "looking to the left" is where something faces, not where it sits in the frame
MOTION = {"looking", "looks", "facing", "faces", "turned", "turning", "pointing", "points", "gazing", "glancing",
          "staring", "leaning", "walking", "running", "heading", "moving", "flying", "swimming", "reaching"}


def _strip_where(text: str) -> str:
    """Drops where-in-the-frame phrases from a caption, keeping directions ("looking to the left")."""
    def drop(match):
        before = text[:match.start()].rstrip(" ,;").rsplit(" ", 1)[-1].lower()
        return match.group(0) if before in MOTION else ""
    return re.sub(r"\s+([,.;])", r"\1", WHERE.sub(drop, text)).strip(" ,;")


MORE = re.compile(r"\b(another|second|more|two|three|four|several|extra|copy|duplicate|twin)\b", re.I)


def _cell(box):
    """(column, row) of a box on a 3x3 grid; a box spanning most of an axis is in its middle."""
    x1, y1, x2, y2 = box
    return (min(2, int((x1 + x2) / 2 / 334)) if x2 - x1 < 700 else 1,
            min(2, int((y1 + y2) / 2 / 334)) if y2 - y1 < 700 else 1)


def _where(box) -> str:
    """A box in words: its place on a 3x3 grid and how big it is ("top, wide", "bottom left, small")."""
    x1, y1, x2, y2 = box
    col, row = _cell(box)
    place = next((name for name, (c, r) in PLACES.items() if (c, r) == (col, row)), "")
    place = place or {(1, 0): "top", (1, 2): "bottom", (0, 1): "left", (2, 1): "right"}[(col, row)]
    area = (x2 - x1) * (y2 - y1) / 1e6
    w, h = x2 - x1, y2 - y1
    size = ("wide" if w >= 700 or (w >= 400 and w >= 3 * h) else "tall" if h >= 700 else
            "small" if area < 0.06 else "large" if area > 0.25 else "")
    return f"{place}, {size}" if size else place


def _edit_row(item) -> str:
    what = f'text "{_sentence(item.get("text"), 80)}"' if item.get("text") else _sentence(item.get("label"), 40) or "object"
    caption = _sentence(item.get("caption"), 120)
    box = clean_box(item.get("bbox"))
    return f"{what} ({_where(box) if box else 'no box'})" + (f": {caption}" if caption else "")


def _placed(box, place: str):
    """The box moved to a named place (its size kept) or nudged; an unknown place leaves it."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    place = re.sub(r"\s+", " ", str(place or "").lower().replace("-", " ")).strip()
    place = {"middle": "center", "centre": "center", "up": "higher", "down": "lower", "upper left": "top left",
             "upper right": "top right", "lower left": "bottom left", "lower right": "bottom right"}.get(place, place)
    if place in NUDGE:
        dx, dy = NUDGE[place]
        x1, y1 = min(max(0, x1 + dx), 1000 - w), min(max(0, y1 + dy), 1000 - h)
        return [x1, y1, x1 + w, y1 + h]
    if place not in PLACES:
        return box
    col, row = PLACES[place]
    here = _cell(box)
    col, row = (None if col == here[0] else col), (None if row == here[1] else row)  # already there: stay put
    at = lambda cell, size, start: start if cell is None else (MARGIN, (1000 - size) // 2, 1000 - MARGIN - size)[cell]  # noqa: E731
    x1, y1 = max(0, at(col, w, x1)), max(0, at(row, h, y1))
    return [x1, y1, min(1000, x1 + w), min(1000, y1 + h)]


def _sized(box, size: str, width: int, height: int):
    """"bigger" / "smaller" scale the box about its centre, kept on the canvas."""
    factor = {"bigger": 1.3, "larger": 1.3, "large": 1.3, "smaller": 0.75, "small": 0.75}.get(str(size or "").lower().strip())
    if not factor:
        return box
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    w, h = min(1000, (x2 - x1) * factor), min(1000, (y2 - y1) * factor)
    x1, y1 = min(max(0, cx - w / 2), 1000 - w), min(max(0, cy - h / 2), 1000 - h)
    return [round(x1), round(y1), round(x1 + w), round(y1 + h)]


def _new_box(change, is_text: bool, width: int, height: int):
    """A box for an added thing: the size word picks its area (lettering is a wide band), the place puts it."""
    size = str(change.get("size") or "").lower().strip()
    if size not in SIZES:  # "a small lamp": the size word in the name or caption
        said = f'{change.get("add") or ""} {change.get("caption") or ""}'.lower()
        size = ("small" if re.search(r"\b(small|tiny|little|mini)\b", said) else
                "large" if re.search(r"\b(large|big|huge|giant|tall)\b", said) else "medium")
    share = SIZES[size]
    if is_text:
        w, h = round(min(900, 1000 * share ** 0.5 * 2)), round(min(300, 1000 * share ** 0.5 / 2))
    else:  # square in pixels: the grid is stretched to the canvas
        side = (share * width * height) ** 0.5
        w, h = round(min(1000, side / width * 1000)), round(min(1000, side / height * 1000))
    x1, y1 = (1000 - w) // 2, (1000 - h) // 2
    return _placed([x1, y1, x1 + w, y1 + h], change.get("place") or "center")


def _target(change, items) -> int | None:
    """The item a change names: its number (1-based, "2" or "2 cat"), else a label or the words it shows."""
    ref = change.get("item")
    if isinstance(ref, (int, float)) or (isinstance(ref, str) and re.match(r"\s*\d+", ref)):
        index = int(re.match(r"\s*(\d+)", str(int(ref) if isinstance(ref, float) else ref)).group(1)) - 1
        return index if 0 <= index < len(items) else None
    name = _sentence(ref, 80).lower()
    if not name:
        return None
    for index, item in enumerate(items):
        if name in (str(item.get("label", "")).lower(), str(item.get("text", "")).lower()):
            return index
    return next((i for i, item in enumerate(items) if name in str(item.get("label", "")).lower()), None)


def _recaption(item, caption: str) -> str:
    """A new caption from an edit: a note about the change is ignored, a trailing detail ("wearing a red coat")
    joins the old caption, a full description that no longer names the item ("a rainy night scene" for the
    cat) is ignored."""
    old = _sentence(item.get("caption"))
    if not caption or CHANGE_NOTE.search(caption):
        return old
    if old and APPEND.match(caption):
        detail = re.sub(r"^now\s+", "", caption.rstrip("."))
        return f"{old.rstrip('.')}, {detail}."
    stems = {re.sub(r"(?<=[^s])e?s$", "", w) for w in re.findall(r"[a-z]{3,}", str(item.get("label", "")).lower())}
    said = {re.sub(r"(?<=[^s])e?s$", "", w) for w in re.findall(r"[a-z]{3,}", caption.lower())}
    if old and stems and not stems & said and not item.get("text"):
        return old
    return caption[0].upper() + caption[1:]


LOG = re.compile(r"\b(removed|deleted|erased|added|moved|replaced|changed|resized|unchanged)\b", re.I)
SCENE = re.compile(r"^\s*(?:please\s+)?(?:make|turn|change|set)\s+(?:it|this|everything|the\s+(?:scene|picture|image|"
                   r"poster|whole\s+thing))\s+(?:into\s+|to\s+|at\s+)?(.+?)[.!]*\s*$", re.I)


def _head(item) -> set:
    """Words that name an item in a sentence: its label words (stems), and "title"/"text" plus its words for
    lettering."""
    words = {re.sub(r"(?<=[^s])e?s$", "", w) for w in re.findall(r"[a-z]{3,}", str(item.get("label", "")).lower())}
    if item.get("text"):
        words |= {"title", "text", "word", "lettering", "heading", "headline", "sign", "logo"}
        words |= set(re.findall(r"[a-z]{3,}", str(item.get("text", "")).lower()))
    return words - {"text"} if item.get("text") and len(words) > 1 else words


def _clauses(summary: str):
    return [c for c in re.split(r"(?<=[.!?])\s+|,\s*", summary) if c.strip()]


def _mentions(clause: str, item) -> bool:
    said = {re.sub(r"(?<=[^s])e?s$", "", w) for w in re.findall(r"[a-z]{3,}", clause.lower())}
    return bool(_head(item) & said)


def _resummarize(summary: str, before, after, gone, request: str) -> str:
    """Keeps the summary true to the edit: clauses about removed items or that log the edit go, new words replace
    old ones, a moved item's place phrase follows its box, and "make it a rainy night" adds that sentence."""
    out = []
    for clause in _clauses(summary):
        if LOG.search(clause) or any(_mentions(clause, item) for item in gone):
            continue
        for old, new in zip(before, after):
            if old.get("text") and new.get("text") and old["text"] != new["text"]:
                clause = re.sub(re.escape(old["text"]), new["text"], clause, flags=re.I)
            if old.get("bbox") != new.get("bbox") and _mentions(clause, old) and WHERE.search(clause):
                clause = WHERE.sub(f" at the {_where(new['bbox']).split(',')[0]}", clause, count=1)
        out.append(clause.strip())
    text = ""
    for clause in out:  # rejoin: a clause after a full stop starts a sentence, the rest follow a comma
        text += (" " if not text or text.endswith((".", "!", "?")) else ", ") + clause
    text = text.strip()
    text = text[:1].upper() + text[1:]
    if text and not text.endswith((".", "!", "?")):
        text += "."
    match = SCENE.match(request or "")
    if match and not ASKS["place"].search(match.group(1)):
        scene = match.group(1).strip()
        text = f"{text} {scene[0].upper()}{scene[1:]}.".strip()
    return text


def apply_edit(layout, data, request: str = "", width: int = 1024, height: int = 1024):
    """Edit answer -> the whole layout. ``data["changes"]`` names what to change, item by item, in words
    (place, size, caption, text, remove) and what to add; the geometry is worked out here, since a 2B model
    copies coordinates back unmoved. An answer that is a whole layout ("items") is taken as it is."""
    layout = layout if isinstance(layout, dict) else {}
    changes = data.get("changes")
    if isinstance(data.get("items"), list) and not isinstance(changes, list):
        return data
    items = [dict(i) for i in layout.get("items", []) if isinstance(i, dict)]
    removed, added = set(), []
    asked = lambda kind: not request or bool(ASKS[kind].search(request))  # noqa: E731
    said = {re.sub(r"(?<=[^s])e?s$", "", w) for w in re.findall(r"[a-z]{3,}", request.lower())}

    def named(item) -> bool:
        words = {re.sub(r"(?<=[^s])e?s$", "", w) for w in re.findall(r"[a-z]{3,}", str(item.get("label", "")).lower())}
        if item.get("text"):
            words |= {"title", "text", "word", "lettering", "heading", "headline", "sign", "logo"}
            words |= {w for w in re.findall(r"[a-z]{3,}", str(item.get("text", "")).lower())}
        return bool(words & said)

    # An instruction that names some items changes only those ("Remove the cat" leaves the woman's caption).
    focus = {i for i, item in enumerate(items) if named(item)}
    names = lambda: {re.sub(r"(?<=[^s])e?s$", "", str(i.get("label", "")).lower()) for i in items}  # noqa: E731
    for change in changes if isinstance(changes, list) else []:
        if not isinstance(change, dict):
            continue
        if change.get("add"):
            if not asked("add"):
                continue
            label = _sentence(change.get("add"), 60)
            words = _sentence(change.get("text"), 200).strip('"')
            is_text = bool(words) and bool(re.search(r"\b(title|text|letter|word|sign|logo|headline|caption)", label.lower()))
            if not is_text and re.sub(r"(?<=[^s])e?s$", "", label.lower()) in names() and not MORE.search(request):
                continue  # the model re-added a thing that is already there
            caption = _strip_where(_sentence(change.get("caption")))
            caption = caption[:1].upper() + caption[1:]  # the box says where it is
            item = clean_item({"label": label, "caption": caption, "text": words,
                               "bbox": clean_box(change.get("bbox")) or _new_box(change, is_text, width, height)})
            if item:
                added.append(item)
            continue
        index = _target(change, items)
        if index is None or (focus and index not in focus):
            continue
        item = items[index]
        if change.get("remove") not in (None, False, "false", "no") and asked("remove"):
            removed.add(index)
            continue
        box = clean_box(item.get("bbox"))
        if box and not item.get("locked"):
            moved = _placed(box, change.get("place")) if asked("place") else box
            moved = _sized(moved, change.get("size"), width, height) if asked("size") else moved
            if clean_box(change.get("bbox")) and not change.get("place") and asked("place"):
                moved = clean_box(change.get("bbox"))
            if moved != box:
                item["caption"] = _strip_where(item.get("caption", ""))
            item["bbox"] = moved
        if _sentence(change.get("caption")):
            item["caption"] = _recaption(item, _sentence(change.get("caption")))
        words = _sentence(change.get("text"), 200).strip('"')
        if words and asked("text") and words != item.get("text") and (item.get("text") or is_text_label(str(item.get("label", "")))):
            caption = _without_words(_without_words(item.get("caption", ""), item.get("text", "")), words)
            item["text"], item["label"] = words, "text"
            item["caption"] = caption or item.get("caption", "")
    gone = [item for index, item in enumerate(items) if index in removed]
    before = [dict(i) for i in layout.get("items", []) if isinstance(i, dict)]
    summary = _sentence(data.get("summary")) if isinstance(data.get("summary"), str) else ""
    if CHANGE_NOTE.search(summary) or LOG.search(summary) or re.search(r"(?i)\b(no|new) summary\b", summary):
        summary = ""  # a note about the edit ("with the cat removed"), not a description of the picture
    if summary:
        summary = _resummarize(summary, [], [], gone, "")
    else:
        summary = _resummarize(_sentence(layout.get("caption")), before, items, gone, request)
    items = [item for index, item in enumerate(items) if index not in removed] + added
    return {"caption": summary or _sentence(layout.get("caption")), "meta": layout.get("meta") or [], "items": items}


def _canvas(width: int, height: int) -> str:
    shape = "square" if abs(width - height) < 32 else ("portrait" if height > width else "landscape")
    return f"{shape} {width}x{height}"


def messages(task, *, request="", regions=(), layout=None, has_image=False, width=1024, height=1024, background=()):
    """Chat for one task; returns (messages, max_new_tokens). ``background`` names things that have no box
    (describe_regions writes them into the background sentence)."""
    regions = list(regions)
    if task == "list_objects":
        # The subject goes first: the detector answers labels in query order under a length cap, so the
        # first label is never cut off. Lettering adds "title"/"text" to the detector query.
        user = (
            'Return {"subject": "...", "objects": ["..."], "background": ["..."], "lettering": false} for this image. '
            '"subject": who or what the picture is about, as a short noun a detector can find. People or animals '
            'come first: "person" for several people, otherwise a specific noun such as "goblin", "woman in a red '
            'coat", "black cat", "koi fish". '
            '"objects": at most 4 other separate things that matter, most important first, as short nouns, for '
            'example "lantern", "mug", "sports car". Not the setting (sky, forest, water, floor, wall, table, '
            'shelves, buildings), not parts of something listed (armor, roof, wheel, hair) and not things that '
            'repeat all over (flowers, leaves, stars, a crowd). '
            '"background": 1 to 4 short nouns for the setting and the repeated things, for example "misty forest", '
            '"red roses". '
            '"lettering": true only if the image shows readable words, a title or a logo.'
        )
        budget = 130
    elif task == "describe_regions":
        n = len(regions)
        reading = [index for index, region in enumerate(regions, 1) if region.get("read")]
        scene = "" if has_image else f"Scene: {request.strip() or 'not given'}\n"
        look = "in this image" if has_image else "for this scene"
        unboxed = f"No box (background): {', '.join(background)}\n" if background else ""
        # Keys carry each region's number and name, so every caption lands on its own box.
        keys = ", ".join(json.dumps(_key(index, region)) + ': "..."' for index, region in enumerate(regions, 1))
        words = (', "words": {' + ", ".join(f'"{index}": "..."' for index in reading) + "}") if reading else ""
        user = (
            f"{scene}{GRID}\nRegions:\n{_listing(regions)}\n{unboxed}"
            f'Return {{"caption": "...", "background": "...", "meta": ["..."], "boxes": {{{keys}}}{words}}}. '
            f'"caption": one sentence on the whole picture {look}: subject, action and composition. '
            '"background": one sentence on what lies behind the boxes: the place, scenery, light and any '
            "repeated pattern, including everything listed as having no box. "
            '"meta": 3 to 6 style tags such as "watercolor", "cinematic photo", "flat vector", "moody". '
            '"boxes": for each region, one sentence of at most 25 words on what is inside that box only: '
            "appearance, colours, material, pose. A (now: ...) note says what the box holds: keep that subject "
            "and describe it afresh. A group region describes the whole group. Do not repeat the name or the "
            "numbers. For a text region describe the lettering (font style, colour, effect), not its words."
            + (' "words": the exact words written in each text region, as printed.' if reading else "")
        )
        budget = min(1200, 150 + 48 * n + 24 * len(reading))
    elif task == "text_layout":
        user = (
            f"Canvas: {_canvas(width, height)}. {GRID}\nMake a layout for: {request.strip()}\n"
            'Return {"caption": "two sentences: the subject and composition, then the background", "meta": ["3 to 6 '
            'style tags: medium, look, mood; never the subjects"], '
            '"items": [{"label": "short noun, or text for lettering", "caption": "one detailed sentence, at most '
            '30 words", "text": "exact words, only for text items", "bbox": [x1, y1, x2, y2]}]}. '
            "Use 2 to 6 items for the subjects, important objects and lettering, listed back to front. Give each a "
            "box that matches its size and place. The setting and scenery go in the caption, not in boxes."
        )
        budget = 700
    elif task == "edit_layout":
        # The model names the changes in words (place, size, caption, words, remove, add) and apply_edit does the
        # geometry: asked for coordinates or the whole layout, a 2B model copies the boxes back unmoved.
        items = [i for i in (layout or {}).get("items", []) if isinstance(i, dict)]
        rows = "\n".join(f"{index}. {_edit_row(item)}" for index, item in enumerate(items, 1)) or "(no items yet)"
        summary = _sentence((layout or {}).get("caption"), 300)
        places = ", ".join(PLACES) + ", " + ", ".join(NUDGE)
        user = (
            f"Canvas: {_canvas(width, height)}.\nSummary: {summary or 'none'}\nItems, back to front:\n{rows}\n"
            f"Instruction: {request.strip()}\n"
            'Return {"changes": [...], "summary": "..."} with one entry per thing the instruction asks for:\n'
            '{"item": N, "place": "..."} moves item N; place is one of: ' + places + '.\n'
            '{"item": N, "size": "bigger"} or "smaller" resizes it.\n'
            '{"item": N, "caption": "new sentence"} changes how it looks.\n'
            '{"item": N, "text": "new words"} changes the words of a text item.\n'
            '{"item": N, "remove": true} removes it.\n'
            '{"add": "short noun, or text for lettering", "caption": "one sentence", "text": "exact words, only for '
            'lettering", "place": "...", "size": "small, medium or large"} adds something new.\n'
            "N is the item number. Change only what the instruction asks for; an item it does not mention gets no "
            "entry. A caption is the full new description of the item, not a note about the change. "
            '"summary": a new description of the whole picture when the scene, setting, weather or light changes or '
            "the changes make the summary wrong; else leave it out.\n"
            'Example: items 1. dog (center), 2. text "HELLO" (top, wide); instruction "put the dog on the left, write '
            'GOODBYE and make it snowy" -> {"changes": [{"item": 1, "place": "left"}, {"item": 2, "text": "GOODBYE"}], '
            '"summary": "A dog stands on the left of a snowy field, with GOODBYE written across the top."}'
        )
        budget = min(900, 200 + 50 * len(items))
    elif task == "image_layout":
        user = (
            f"{GRID}\nDescribe this image as a layout. "
            'Return {"caption": "two sentences: the subject and composition, then the background", "meta": ["3 to 6 '
            'style tags: medium, look, mood; never the subjects"], '
            '"items": [{"label": "short noun, or text for lettering", "caption": "one sentence, at most 25 words", '
            '"text": "exact words, only for text items", "bbox": [x1, y1, x2, y2]}]} for the 2 to 6 main '
            "subjects, objects and lettering, listed back to front. The setting goes in the caption, not in boxes."
        )
        budget = 640
    else:
        raise ValueError(f"Unknown layout task: {task}")
    content = ([{"type": "image"}] if has_image else []) + [{"type": "text", "text": user}]
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}], budget


# -- answers --------------------------------------------------------------------------------------
def _words(value, limit=6):
    if isinstance(value, str):
        value = re.split(r"[,;/]", value)
    if not isinstance(value, list):
        return []
    out = []
    for entry in value:
        for part in (re.split(r"[,;]", entry) if isinstance(entry, str) else []):
            part = part.strip().strip(".").strip()
            if part and part.lower() not in (w.lower() for w in out):
                out.append(part[:40])
    return out[:limit]


def _sentence(value, limit=400) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit] if isinstance(value, str) else ""


def _numbered(value, n: int, slots=None) -> list:
    """{"1 dog": "...", "2 cat": "..."} -> values in region order; unnumbered answers fill the gaps in order
    (only the indices in ``slots`` when given)."""
    out, loose = [""] * n, []
    for key, entry in value.items():
        text = _sentence(entry) if isinstance(entry, str) else ""
        match = re.match(r"\s*(\d+)", str(key))
        if match and 1 <= int(match.group(1)) <= n and not out[int(match.group(1)) - 1]:
            out[int(match.group(1)) - 1] = text
        else:
            loose.append(text)
    for index in (range(n) if slots is None else slots):
        if not out[index] and loose:
            out[index] = loose.pop(0)
    return out


def _captions(data, n: int) -> list:
    """Per-region captions: the numbered "boxes" object (keys "1 dog", "2 cat"), else a list in order."""
    boxes = data.get("boxes")
    if isinstance(boxes, dict):
        return _numbered(boxes, n)
    captions = data.get("captions") if isinstance(data.get("captions"), list) else boxes
    if not isinstance(captions, list) and isinstance(data.get("items"), list):
        captions = [i.get("caption") if isinstance(i, dict) else i for i in data["items"]]
    return [_sentence(c) if isinstance(c, str) else "" for c in (captions or [])]


def _salvage(raw_text: str):
    """Captions from a describe answer that will not parse (a bare quote inside a value): the
    "N ...": "..." pairs, the caption, background, meta and words, read field by field."""
    text = str(raw_text or "")
    words_at = text.find('"words"')
    head, tail = (text[:words_at], text[words_at:]) if words_at >= 0 else (text, "")
    boxes = {m.group(1): m.group(2) for m in re.finditer(r'"(\d+)\b[^:\n]*?"\s*:\s*"((?:[^"\\]|\\.)*)"', head)}
    if not boxes:
        return None
    field = lambda name: re.search(rf'"{name}"\s*:\s*"((?:[^"\\]|\\.)*)"', head)  # noqa: E731
    meta = re.search(r'"meta"\s*:\s*\[([^\]]*)\]', head)
    words = {m.group(1): m.group(2) for m in re.finditer(r'"(\d+)"\s*:\s*"((?:[^"\\]|\\.)*)"', tail)}
    return {"caption": field("caption").group(1) if field("caption") else "",
            "background": field("background").group(1) if field("background") else "", "boxes": boxes,
            "meta": re.findall(r'"([^"]+)"', meta.group(1)) if meta else [], "words": words}


def _salvage_edit(raw_text: str):
    """Changes from an edit answer that will not parse: each change object that parses on its own, and the
    summary."""
    text = str(raw_text or "")
    changes = []
    for chunk in re.findall(r"\{[^{}]*\}", text):
        try:
            change = json.loads(re.sub(r",\s*}", "}", chunk))
        except json.JSONDecodeError:
            continue
        if isinstance(change, dict) and ("item" in change or "add" in change):
            changes.append(change)
    summary = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if not changes and not summary:
        return None
    return {"changes": changes, **({"summary": summary.group(1)} if summary else {})}


def _unecho(caption: str, region) -> str:
    """Drops an echoed "woman [150, 0, 1000, 995]" lead-in; the box is already that woman."""
    text = re.sub(r"\s+", " ", re.sub(r"\[\s*\d+(?:\s*,\s*\d+){3}\s*\]", "", caption)).strip(" ,;")
    label = str(region.get("label", "")).strip()
    rest = text[len(label):].strip(" :,-") if label and text.lower().startswith(label.lower() + " ") else ""
    if rest and rest.split(" ", 1)[0].lower() not in LINKS:  # "clothing black top" -> "Black top"
        text = rest[0].upper() + rest[1:]
    return text


def _unplaced(caption: str) -> str:
    """Drops where-in-the-frame phrases ("on the left", "at the top center"): the box already says where."""
    if not WHERE.search(caption):
        return caption
    text = _strip_where(caption)
    return text[:1].upper() + text[1:] if len(re.findall(r"[A-Za-z]{2,}", text)) >= 3 else caption


def _without_words(caption: str, words: str) -> str:
    """A text box's caption describes the look; the words are already its text ("The title 'CATS' in red" ->
    "The title in red"). A caption that was only the words is dropped."""
    if not caption or not words:
        return caption
    lead = r"(?:(?:spelling|reading|saying|that (?:says|reads)|with the (?:words?|text))\s+)?"
    pattern = re.compile(lead + r"[\"'“”‘’]?\s*" + r"\s+".join(map(re.escape, words.split())) + r"\s*[\"'“”‘’]?", re.I)
    if not pattern.search(caption):
        return caption
    text = re.sub(r"\s+", " ", pattern.sub(" ", caption)).strip(" ,;:-")
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text[:1].upper() + text[1:] if len(re.findall(r"[A-Za-z]{2,}", text)) >= 3 else ""


def _lettering(value) -> str:
    """Words read from a text region: one line, no wrapping quotes, nothing that only says it is unreadable."""
    text = _sentence(value, 200).strip("\"'“”‘’ ")
    if not text or re.fullmatch(r"(?i)(none|n/?a|unreadable|illegible|unknown|no text|\.\.\.|…)", text):
        return ""
    return text


LINKS = {"in", "with", "on", "of", "at", "is", "are", "holding", "wearing", "standing", "sitting"}
ECHO_META = {"medium", "rendering", "mood", "style", "style words", "words", "tags", "..."}


def clean_item(raw):
    if not isinstance(raw, dict):
        return None
    box = clean_box(raw.get("bbox"))
    if box is None:
        return None
    label = _sentence(raw.get("label"), 60) or "object"
    text = _sentence(raw.get("text"), 200).strip('"')
    is_text = label.lower() in TEXT_LABELS or ("text" in label.lower().split())
    if text and not is_text and text.lower() in (label.lower(), _sentence(raw.get("caption")).lower()):
        text = ""  # the model echoed the label as lettering ("Red fox"): it would be drawn as words
    if text and not is_text:
        is_text = bool(re.search(r"\b(title|text|letter|word|sign|logo|headline)", label.lower()))
    item = {"label": "text" if is_text and text else label, "caption": _sentence(raw.get("caption")), "bbox": box}
    if is_text and text:
        item["text"] = text
        item["caption"] = _without_words(item["caption"], text)
    for key in ("locked",):
        if raw.get(key):
            item[key] = True
    return item


def _objects(names, limit):
    """List answer nouns -> detector labels: lower case, no repeats, no noun already inside a longer one
    ("vase" after "flower vase"), the setting and parts left out."""
    out = []
    stem = lambda word: re.sub(r"(?<=[^s])e?s$", "", word)  # noqa: E731  "hammers" and "hammer", "boxes" and "box"
    for name in names:
        name = re.sub(r"\s+", " ", name.strip().strip(".")).lower()[:40]
        if not name or any(stem(name) == stem(o) or re.search(rf"\b{re.escape(stem(name))}e?s?\b", o) for o in out):
            continue
        if out and (STUFF.search(name) or PARTS.search(name) or is_text_label(name)):
            continue  # the subject itself may be scenery ("cathedral", "mountain lake")
        out.append(name)
    return out[:limit]


def parse_answer(task, raw_text, regions=(), layout=None, request=""):
    """Model answer -> normalized layout dict. Raises ValueError when nothing usable came back. ``layout`` is
    the layout an edit_layout answer changes (its width/height size new boxes), ``request`` the instruction."""
    try:
        data = repair_json(raw_text)
    except ValueError:
        data = (_salvage(raw_text) if task == "describe_regions" else
                _salvage_edit(raw_text) if task == "edit_layout" else None)
        if not data:
            raise
    if task == "list_objects":
        objects = data.get("objects") if isinstance(data, dict) else data
        subject = data.get("subject") if isinstance(data, dict) else None
        names = [o for o in ([subject] if isinstance(subject, str) else []) + (objects if isinstance(objects, list) else [])
                 if isinstance(o, str) and o.strip()]
        if not names:
            raise ValueError("The model listed no objects.")
        background = _words(data.get("background") if isinstance(data, dict) else None, 6)
        # an object the list also calls background ("rose" beside "red roses") is a pattern, not a thing to box
        scenery = " ".join(background).lower()
        names = names[:1] + [n for n in names[1:] if not re.search(
            rf"\b{re.escape(re.sub(r'(?<=[^s])e?s$', '', n.strip().lower()))}(e?s)?\b", scenery)]
        kept = _objects(names, 1 + MAX_OBJECTS)
        dropped = [n.strip().lower() for n in names if n.strip().lower() not in kept and STUFF.search(n)]
        lettering = data.get("lettering") if isinstance(data, dict) else None
        # Only an explicit false skips the lettering labels; a missing or odd value looks for lettering.
        return {"objects": kept, "background": list(dict.fromkeys(background + dropped))[:6],
                "lettering": lettering is not False and str(lettering).lower() != "false"}
    if not isinstance(data, dict):
        raise ValueError("The model's answer is not a layout object.")
    if task == "edit_layout":
        size = layout if isinstance(layout, dict) else {}
        data = apply_edit(layout, data, request, int(size.get("width") or 1024), int(size.get("height") or 1024))
    out = {"caption": _sentence(data.get("caption")), "meta": [w for w in _words(data.get("meta"), 8) if w.lower() not in ECHO_META][:6]}
    if task == "describe_regions":
        background = _sentence(data.get("background"))
        if background and background.lower() not in out["caption"].lower():
            out["caption"] = f"{out['caption']} {background}".strip()
        captions = _captions(data, len(regions))
        rescued = None
        if not all(captions[:len(regions)]):  # the repair may have dropped a malformed entry
            rescued = _salvage(raw_text) or {}
            again = _captions(rescued, len(regions))
            captions = [c or (again[i] if i < len(again) else "") for i, c in enumerate(captions + [""] * (len(regions) - len(captions)))]
        captions = [_unplaced(_unecho(c, regions[i])) if i < len(regions) else c for i, c in enumerate(captions)]
        words = data.get("words") if isinstance(data.get("words"), dict) else (rescued or _salvage(raw_text) or {}).get("words") or {}
        slots = [index for index, region in enumerate(regions) if region.get("read")]
        read = _numbered(words, len(regions), slots) if isinstance(words, dict) else [""] * len(regions)
        items = []
        for index, region in enumerate(regions):
            item = {"label": region.get("label", "object"), "caption": captions[index] if index < len(captions) else "",
                    "bbox": list(region["bbox"])}
            if region.get("text"):
                item["label"], item["text"] = "text", region["text"]
            elif region.get("read"):
                lettering = _lettering(read[index])
                if not lettering:
                    continue  # a lettering block the model could not read would be drawn empty
                item["label"], item["text"] = "text", lettering
            if item.get("text"):
                item["caption"] = _without_words(item["caption"], item["text"])
            if region.get("locked"):
                item["locked"] = True
            items.append(item)
        out["items"] = items
        out["described"] = sum(1 for item in items if item["caption"])
        return out
    items = [clean_item(item) for item in (data.get("items") or [])]
    out["items"] = [item for item in items if item is not None][:MAX_REGIONS + MAX_TEXT_LINES]
    # Style tags name the look; one that repeats a box's subject or lettering ("pagoda", "KYOTO") is dropped.
    subjects = {w.lower().rstrip("s") for item in out["items"] for w in (item["label"], item.get("text", "")) if w}
    out["meta"] = [m for m in out["meta"] if m.lower().rstrip("s") not in subjects]
    if not out["items"] and not out["caption"]:
        raise ValueError("The model wrote no usable boxes.")
    return out


# -- one task, without the model ------------------------------------------------------------------
def frame(boxes):
    """First frame of a detector answer: a dict, a flat list, or per-frame lists."""
    if isinstance(boxes, dict):
        return [boxes]
    if isinstance(boxes, (list, tuple)) and boxes and isinstance(boxes[0], (list, tuple)):
        return list(boxes[0])
    return list(boxes or [])


def _json(value, name: str):
    if isinstance(value, str):
        try:
            return json.loads(value) if value.strip() else {}
        except json.JSONDecodeError as error:
            raise ValueError(f"{name} is not JSON: {error}") from error
    return value or {}


def prepare(task, *, request="", layout=None, objects=None, words=None, image_size=None, scene=None, lettering=True):
    """Everything before the model call. ``image_size`` is the picture's (width, height) when there is one;
    ``objects``/``words`` are detector boxes in its pixels; ``scene`` is a list_objects result (its background
    nouns join the describe step's list of things without a box); ``lettering`` False drops detected lettering.

    Returns a job: ``task`` (describe_regions becomes image_layout when nothing was found), ``messages``,
    ``budget``, ``use_image``, ``regions``, ``background``, ``warnings``, ``layout``, ``request``."""
    if task not in TASKS:
        raise ValueError(f"task must be one of {', '.join(TASKS)}")
    given = _json(layout, "layout")
    width, height = image_size or (1024, 1024)
    if isinstance(given, dict) and given.get("width") and given.get("height"):
        width, height = int(given["width"]), int(given["height"])
    try:
        listed = _json(scene, "scene")
    except ValueError:
        listed = {}
    regions, warnings, background = [], [], []
    if task == "describe_regions":
        if (objects is not None or words is not None) and image_size:
            regions, background = select_regions(frame(objects), *image_size)
            if not lettering:
                regions = [region for region in regions if not region.get("read")]
            regions = merge_regions(regions, text_lines(frame(words), *image_size))
            if isinstance(listed, dict) and isinstance(listed.get("background"), list):
                background = list(dict.fromkeys(background + [str(b)[:40] for b in listed["background"]]))[:8]
        else:
            for item in (given.get("items") or []) if isinstance(given, dict) else []:
                box = clean_box(item.get("bbox")) if isinstance(item, dict) else None
                if box:
                    # A caption the box already has says what it holds (a rewrite would otherwise only see "object").
                    hint = " ".join(str(item.get("caption") or "").split())[:120]
                    regions.append({"label": str(item.get("label") or "object")[:60], "bbox": box,
                                    **({"text": str(item["text"])[:200]} if item.get("text") else {}),
                                    **({"hint": hint} if hint else {})})
            regions = regions[: MAX_REGIONS + MAX_TEXT_LINES]
        if not regions:
            if not image_size:
                raise ValueError("Draw or detect at least one box to describe")
            task = "image_layout"
            warnings.append("The detector found nothing, so the model placed the boxes itself.")
    if task in ("list_objects", "image_layout") and not image_size:
        raise ValueError("This task needs an image")
    if task in ("text_layout", "edit_layout") and not str(request).strip():
        raise ValueError("Write what the layout should show or change")
    summary = given.get("caption", "") if isinstance(given, dict) else ""
    chat, budget = messages(
        task, request=request if task != "describe_regions" else (request or summary), regions=regions,
        layout=given if task == "edit_layout" else None,
        has_image=bool(image_size) and task not in ("text_layout", "edit_layout"),
        width=width, height=height, background=background,
    )
    return {"task": task, "messages": chat, "budget": budget, "regions": regions, "background": background,
            "warnings": warnings, "layout": given, "request": request,
            "use_image": bool(image_size) and task in ("list_objects", "describe_regions", "image_layout")}


def finish(job, raw_text):
    """The model's answer for a prepared job -> (layout dict, detector labels). The labels (one per line, the
    subject first, then "title"/"text" when the list saw lettering) are only set for list_objects. Raises
    ValueError for an unreadable answer, except a list, which falls back to looking for the main subject."""
    task, warnings = job["task"], list(job["warnings"])
    try:
        result = parse_answer(task, raw_text, job["regions"], layout=job["layout"] if task == "edit_layout" else None,
                              request=job["request"])
    except (ValueError, json.JSONDecodeError):
        if task != "list_objects":
            raise
        result = {"objects": [], "background": [], "lettering": True}
        warnings.append("The model listed no objects; the detector looked for the main subject instead.")
    labels = ""
    if task == "list_objects":
        # Lettering is found in the same detector call as the objects; the describe step reads it.
        labels = "\n".join((result.get("objects") or ["main subject"])
                           + (list(TEXT_QUERY) if result.get("lettering", True) is not False else []))
    result.update({"task": task, "grid": "xyxy-1000", **({"warnings": warnings} if warnings else {})})
    return result, labels
