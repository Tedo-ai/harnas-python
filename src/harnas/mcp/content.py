"""MCP content flattening helpers."""

from __future__ import annotations

import base64
from typing import Any


def flatten(content_items: list[dict[str, Any]] | None) -> str:
    if not content_items:
        return ""
    return "\n\n".join(_flatten_item(item or {}) for item in content_items)


def _flatten_item(item: dict[str, Any]) -> str:
    kind = item.get("type")
    if kind == "text":
        return str(item.get("text") or "")
    if kind == "image":
        return f"[image: {item.get('mimeType')}, {_decoded_size(str(item.get('data') or ''))} bytes]"
    if kind in {"resource", "resource_link"}:
        uri = item.get("uri")
        if uri is None and isinstance(item.get("resource"), dict):
            uri = item["resource"].get("uri")
        return f"[resource: {uri or ''}]"
    return f"[{kind or ''}]"


def _decoded_size(data: str) -> int:
    try:
        return len(base64.b64decode(data, validate=True))
    except Exception:  # noqa: BLE001 - degraded placeholder behavior
        return len(data)

