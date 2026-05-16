"""Helpers for snapshotting dynamic tool registries."""

from __future__ import annotations

import json
from typing import Any


def descriptors(registry: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "handler": getattr(tool, "handler_name", None) or tool.name,
            "description": tool.description,
            "input_schema": _copy(tool.input_schema),
            "config": _copy(tool.config or {}),
        }
        for tool in registry.tools
    ]


def manifest_metadata(
    *,
    registry: Any,
    skills: Any | None = None,
    mcp: Any | None = None,
) -> dict[str, Any]:
    metadata = {"tools": descriptors(registry)}
    if skills is not None:
        metadata["skills"] = _copy(skills)
    if mcp is not None:
        metadata["mcp"] = _copy(mcp)
    return metadata


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))
