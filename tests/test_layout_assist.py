"""LFM3 layout assistant helpers (pure Python): JSON repair, detector boxes, answers."""

from __future__ import annotations

import importlib.util
import json
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


def px(box, label, width=896, height=1152):
    """A 0-1000 xyxy box as a detector box in pixels."""
    x1, y1, x2, y2 = box
    return {"x": x1 * width / 1000, "y": y1 * height / 1000, "width": (x2 - x1) * width / 1000,
            "height": (y2 - y1) * height / 1000, "label": label}


def test_detections_normalized_capped_and_big_first():
    boxes = [{"x": 0, "y": 0, "width": 896, "height": 1000, "label": "woman"},
             {"x": 10, "y": 10, "width": 4, "height": 4, "label": "speck"}]
    boxes += [{"x": 100 * i, "y": 100, "width": 80 + i, "height": 120, "label": "jar"} for i in range(7)]
    regions = assist.normalize_detections(boxes, 896, 1152)
    assert regions[0] == {"label": "woman", "bbox": [0, 0, 1000, 868]}
    assert sum(r["label"] == "jar" and "count" not in r for r in regions) == assist.MAX_PER_LABEL
    assert all(r["label"] != "speck" for r in regions)


def test_setting_and_patterns_become_background():
    # Black-cat render: 7 candles and 9 roses all over the frame, the cat in the middle.
    boxes = [px([316, 191, 777, 774], "black cat")]
    boxes += [px([x, y, x + 70, y + 70], "candle") for x, y in ((50, 600), (700, 820), (850, 300), (100, 900), (400, 880),
                                                                  (600, 60), (200, 120))]
    boxes += [px([x, y, x + 90, y + 70], "rose") for x, y in ((0, 430), (0, 760), (150, 850), (840, 700), (880, 420))]
    regions, background = assist.select_regions(boxes, 896, 1152)
    assert [r["label"] for r in regions] == ["black cat"]
    assert background == ["candle", "rose"]
    # Shop render: shelves are the setting; the jars in the cart are its contents; the held jar stays.
    shop = [px([150, 0, 1000, 995], "woman"), px([0, 676, 455, 999], "shopping cart"), px([134, 512, 321, 674], "jar"),
            px([58, 868, 149, 960], "jar"), px([155, 860, 282, 943], "jar"), px([231, 803, 317, 890], "jar"),
            px([0, 456, 124, 496], "shelf"), px([0, 633, 172, 683], "shelf")]
    regions, background = assist.select_regions(shop, 896, 1152)
    assert [r["label"] for r in regions] == ["woman", "shopping cart", "jar"]
    assert "shelf" in background and "jar" not in background


def test_a_big_box_touching_two_edges_is_setting_unless_it_is_the_subject():
    boxes = [px([28, 628, 262, 912], "person"), px([306, 183, 502, 407], "person"), px([2, 233, 999, 884], "train")]
    regions, background = assist.select_regions(boxes, 896, 1152)
    assert [r["label"] for r in regions] == ["person", "person"] and background == ["train"]
    assert [r["label"] for r in assist.select_regions(boxes[2:], 896, 1152)[0]] == ["train"]


def test_minor_repeats_group_or_go():
    # the hero and a crowd of small figures under him: the crowd is one group box
    boxes = [px([207, 335, 823, 734], "man")] + [px([480 + 50 * i, 860, 530 + 50 * i, 950], "man") for i in range(5)]
    regions, _ = assist.select_regions(boxes, 896, 1152)
    assert [(r["label"], r.get("count")) for r in regions] == [("man", None), ("man", 5)]
    assert regions[1]["bbox"] == [480, 860, 730, 950]


def test_same_thing_under_two_names_is_boxed_once():
    boxes = [px([305, 585, 699, 909], "flower vase"), px([305, 585, 698, 909], "vase"), px([660, 690, 939, 920], "mug")]
    assert [r["label"] for r in assist.normalize_detections(boxes, 896, 1152)] == ["flower vase", "mug"]


def test_lettering_blocks_join_and_cap():
    boxes = [px([268, 148, 687, 964], "knight"), px([58, 24, 949, 253], "title"), px([61, 153, 949, 255], "text"),
             px([101, 635, 932, 668], "text"), px([300, 700, 330, 720], "text")]
    regions = assist.normalize_detections(boxes, 896, 1152)
    text = [r for r in regions if r.get("read")]
    assert [r["bbox"] for r in text] == [[58, 24, 949, 253], [101, 635, 932, 668]]
    assert all(r["label"] == "text" for r in text) and regions[0]["label"] == "knight"


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
    out = assist.parse_answer("list_objects", '{"objects": ["Dog", "dog", "dogs", "cat"]}')
    assert out == {"objects": ["dog", "cat"], "background": [], "lettering": True}


def test_list_objects_puts_the_subject_first_and_caps_labels():
    raw = ('{"subject": "Goblin", "objects": ["mushroom", "tree", "moon", "fox", "rock", "goblin", "grass", "leaf"], '
           '"background": ["misty forest"], "lettering": false}')
    out = assist.parse_answer("list_objects", raw)
    assert out["objects"][0] == "goblin" and out["objects"].count("goblin") == 1
    assert out["objects"] == ["goblin", "mushroom", "tree", "moon", "fox"]
    assert out["lettering"] is False


def test_list_objects_leaves_setting_parts_and_patterns_to_the_background():
    raw = ('{"subject": "black cat", "objects": ["candle", "rose", "armor", "forest", "flower vase", "vase"], '
           '"background": ["red roses", "dark background"], "lettering": false}')
    out = assist.parse_answer("list_objects", raw)
    assert out["objects"] == ["black cat", "candle", "flower vase"]
    assert out["background"] == ["red roses", "dark background", "forest"]
    # the subject itself may be scenery
    assert assist.parse_answer("list_objects", '{"subject": "cathedral", "objects": ["fog", "moon"]}')["objects"] == ["cathedral", "moon"]


@pytest.mark.parametrize("value, expected", [("true", True), ('"false"', False), ("null", True), ("1", True)])
def test_only_an_explicit_no_skips_lettering(value, expected):
    out = assist.parse_answer("list_objects", f'{{"subject": "poster", "objects": [], "lettering": {value}}}')
    assert out["lettering"] is expected


@pytest.mark.parametrize("task", assist.TASKS)
def test_every_task_has_a_prompt(task):
    regions = [{"label": "dog", "bbox": [1, 2, 300, 400]}]
    chat, budget = assist.messages(task, request="a fox", regions=regions, layout={"items": []}, has_image=True)
    assert chat[0]["role"] == "system" and 60 < budget <= 1400
    assert "0-1000" in chat[1]["content"][-1]["text"] or task in ("list_objects", "edit_layout")


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
    assert '"1 hammer": "..."' in chat[1]["content"][1]["text"] and budget == 150 + 48 * 3
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


def test_detected_lettering_is_read_and_the_background_joins_the_caption():
    regions = [{"label": "knight", "bbox": [268, 148, 687, 964]}, {"label": "text", "bbox": [296, 60, 702, 114], "read": True},
               {"label": "text", "bbox": [300, 900, 700, 950], "read": True}]
    chat, budget = assist.messages("describe_regions", regions=regions, has_image=True, background=["misty forest"])
    prompt = chat[1]["content"][1]["text"]
    assert "No box (background): misty forest" in prompt and '"words": {"2": "...", "3": "..."}' in prompt
    assert budget == 150 + 48 * 3 + 24 * 2
    raw = ('{"caption": "A knight holds a lantern.", "background": "Misty pines fade into fog.", "meta": ["cinematic"], '
           '"boxes": {"1 knight": "Silver armour.", "2 text": "The title \'THE LANTERN BEARER\' in gold serif capitals.", '
           '"3 text": "Small white caps."}, "words": {"2": "THE LANTERN BEARER", "3": "unreadable"}}')
    out = assist.parse_answer("describe_regions", raw, regions)
    assert out["caption"] == "A knight holds a lantern. Misty pines fade into fog."
    assert [i.get("text") for i in out["items"]] == [None, "THE LANTERN BEARER"]  # an unread block is dropped
    assert out["items"][1]["caption"] == "The title in gold serif capitals."


BOOKSHOP = {"width": 896, "height": 1152, "meta": ["cozy"], "caption": (
    "A cozy bookshop poster at night with a large 'OPEN LATE' title at the top, a sleeping cat on stacked books in "
    "the lower left, and a woman reading by a window on the right."), "items": [
    {"label": "text", "text": "OPEN LATE", "caption": "Bold white letters spelling 'OPEN LATE' across the top of the poster.",
     "bbox": [250, 100, 750, 200]},
    {"label": "sleeping cat", "caption": "A fluffy cat curled on colorful books in the lower left corner.", "bbox": [100, 600, 350, 900]},
    {"label": "woman reading", "caption": "A woman with long hair reading by a bright window on the right side.",
     "bbox": [600, 500, 900, 900]}]}


def edit(request, raw):
    return assist.parse_answer("edit_layout", raw, layout=BOOKSHOP, request=request)


def test_edit_prompt_shows_places_in_words_not_coordinates():
    chat, budget = assist.messages("edit_layout", request="Move the title to the bottom", layout=BOOKSHOP, width=896, height=1152)
    prompt = chat[1]["content"][0]["text"]
    assert '1. text "OPEN LATE" (top, wide): Bold white letters' in prompt
    assert "2. sleeping cat (bottom left)" in prompt and "[250, 100" not in prompt
    assert budget == 200 + 50 * 3


# The answers below are LFM3's own (live runs on the bookshop layout), restated places and stray brackets included.
def test_edit_moves_by_place_and_adds_a_sized_box():
    out = edit("Move the title to the bottom and add a small lamp on the right.",
               '{"changes": [{"item": 1, "place": "bottom", "size": "large"}, {"item": 2, "place": "bottom left"}, '
               '{"item": 3, "place": "bottom right"}, {"item": 4, "add": "small lamp", "place": "right", "caption": '
               '"A small lamp sits on the windowsill to the right of the woman reading.", "text": "small lamp"}]}')
    title, cat, woman, lamp = out["items"]
    assert title["bbox"] == [250, 860, 750, 960] and title["caption"] == "Bold white letters."  # no "large": not asked
    assert cat["bbox"] == [100, 600, 350, 900] and woman["bbox"] == [600, 500, 900, 900]  # restated places stay put
    assert lamp["label"] == "small lamp" and "text" not in lamp and lamp["bbox"][2] == 1000 - assist.MARGIN
    assert (lamp["bbox"][2] - lamp["bbox"][0]) * (lamp["bbox"][3] - lamp["bbox"][1]) < 0.07e6
    assert "title at the bottom" in out["caption"]


def test_edit_removes_and_repairs_a_summary_that_logs_the_change():
    out = edit("Remove the cat.", '{"changes": [{"item": 2, "remove": true}, {"item": 3, "caption": "woman reading by a '
               'window on the right"}], "summary": "A cozy bookshop poster at night with a sleeping cat removed, a '
               'woman reading by a window on the right."}')
    assert [i["label"] for i in out["items"]] == ["text", "woman reading"]
    assert out["items"][1]["caption"] == BOOKSHOP["items"][2]["caption"]  # the woman was not named
    assert out["caption"] == ("A cozy bookshop poster at night with a large 'OPEN LATE' title at the top, and a woman "
                              "reading by a window on the right.")


def test_edit_changes_words_and_looks_of_named_items_only():
    out = edit("Change the title to CLOSED and make the woman wear a red coat.",
               '{"changes": [{"item": 1, "text": "CLOSED"}, {"item": 3, "caption": "A woman with long hair wearing a '
               'red coat reading by a bright window"}, {"item": 3, "text": "A woman in red"}, {"item": 2, "size": '
               '"smaller"}]}, "summary": "No summary needed."}')
    title, cat, woman = out["items"]
    assert title["text"] == "CLOSED" and "OPEN LATE" not in title["caption"]
    assert cat["bbox"] == BOOKSHOP["items"][1]["bbox"] and cat["caption"] == BOOKSHOP["items"][1]["caption"]
    assert "red coat" in woman["caption"] and "text" not in woman
    assert "'CLOSED' title" in out["caption"]
    detail = edit("Make the woman wear a red coat.", '{"changes": [{"item": 3, "caption": "wearing a red coat"}]}')
    assert detail["items"][2]["caption"].endswith("on the right side, wearing a red coat.")
    note = edit("Make the woman wear a red coat.", '{"changes": [{"item": 3, "caption": "moved to the left side"}]}')
    assert note["items"][2]["caption"] == BOOKSHOP["items"][2]["caption"]


def test_edit_moves_two_items_and_the_summary_follows():
    out = edit("Move the woman to the left and the cat to the right.",
               '{"changes": [{"item": 3, "place": "left"}, {"item": 2, "place": "right"}]}')
    assert [i["bbox"] for i in out["items"][1:]] == [[710, 600, 960, 900], [40, 500, 340, 900]]
    assert out["items"][1]["caption"] == "A fluffy cat curled on colorful books."  # the old place words go
    assert "stacked books at the bottom right" in out["caption"] and "window at the bottom left" in out["caption"]


def test_edit_scene_change_without_a_summary_adds_the_scene():
    out = edit("Make it a rainy night scene.", '{"changes": [{"item": "1", "place": "top", "text": "OPEN LATE"}]}')
    assert out["caption"].endswith("on the right. A rainy night scene.")
    assert [(i["bbox"], i.get("text")) for i in out["items"]] == [(i["bbox"], i.get("text")) for i in BOOKSHOP["items"]]


def test_edit_salvage_and_whole_layouts():
    broken = '{"changes": [{"item": 2, "remove": true}, {"add": "lamp", "caption": "A brass lamp.", "place": "top right"}'
    out = edit("Remove the cat and add a lamp", broken)
    assert [i["label"] for i in out["items"]] == ["text", "woman reading", "lamp"]
    assert out["items"][2]["bbox"][1] == assist.MARGIN
    whole = '{"caption": "A poster.", "items": [{"label": "cat", "caption": "A cat.", "bbox": [1, 2, 300, 400]}]}'
    assert edit("anything", whole)["items"][0]["label"] == "cat"


def test_unbalanced_brackets_are_repaired():
    assert assist.repair_json('{"a": [1, 2]], "b": "x]"}') == {"a": [1, 2], "b": "x]"}


def test_prepare_and_finish_run_a_task_without_the_model():
    scene = '{"objects": ["black cat"], "background": ["red roses"], "lettering": false}'
    boxes = [px([316, 191, 777, 774], "black cat"), px([0, 0, 1000, 1000], "wall")]
    job = assist.prepare("describe_regions", objects=[boxes], image_size=(896, 1152), scene=scene)
    assert [r["label"] for r in job["regions"]] == ["black cat"] and job["use_image"]
    assert job["background"] == ["wall", "red roses"]
    assert "No box (background): wall, red roses" in job["messages"][1]["content"][1]["text"]
    out, labels = assist.finish(job, '{"caption": "A cat.", "background": "A wall of roses.", "boxes": {"1 black cat": "Sleek."}}')
    assert out["caption"] == "A cat. A wall of roses." and out["grid"] == "xyxy-1000" and labels == ""
    # nothing found: the model places the boxes itself
    assert assist.prepare("describe_regions", objects=[], image_size=(896, 1152))["task"] == "image_layout"
    with pytest.raises(ValueError, match="needs an image"):
        assist.prepare("list_objects")
    with pytest.raises(ValueError, match="at least one box"):
        assist.prepare("describe_regions", layout={"items": []})


def test_finish_turns_a_list_into_detector_labels():
    job = assist.prepare("list_objects", image_size=(896, 1152))
    out, labels = assist.finish(job, '{"subject": "knight", "objects": ["lantern"], "lettering": true}')
    assert labels == "knight\nlantern\ntitle\ntext" and out["objects"] == ["knight", "lantern"]
    out, labels = assist.finish(job, "no idea")
    assert labels == "main subject\ntitle\ntext" and out["warnings"]
    edit = assist.prepare("edit_layout", request="Remove the cat.", layout=json.dumps(BOOKSHOP))
    out, _ = assist.finish(edit, '{"changes": [{"item": 2, "remove": true}]}')
    assert [i["label"] for i in out["items"]] == ["text", "woman reading"]


def test_describe_captions_drop_where_in_the_frame():
    regions = [{"label": "mushroom", "bbox": [56, 522, 182, 736]}, {"label": "text", "bbox": [297, 49, 702, 114], "read": True}]
    raw = ('{"caption": "A forest.", "boxes": {"1 mushroom": "A mushroom with a pink striped cap on the left.", '
           '"2 text": "Golden serif lettering at the top center."}, "words": {"2": "THE LANTERN BEARER"}}')
    out = assist.parse_answer("describe_regions", raw, regions)
    assert [i["caption"] for i in out["items"]] == ["A mushroom with a pink striped cap.", "Golden serif lettering."]
    # a place that is part of the thing stays ("to the left of the woman")
    assert assist._unplaced("A lamp to the right of the woman.") == "A lamp to the right of the woman."
    assert assist._unplaced("A green cat on a red chair on the right, looking to the left.") == (
        "A green cat on a red chair, looking to the left.")  # live answer: the gaze stays
