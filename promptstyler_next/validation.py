"""Bounded JSON and explicit schema primitives. Packs are data, never programs."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import StylerError

AXES = ("medium", "lighting", "palette", "composition", "texture", "mood", "detail")
IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
SEMVER = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?\Z")
MAX_PACK_BYTES = 4 * 1024 * 1024


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StylerError("duplicate_key", "Duplicate JSON object key.", key)
        result[key] = value
    return result


def _constant(value: str) -> object:
    raise StylerError("invalid_json", "Non-finite JSON number is not allowed.")


def parse_json(text: str | bytes, *, max_bytes: int = 65536) -> object:
    try:
        raw = text.encode("utf-8") if isinstance(text, str) else text
        if len(raw) > max_bytes:
            raise StylerError("input_too_large", f"Input exceeds {max_bytes} bytes.")
        value: object = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except StylerError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StylerError("invalid_json", "Expected bounded, valid UTF-8 JSON.") from exc
    _depth(value)
    return value


def _depth(value: object, level: int = 0) -> None:
    if level > 24:
        raise StylerError("input_too_deep", "JSON nesting exceeds 24 levels.")
    if isinstance(value, dict):
        for key, item in value.items():
            string(key, "key", maximum=256)
            _depth(item, level + 1)
    elif isinstance(value, list):
        for item in value:
            _depth(item, level + 1)
    elif isinstance(value, str):
        string(value, "value", maximum=MAX_PACK_BYTES, empty=True)
    elif isinstance(value, float) and not math.isfinite(value):
        raise StylerError("invalid_json", "Non-finite JSON number is not allowed.")


def read_json(path: Path, *, max_bytes: int = MAX_PACK_BYTES) -> object:
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
    except OSError as exc:
        raise StylerError("pack_io", "Cannot read style pack.", path.name) from exc
    return parse_json(raw, max_bytes=max_bytes)


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def obj(
    value: object, path: str, *, required: tuple[str, ...] = (), optional: tuple[str, ...] = ()
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise StylerError("invalid_type", "Expected an object.", path)
    data = dict(value)
    unknown = data.keys() - set(required) - set(optional)
    missing = set(required) - data.keys()
    if unknown:
        raise StylerError("unknown_field", "Unknown field.", f"{path}.{sorted(unknown)[0]}")
    if missing:
        raise StylerError("missing_field", "Required field is missing.", f"{path}.{sorted(missing)[0]}")
    return data


def string(value: object, path: str, *, maximum: int = 512, empty: bool = False) -> str:
    if not isinstance(value, str):
        raise StylerError("invalid_type", "Expected a string.", path)
    if len(value) > maximum or (not empty and not value.strip()):
        raise StylerError("invalid_string", f"Expected {'0' if empty else '1'}–{maximum} characters.", path)
    if any(ord(char) < 32 and char not in "\n\r\t" or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise StylerError(
            "invalid_string", "Control characters and unpaired surrogates are not allowed.", path
        )
    return value


def identifier(value: object, path: str) -> str:
    text = string(value, path, maximum=96)
    if not IDENTIFIER.fullmatch(text):
        raise StylerError(
            "invalid_identifier", "Use a lowercase dotted, dashed or underscored identifier.", path
        )
    return text


def array(value: object, path: str, *, maximum: int = 64) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        raise StylerError("invalid_type", "Expected an array.", path)
    if len(value) > maximum:
        raise StylerError("too_many_items", f"Maximum {maximum} items.", path)
    return list(value)


def strings(value: object, path: str, *, maximum: int = 32, length: int = 96) -> tuple[str, ...]:
    items = tuple(
        string(item, f"{path}[{i}]", maximum=length)
        for i, item in enumerate(array(value, path, maximum=maximum))
    )
    if len(set(items)) != len(items):
        raise StylerError("duplicate_item", "Duplicate entries are not allowed.", path)
    return items


def choice(value: object, options: tuple[str, ...], path: str) -> str:
    text = string(value, path, maximum=96)
    if text not in options:
        raise StylerError("invalid_choice", f"Choose from: {', '.join(options)}.", path)
    return text


def unit_float(value: object, path: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 1
        or not math.isfinite(value)
    ):
        raise StylerError("invalid_intensity", "Expected a finite number between 0 and 1.", path)
    return float(value)


def integer(value: object, path: str, *, minimum: int = 0, maximum: int = 1000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise StylerError("invalid_integer", f"Expected an integer between {minimum} and {maximum}.", path)
    return value


def version(value: object, path: str) -> str:
    text = string(value, path, maximum=64)
    if not SEMVER.fullmatch(text):
        raise StylerError("invalid_version", "Expected a semantic version.", path)
    return text


def schema_version(value: object, path: str) -> None:
    if type(value) is not int or value != 1:
        raise StylerError("unsupported_schema", "Only schema_version 1 is supported.", path)
