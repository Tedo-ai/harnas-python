"""Helpers for turning CLI input files into content blocks."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any


def content_blocks(text: str, paths: list[str]) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text}, *[content_block(path) for path in paths]]


def content_block(path: str) -> dict[str, Any]:
    media_type, block_type = _media_type_for(path)
    data = Path(path).read_bytes()
    return {
        "type": block_type,
        "media_type": media_type,
        "name": Path(path).name,
        "source": {
            "kind": "base64",
            "data": base64.b64encode(data).decode("ascii"),
        },
    }


def _media_type_for(path: str) -> tuple[str, str]:
    match Path(path).suffix.lower():
        case ".jpg" | ".jpeg":
            return "image/jpeg", "image"
        case ".png":
            return "image/png", "image"
        case ".gif":
            return "image/gif", "image"
        case ".webp":
            return "image/webp", "image"
        case ".pdf":
            return "application/pdf", "document"
        case _:
            raise ValueError(f"unsupported input file type: {path}")
