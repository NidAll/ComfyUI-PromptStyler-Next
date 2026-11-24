"""LFM3-VL layout assistant: the JSON half of the MOSS layout pipeline.

Boxes travel as ``[x1, y1, x2, y2]`` on a 0-1000 grid (left, top, right, bottom). That is the
order LFM3 writes on its own; asked for ``yxyx`` it mixes the two orders, so the model only ever
sees and writes ``xyxy`` and the MOSS converter turns it into centred pixels. Detector boxes
(WeVisOne-VL) arrive in pixels and are normalized here. Model answers are repaired leniently
(fences, stray closing brackets, repeated keys) instead of retried.

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
MAX_REGIONS = 12
MAX_TEXT_LINES = 6
MAX_PER_LABEL = 3
MAX_COVER = 0.9  # a detection this big is the backdrop: the summary caption already describes it
# Parts and clothing of someone already boxed are described in that box's caption, not boxed again.
PARTS = re.compile(r"\b(armou?r|belt|boots?|shoes?|hair|clothing|clothes|outfit|shirt|t-shirt|top|skirt|dress|jacket|coat|"
                   r"pants|trousers|jeans|sleeves?|collar|gloves?|hands?|arms?|legs?|feet|foot|face|eyes?|head|helmet|mouth)\b", re.I)
MIN_AREA = 0.003  # of the image; smaller detections are noise for a layout
TEXT_LABELS = {"text", "title", "headline", "lettering", "caption text", "logo text", "sign text", "words"}


# -- JSON -----------------------------------------------------------------------------------------
def repair_json(text: str):
    """First balanced JSON object or array in ``text``; tolerates fences and trailing junk."""
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


def normalize_detections(boxes, width: int, height: int):
    """Detector boxes in pixels ({x, y, width, height, label}) -> regions, big first (back to front)."""
    regions = []
    for box in boxes or []:
        if not isinstance(box, dict):
            continue
        try:
            x, y, w, h = (float(box[k]) for k in ("x", "y", "width", "height"))
        except (KeyError, TypeError, ValueError):
            continue
        cleaned = clean_box([x / width * 1000, y / height * 1000, (x + w) / width * 1000, (y + h) / height * 1000])
        if cleaned is None or _area(cleaned) < MIN_AREA:
            continue
        regions.append({"label": str(box.get("label") or "object").strip()[:60] or "object", "bbox": cleaned})
    regions.sort(key=lambda r: _area(r["bbox"]), reverse=True)
    if len(regions) > 1:
        regions = [r for r in regions if _area(r["bbox"]) < MAX_COVER]
    kept, per_label = [], {}
    for region in regions:
        key = region["label"].lower()
        if per_label.get(key, 0) >= MAX_PER_LABEL:
            continue
        if PARTS.search(key) and any(_inside(region["bbox"], other["bbox"]) >= 0.8 for other in kept):
            continue
        per_label[key] = per_label.get(key, 0) + 1
        kept.append(region)
    return kept[:MAX_REGIONS]


LETTERING = re.compile(r"\b(text|title|lettering|letters|words|headline|caption|typography|logo text)\b", re.I)


def merge_regions(detections, lines):
    """Detector boxes plus OCR lines; a detector box for the lettering itself ("title text") gives way to the
    exact lines it holds, so the words are boxed once."""
    lines = list(lines)
    kept = [d for d in detections
            if not (LETTERING.search(d["label"]) and any(_inside(line["bbox"], d["bbox"]) >= 0.6 for line in lines))]
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
        what = f'text "{region["text"]}"' if region.get("text") else region.get("label", "object")
        hint = f' (now: {region["hint"]})' if region.get("hint") else ""
        rows.append(f"{index}. {what}{hint} {region['bbox']}")
    return "\n".join(rows)


def _key(index: int, region) -> str:
    # No quotes or backslashes: the model copies keys back verbatim, and an escaped quote comes back bare.
    what = f'text {region["text"]}' if region.get("text") else region.get("label", "object")
    return re.sub(r'["\\\s]+', " ", f"{index} {what}").strip()[:48]


def _canvas(width: int, height: int) -> str:
    shape = "square" if abs(width - height) < 32 else ("portrait" if height > width else "landscape")
    return f"{shape} {width}x{height}"


def messages(task, *, request="", regions=(), layout=None, has_image=False, width=1024, height=1024):
    """Chat for one task; returns (messages, max_new_tokens)."""
    regions = list(regions)
    if task == "list_objects":
        user = (
            "List the 3 to 8 main visible things in this image as short nouns a detector can find, for example "
            '"woman", "red car", "street lamp". Name whole things: not the parts or clothing of a person or '
            "animal. Skip the background, the sky and tiny details. "
            'Return {"objects": ["..."]}.'
        )
        budget = 90
    elif task == "describe_regions":
        n = len(regions)
        scene = "" if has_image else f"Scene: {request.strip() or 'not given'}\n"
        look = "in this image" if has_image else "for this scene"
        # Keys carry each region's number and name, so every caption lands on its own box.
        keys = ", ".join(json.dumps(_key(index, region)) + ': "..."' for index, region in enumerate(regions, 1))
        user = (
            f"{scene}{GRID}\nRegions:\n{_listing(regions)}\n"
            f'Return {{"caption": "...", "meta": ["..."], "boxes": {{{keys}}}}}. '
            f'"caption": two sentences on the whole picture {look}: subject, setting, light and composition. '
            '"meta": 3 to 6 style tags such as "watercolor", "cinematic photo", "flat vector", "moody". '
            '"boxes": for each region, one sentence of at most 25 words on what is inside that box only: '
            "appearance, colours, material, pose. A (now: ...) note says what the box holds: keep that subject "
            "and describe it afresh. Do not repeat the name or the numbers. For a text region "
            "describe the lettering (font style, colour, effect), not its words."
        )
        budget = min(1100, 110 + 48 * n)
    elif task == "text_layout":
        user = (
            f"Canvas: {_canvas(width, height)}. {GRID}\nMake a layout for: {request.strip()}\n"
            'Return {"caption": "two sentences for the whole picture", "meta": ["3 to 6 style tags: medium, look, mood; never the subjects"], '
            '"items": [{"label": "short noun, or text for lettering", "caption": "one detailed sentence, at most '
            '30 words", "text": "exact words, only for text items", "bbox": [x1, y1, x2, y2]}]}. '
            "Use 3 to 8 items, listed back to front. Give each subject a box that matches its size and place; "
            "only a background item may cover the whole canvas."
        )
        budget = 760
    elif task == "edit_layout":
        compact = json.dumps(layout or {}, ensure_ascii=False, separators=(",", ":"))
        n = len((layout or {}).get("items", []))
        user = (
            f"Canvas: {_canvas(width, height)}. {GRID}\nLayout:\n{compact}\nInstruction: {request.strip()}\n"
            "Return the whole updated layout in the same format. Keep every item the instruction does not "
            "mention exactly as it is, in the same order; add new items at the end."
        )
        budget = min(1400, 160 + 80 * (n + 2))
    elif task == "image_layout":
        user = (
            f"{GRID}\nDescribe this image as a layout. "
            'Return {"caption": "two sentences for the whole picture", "meta": ["3 to 6 style tags: medium, look, mood; never the subjects"], '
            '"items": [{"label": "short noun, or text for lettering", "caption": "one sentence, at most 25 words", '
            '"text": "exact words, only for text items", "bbox": [x1, y1, x2, y2]}]} for the 3 to 8 main '
            "elements, listed back to front."
        )
        budget = 700
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


def _captions(data, n: int) -> list:
    """Per-region captions: the numbered "boxes" object (keys "1 dog", "2 cat"), else a list in order."""
    boxes = data.get("boxes")
    if isinstance(boxes, dict):
        out = [""] * n
        loose = []
        for key, value in boxes.items():
            text = _sentence(value) if isinstance(value, str) else ""
            match = re.match(r"\s*(\d+)", str(key))
            if match and 1 <= int(match.group(1)) <= n and not out[int(match.group(1)) - 1]:
                out[int(match.group(1)) - 1] = text
            else:
                loose.append(text)
        for index in range(n):  # unnumbered answers fill the gaps in order
            if not out[index] and loose:
                out[index] = loose.pop(0)
        return out
    captions = data.get("captions") if isinstance(data.get("captions"), list) else boxes
    if not isinstance(captions, list) and isinstance(data.get("items"), list):
        captions = [i.get("caption") if isinstance(i, dict) else i for i in data["items"]]
    return [_sentence(c) if isinstance(c, str) else "" for c in (captions or [])]


def _salvage(raw_text: str):
    """Captions from a describe answer that will not parse (a bare quote inside a value): the
    "N ...": "..." pairs, the caption and the meta words, read field by field."""
    text = str(raw_text or "")
    boxes = {m.group(1): m.group(2) for m in re.finditer(r'"(\d+)\b[^:\n]*?"\s*:\s*"((?:[^"\\]|\\.)*)"', text)}
    if not boxes:
        return None
    caption = re.search(r'"caption"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    meta = re.search(r'"meta"\s*:\s*\[([^\]]*)\]', text)
    return {"caption": caption.group(1) if caption else "", "boxes": boxes,
            "meta": re.findall(r'"([^"]+)"', meta.group(1)) if meta else []}


def _unecho(caption: str, region) -> str:
    """Drops an echoed "woman [150, 0, 1000, 995]" lead-in; the box is already that woman."""
    text = re.sub(r"\s+", " ", re.sub(r"\[\s*\d+(?:\s*,\s*\d+){3}\s*\]", "", caption)).strip(" ,;")
    label = str(region.get("label", "")).strip()
    rest = text[len(label):].strip(" :,-") if label and text.lower().startswith(label.lower() + " ") else ""
    if rest and rest.split(" ", 1)[0].lower() not in LINKS:  # "clothing black top" -> "Black top"
        text = rest[0].upper() + rest[1:]
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
    return item


def parse_answer(task, raw_text, regions=()):
    """Model answer -> normalized layout dict. Raises ValueError when nothing usable came back."""
    try:
        data = repair_json(raw_text)
    except ValueError:
        data = _salvage(raw_text) if task == "describe_regions" else None
        if not data:
            raise
    if task == "list_objects":
        objects = data.get("objects") if isinstance(data, dict) else data
        names = [o.strip()[:40] for o in objects if isinstance(o, str) and o.strip()] if isinstance(objects, list) else []
        if not names:
            raise ValueError("The model listed no objects.")
        unique = list(dict.fromkeys(n.lower() for n in names))
        return {"objects": unique[:8]}
    if not isinstance(data, dict):
        raise ValueError("The model's answer is not a layout object.")
    out = {"caption": _sentence(data.get("caption")), "meta": [w for w in _words(data.get("meta"), 8) if w.lower() not in ECHO_META][:6]}
    if task == "describe_regions":
        captions = _captions(data, len(regions))
        if not all(captions[:len(regions)]):  # the repair may have dropped a malformed entry
            rescued = _captions(_salvage(raw_text) or {}, len(regions))
            captions = [c or (rescued[i] if i < len(rescued) else "") for i, c in enumerate(captions + [""] * (len(regions) - len(captions)))]
        captions = [_unecho(c, regions[i]) if i < len(regions) else c for i, c in enumerate(captions)]
        items = []
        for index, region in enumerate(regions):
            item = {"label": region.get("label", "object"), "caption": captions[index] if index < len(captions) else "",
                    "bbox": list(region["bbox"])}
            if region.get("text"):
                item["label"], item["text"] = "text", region["text"]
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
