from __future__ import annotations

import copy
import json

import pytest
from conftest import make_pack, make_style

from promptstyler_next import StylerError
from promptstyler_next.catalog import Catalog, Pack
from promptstyler_next.validation import parse_json


@pytest.mark.parametrize(
    "raw",
    [
        '{"a":1,"a":2}',
        '{"a":NaN}',
        '{"a":Infinity}',
        '{"x":1e9999}',
        '{"x":"\\ud800"}',
        '"\\u0000"',
        b"\xff",
        "{",
        "[" * 30 + "0" + "]" * 30,
    ],
)
def test_untrusted_json_is_strict(raw):
    with pytest.raises(StylerError):
        parse_json(raw)


def test_json_size_limit_and_safe_literals():
    with pytest.raises(StylerError) as failure:
        parse_json('"abcd"', max_bytes=3)
    assert failure.value.code == "input_too_large"
    assert parse_json('{"text":"${HOME} {prompt} __import__(os)"}') == {
        "text": "${HOME} {prompt} __import__(os)"
    }


def test_pack_load_roundtrip_and_snapshot(tmp_path):
    data = make_pack()
    path = tmp_path / "pack.json"
    path.write_text(json.dumps(data))
    pack = Pack.load(path)
    assert Pack.from_dict(pack.to_dict()) == pack
    catalog = Catalog([pack])
    original = catalog.fingerprint
    data["styles"][0]["clauses"][0]["text"] = "Different ink"
    path.write_text(json.dumps(data))
    assert Catalog([Pack.load(path)]).fingerprint != original
    assert catalog.get("test.ink").clauses[0].text == "Use carved ink contours"


@pytest.mark.parametrize(
    "key,value",
    [
        ("id", "../escape"),
        ("name", " "),
        ("schema_version", 2),
        ("version", "latest"),
        ("styles", []),
        ("author", 1),
    ],
)
def test_invalid_pack_fields(key, value):
    with pytest.raises(StylerError):
        Pack.from_dict(make_pack(**{key: value}))


@pytest.mark.parametrize(
    "changes",
    [
        {"extra": "unknown"},
        {"category": "../outside"},
        {"kind": "macro"},
        {"claims": {"subject": "cat"}},
        {"claims": []},
        {"variants": []},
        {"clauses": []},
        {"clauses": [{"axis": "medium", "text": "ink", "tags": "string"}]},
        {"tags": ["ink", "ink"]},
        {"preview": {"path": "../secret.png", "alt": "invalid", "kind": "reference"}},
        {"preview": {"path": "https://evil.test/x.png", "alt": "invalid", "kind": "reference"}},
        {"preview": {"path": "x.svg", "alt": "invalid", "kind": "reference"}},
    ],
)
def test_invalid_style_fields(changes):
    with pytest.raises(StylerError):
        Pack.from_dict(make_pack([make_style(**changes)]))


def test_duplicate_ids_and_packs_cannot_override():
    pack = Pack.from_dict(make_pack())
    with pytest.raises(StylerError, match="Pack IDs"):
        Catalog([pack, pack])
    duplicate = Pack.from_dict(make_pack(id="second.pack"))
    with pytest.raises(StylerError, match="Style IDs"):
        Catalog([pack, duplicate])


def test_pack_does_not_execute_templates(tmp_path):
    target = tmp_path / "should-not-exist"
    data = make_pack()
    payload = f"{{__import__('pathlib').Path('{target}').touch()}}"
    data["styles"][0]["clauses"][0]["text"] = payload
    pack = Pack.from_dict(copy.deepcopy(data))
    assert pack.styles[0].clauses[0].text == payload
    assert not target.exists()


def test_io_errors_are_typed_and_do_not_include_prompt(tmp_path):
    with pytest.raises(StylerError) as failure:
        Pack.load(tmp_path / "missing.json")
    assert failure.value.code == "pack_io"
