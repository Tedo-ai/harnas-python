"""Canonical provider usage metadata helpers."""

from __future__ import annotations

from typing import Any


def normalize(raw: Any) -> dict[str, Any]:
    usage = _stringify(raw) if isinstance(raw, dict) else {}
    if _is_canonical(usage):
        return {
            "input_tokens": _int(usage.get("input_tokens")),
            "output_tokens": _int(usage.get("output_tokens")),
            "total_tokens": _int(usage.get("total_tokens")),
            "cache_read_input_tokens": _optional_int(usage.get("cache_read_input_tokens")),
            "cache_write_input_tokens": _optional_int(usage.get("cache_write_input_tokens")),
            "reasoning_tokens": _optional_int(usage.get("reasoning_tokens")),
            "provider_raw": usage.get("provider_raw"),
            "provenance": str(usage.get("provenance") or ""),
        }

    input_tokens = _int(_first(usage.get("input_tokens"), usage.get("prompt_tokens"), usage.get("promptTokenCount")))
    output_tokens = _int(_first(usage.get("output_tokens"), usage.get("completion_tokens"), usage.get("candidatesTokenCount")))
    total_tokens = _int(_first(usage.get("total_tokens"), usage.get("totalTokenCount")))
    if total_tokens == 0 and (input_tokens > 0 or output_tokens > 0):
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cache_read_input_tokens": _optional_int(_first(
            _dig(usage, "prompt_tokens_details", "cached_tokens"),
            _dig(usage, "input_token_details", "cache_read"),
            usage.get("cache_read_input_tokens"),
        )),
        "cache_write_input_tokens": _optional_int(_first(
            _dig(usage, "cache_creation", "input_tokens"),
            usage.get("cache_write_input_tokens"),
        )),
        "reasoning_tokens": _optional_int(_first(
            _dig(usage, "completion_tokens_details", "reasoning_tokens"),
            usage.get("reasoning_tokens"),
        )),
        "provider_raw": usage or None,
        "provenance": "provider_reported" if usage else "unavailable",
    }


def _is_canonical(usage: dict[str, Any]) -> bool:
    required = {"input_tokens", "output_tokens", "total_tokens", "provider_raw", "provenance"}
    return bool(usage) and required.issubset(usage)


def _stringify(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stringify(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_stringify(item) for item in value]
    return value


def _first(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _dig(value: dict[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _optional_int(value: Any) -> int | None:
    return None if value is None else _int(value)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
