"""harnas-jcs-v1 canonical JSON and Event row content hashes."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


class InvalidUnicodeError(ValueError):
    """Raised when canonicalization sees invalid Unicode."""


def canonicalize_json(source: str | bytes, *, exclude_keys: list[str] | None = None) -> str:
    text = source.decode("utf-8") if isinstance(source, bytes) else source
    _validate_surrogate_escapes(text)
    value = json.loads(text)
    if isinstance(value, dict):
        for key in exclude_keys or []:
            value.pop(key, None)
    return canonicalize(value)


def content_hash_json(source: str | bytes) -> str:
    return hashlib.sha256(canonicalize_json(source, exclude_keys=["content_hash"]).encode("utf-8")).hexdigest()


def canonicalize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return _es6_number(value)
    if isinstance(value, list):
        return "[" + ",".join(canonicalize(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value.keys(), key=_utf16_units)
        return "{" + ",".join(f"{_string(str(key))}:{canonicalize(value[key])}" for key in keys) + "}"
    raise TypeError(f"unsupported canonical JSON value {type(value)!r}")


def _string(value: str) -> str:
    out = ['"']
    for char in value:
        codepoint = ord(char)
        if char == '"':
            out.append('\\"')
        elif char == "\\":
            out.append("\\\\")
        elif char == "\b":
            out.append("\\b")
        elif char == "\t":
            out.append("\\t")
        elif char == "\n":
            out.append("\\n")
        elif char == "\f":
            out.append("\\f")
        elif char == "\r":
            out.append("\\r")
        elif codepoint < 0x20:
            out.append(f"\\u{codepoint:04x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _es6_number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("invalid number")
    if value == 0:
        return "0"
    raw = repr(value).replace("E", "e")
    if "e" not in raw:
        return raw[:-2] if raw.endswith(".0") else raw
    mantissa, exponent_text = raw.split("e", 1)
    exponent = int(exponent_text)
    absolute = abs(value)
    if absolute >= 1e-6 and absolute < 1e21:
        return _exponent_to_decimal(mantissa, exponent)
    return _normalize_exponent(mantissa, exponent)


def _exponent_to_decimal(mantissa: str, exponent: int) -> str:
    negative = mantissa.startswith("-")
    mantissa = mantissa.removeprefix("-")
    digits = mantissa.replace(".", "")
    decimal_places = len(mantissa) - mantissa.index(".") - 1 if "." in mantissa else 0
    point = len(digits) - decimal_places + exponent
    if point <= 0:
        out = "0." + ("0" * -point) + digits
    elif point >= len(digits):
        out = digits + ("0" * (point - len(digits)))
    else:
        out = digits[:point] + "." + digits[point:]
    out = out.rstrip("0").rstrip(".")
    return f"-{out}" if negative else out


def _normalize_exponent(mantissa: str, exponent: int) -> str:
    mantissa = mantissa.removesuffix(".0")
    sign = "+" if exponent >= 0 else ""
    return f"{mantissa}e{sign}{exponent}"


def _utf16_units(value: str) -> list[int]:
    encoded = value.encode("utf-16-be")
    return [(encoded[i] << 8) + encoded[i + 1] for i in range(0, len(encoded), 2)]


def _validate_surrogate_escapes(text: str) -> None:
    in_string = False
    i = 0
    while i < len(text):
        char = text[i]
        if not in_string:
            in_string = char == '"'
            i += 1
            continue
        if char == '"':
            in_string = False
            i += 1
            continue
        if char != "\\":
            i += 1
            continue
        i += 1
        if i >= len(text) or text[i] != "u":
            i += 1
            continue
        code = int(text[i + 1 : i + 5], 16)
        if 0xD800 <= code <= 0xDBFF:
            if text[i + 5 : i + 7] != "\\u":
                raise InvalidUnicodeError("invalid_unicode")
            low = int(text[i + 7 : i + 11], 16)
            if not 0xDC00 <= low <= 0xDFFF:
                raise InvalidUnicodeError("invalid_unicode")
            i += 11
            continue
        if 0xDC00 <= code <= 0xDFFF:
            raise InvalidUnicodeError("invalid_unicode")
        i += 5
