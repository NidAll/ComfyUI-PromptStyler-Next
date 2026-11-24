"""LFM3 layout assistant helpers (pure Python): JSON repair, detector boxes, answers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("psn_layout_assist", ROOT / "comfyui" / "upscaler" / "layout_assist.py")
assist = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assist)


def test_repair_stray_bracket_and_duplicate_key():
    # real LFM3 answers from the 2026-11-24 probe: an extra "]" and a repeated "label" key
    raw = '{"items": [{"id": 1, "caption": "A hammer."}]}]'
    assert assist.repair_json(raw) == {"items": [{"id": 1, "caption": "A hammer."}]}
    raw = '```json\n{"items": [{"label": "dog", "bbox": [1, 2, 3, 4], "label": "dog"}]}\n```'
    assert assist.repair_json(raw)["items"][0]["label"] == "dog"


def test_repair_closes_a_cut_off_answer():
    raw = '{"caption": "A fox.", "items": [{"label": "fox", "caption": "Red fox", "bbox": [1, 2, 300, 400]}, {"label": "mo'
    data = assist.repair_json(raw)
    assert data["items"][0]["bbox"] == [1, 2, 300, 400]


def test_repair_rejects_prose():
    with pytest.raises(ValueError):
        assist.repair_json("I cannot see the image.")


def test_detections_normalized_capped_and_big_first():
    boxes = [{"x": 0, "y": 0, "width": 896, "height": 1000, "label": "woman"},
             {"x": 10, "y": 10, "width": 4, "height": 4, "label": "speck"}]
    boxes += [{"x": 100 + i, "y": 100, "width": 80 + i, "height": 120, "label": "jar"} for i in range(7)]
    regions = assist.normalize_detections(boxes, 896, 1152)
    assert regions[0] == {"label": "woman", "bbox": [0, 0, 1000, 868]}
    assert sum(r["label"] == "jar" for r in regions) == assist.MAX_PER_LABEL
    assert all(r["label"] != "speck" for r in regions)


def test_ocr_words_join_into_lines():
    # WeVisOne OCR on the knight render: three words of one title line
    words = [{"x": 419, "y": 55, "width": 57, "height": 28, "label": "THE"},
             {"x": 263, "y": 84, "width": 203, "height": 46, "label": "LANTERN"},
             {"x": 475, "y": 87, "width": 153, "height": 42, "label": "BEARER"}]
    lines = assist.text_lines(words, 896, 1152)
    assert [line["text"] for line in lines] == ["THE", "LANTERN BEARER"]
    assert all(line["label"] == "text" for line in lines)


def test_describe_answer_keeps_regions_and_text():
    regions = [{"label": "dog", "bbox": [342, 34, 652, 981]}, {"label": "text", "text": "NORTH", "bbox": [1, 2, 300, 90]}]
    raw = '{"caption": "A poster.", "meta": "flat design, low poly", "captions": ["An orange dog.", "White serif letters."]}'
    out = assist.parse_answer("describe_regions", raw, regions)
    assert out["meta"] == ["flat design", "low poly"]
    assert out["items"][1] == {"label": "text", "caption": "White serif letters.", "bbox": [1, 2, 300, 90], "text": "NORTH"}
    assert out["described"] == 2


def test_echoed_label_is_not_lettering():
    # LFM3 wrote "text": "Red fox" on the fox item; MOSS would draw those words
    item = assist.clean_item({"label": "red fox", "caption": "A red fox sits.", "text": "Red fox", "bbox": [100, 650, 300, 900]})
    assert item == {"label": "red fox", "caption": "A red fox sits.", "bbox": [100, 650, 300, 900]}
    title = assist.clean_item({"label": "title text", "text": "NORTHERN LIGHTS", "caption": "Title.", "bbox": [300, 50, 700, 120]})
    assert title["label"] == "text" and title["text"] == "NORTHERN LIGHTS"


def test_boxes_are_clamped_and_ordered():
    assert assist.clean_box([900, 1200, 100, -5]) == [100, 0, 900, 1000]
    assert assist.clean_box([1, 2, 3]) is None


def test_list_objects_dedupes():
    out = assist.parse_answer("list_objects", '{"objects": ["Dog", "dog", "cat"]}')
    assert out == {"objects": ["dog", "cat"]}


@pytest.mark.parametrize("task", assist.TASKS)
def test_every_task_has_a_prompt(task):
    regions = [{"label": "dog", "bbox": [1, 2, 300, 400]}]
    chat, budget = assist.messages(task, request="a fox", regions=regions, layout={"items": []}, has_image=True)
    assert chat[0]["role"] == "system" and 60 < budget <= 1400
    assert "0-1000" in chat[1]["content"][-1]["text"] or task == "list_objects"


def test_backdrops_and_parts_of_boxed_people_are_dropped():
    # Knight render detections: the full-frame forest and the armour/belt inside the man go; the lantern stays.
    px = lambda b, label: {"x": b[0] * 0.896, "y": b[1] * 1.152, "width": (b[2] - b[0]) * 0.896, "height": (b[3] - b[1]) * 1.152, "label": label}
    boxes = [px([1, 0, 999, 995], "forest"), px([269, 148, 686, 964], "man"), px([268, 267, 679, 643], "armor"),
             px([393, 442, 628, 580], "belt"), px([287, 413, 395, 639], "lantern")]
    assert [r["label"] for r in assist.normalize_detections(boxes, 896, 1152)] == ["man", "lantern"]
    assert [r["label"] for r in assist.normalize_detections(boxes[:1], 896, 1152)] == ["forest"]


def test_numbered_captions_land_on_their_boxes():
    regions = [{"label": "hammer", "bbox": [22, 36, 319, 980]}, {"label": "dog", "bbox": [342, 34, 652, 981]},
               {"label": "woman", "bbox": [150, 0, 1000, 995]}]
    chat, budget = assist.messages("describe_regions", regions=regions, has_image=True)
    assert '"1 hammer": "..."' in chat[1]["content"][1]["text"] and budget == 110 + 48 * 3
    raw = ('{"caption": "Three things.", "meta": ["medium", "flat vector", "mood"], "boxes": {"2 dog": "An orange dog.", '
           '"1 hammer": "A blue hammer.", "3 woman": "woman [150, 0, 1000, 995] in a supermarket"}}')
    out = assist.parse_answer("describe_regions", raw, regions)
    assert [i["caption"] for i in out["items"]] == ["A blue hammer.", "An orange dog.", "woman in a supermarket"]
    assert out["meta"] == ["flat vector"]
    assert assist._unecho("clothing black top and skirt", {"label": "clothing"}) == "Black top and skirt"


def test_describe_answer_with_a_bare_quote_still_gives_captions():
    regions = [{"label": "hammer", "bbox": [22, 36, 319, 980]}, {"label": "text", "text": "BLUE", "bbox": [138, 462, 214, 585]}]
    raw = '{"caption": "Flat shapes.", "meta": ["flat vector"], "boxes": {"1 hammer": "A blue hammer.", "2 text "BLUE"": "White letters."}}'
    out = assist.parse_answer("describe_regions", raw, regions)
    assert [i["caption"] for i in out["items"]] == ["A blue hammer.", "White letters."]
    assert out["caption"] == "Flat shapes." and out["meta"] == ["flat vector"]


def test_style_tags_never_repeat_the_subjects():
    raw = ('{"caption": "A travel poster.", "meta": ["retro travel poster", "Kyoto", "pagoda", "hikers", "retro"], "items": ['
           '{"label": "text", "text": "KYOTO", "caption": "huge title", "bbox": [250, 50, 750, 200]},'
           '{"label": "pagoda", "caption": "red pagoda", "bbox": [300, 300, 700, 800]},'
           '{"label": "hiker", "caption": "two hikers", "bbox": [600, 650, 900, 950]}]}')
    assert assist.parse_answer("text_layout", raw)["meta"] == ["retro travel poster", "retro"]


def test_existing_captions_tell_the_model_what_a_box_holds():
    regions = [{"label": "object", "hint": "A hiker in the lower right", "bbox": [430, 590, 640, 900]}]
    chat, _ = assist.messages("describe_regions", regions=regions, request="A travel poster.")
    assert '1. object (now: A hiker in the lower right) [430, 590, 640, 900]' in chat[1]["content"][0]["text"]


def test_a_lettering_detection_gives_way_to_the_ocr_lines():
    detections = [{"label": "man", "bbox": [268, 148, 687, 964]}, {"label": "golden title text", "bbox": [280, 40, 710, 120]}]
    lines = [{"label": "text", "text": "THE", "bbox": [468, 48, 532, 72]}, {"label": "text", "text": "LANTERN BEARER", "bbox": [294, 73, 701, 113]}]
    assert [r.get("text") or r["label"] for r in assist.merge_regions(detections, lines)] == ["man", "THE", "LANTERN BEARER"]
    assert len(assist.merge_regions(detections, [])) == 2
