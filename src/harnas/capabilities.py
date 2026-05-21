"""Provider/model content capability helpers."""

from __future__ import annotations

from typing import Any

from . import content_blocks
from .attachments import AttachmentStore


class CapabilityMismatchError(RuntimeError):
    def __init__(self, provider_kind: str, model: str, block_type: str) -> None:
        self.block_type = block_type
        super().__init__(f"{provider_kind}/{model} does not support {block_type} content blocks")


def supported(
    *,
    provider_kind: str,
    model: str,
    overrides: dict[str, bool] | None,
    block_type: str,
) -> bool:
    key = f"user_message_{block_type}s"
    if overrides is not None and key in overrides:
        return bool(overrides[key])
    images, documents = defaults(provider_kind, model.lower())
    if block_type == "image":
        return images
    if block_type == "document":
        return documents
    return True


def defaults(provider_kind: str, model: str) -> tuple[bool, bool]:
    if provider_kind in {"anthropic", "mock"}:
        if model.startswith("claude-2-"):
            return False, False
        if (
            "claude-3-5" in model
            or "claude-3-7" in model
            or "claude-sonnet-4" in model
            or "claude-opus-4" in model
        ):
            return True, True
        if model.startswith(("claude-3-", "claude-")):
            return True, False
    if provider_kind == "openai":
        if model.startswith("gpt-4o") or model in {"gpt-4-turbo", "gpt-4-vision-preview"}:
            return True, False
    if provider_kind == "gemini":
        if model.startswith("gemini-1.0-"):
            return True, False
        if model.startswith(("gemini-1.5-", "gemini-2.0-", "gemini-3.", "gemini-")):
            return True, True
    return False, False


def mismatch_behavior(value: str | None) -> str:
    return "error" if value == "error" else "metadata_fallback"


def fallback_block(block: dict[str, Any], store: AttachmentStore | None) -> dict[str, Any]:
    meta = content_blocks.resolve_data(block, store)
    return {"type": "text", "text": fallback_text(block, meta)}


def fallback_text(block: dict[str, Any], meta: dict[str, Any]) -> str:
    block_type = str(block.get("type", ""))
    segments = [
        f"[Note: A {block_type} was attached to this message but cannot be viewed by this provider."
    ]
    if block.get("name"):
        segments.append(f"Name: {block['name']}.")
    media_type = block.get("media_type") or meta.get("media_type")
    if media_type:
        segments.append(f"Type: {media_type}.")
    if int(meta.get("byte_size") or 0) > 0:
        segments.append(f"Size: {meta['byte_size']} bytes.")
    if meta.get("uri"):
        segments.append(f"URI: {meta['uri']}.")
    segments.append("Use available tools to access the content.]")
    return " ".join(segments)
