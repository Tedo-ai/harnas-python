"""UI-neutral projection from a Harnas Log to transcript items."""

from __future__ import annotations

import base64
from typing import Any


def project(
    log: Any,
    *,
    include_tools: bool = True,
    include_errors: bool = True,
    include_annotations: bool = False,
    content_placeholder: Any | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for event in log:
        payload = event.payload
        if event.type == "user_message":
            items.append(_item(
                event,
                kind="user",
                role="user",
                text=_message_text(payload, content_placeholder),
            ))
        elif event.type == "assistant_message":
            items.append(_item(
                event,
                kind="assistant",
                role="assistant",
                text=_message_text(payload, content_placeholder),
                stop_reason=payload.get("stop_reason"),
                usage=payload.get("usage", {}),
                reasoning=payload.get("reasoning"),
            ))
        elif event.type == "tool_use" and include_tools:
            items.append(_item(
                event,
                kind="tool_use",
                name=payload.get("name"),
                tool_use_id=payload.get("id"),
                arguments=payload.get("arguments", {}),
            ))
        elif event.type == "tool_result" and include_tools:
            items.append(_item(
                event,
                kind="tool_result",
                tool_use_id=payload.get("tool_use_id"),
                output=payload.get("output"),
                error=payload.get("error"),
                status="error" if payload.get("error") else "ok",
            ))
        elif event.type in {"provider_error", "runtime_error"} and include_errors:
            items.append(_item(
                event,
                kind=event.type,
                error=payload.get("message") or payload.get("error"),
                terminal=payload.get("terminal"),
                payload=payload,
            ))
        elif event.type == "annotation" and include_annotations:
            items.append(_item(
                event,
                kind="annotation",
                annotation_kind=payload.get("kind"),
                data=payload.get("data"),
            ))
        elif event.type in {"compact", "summary", "revert", "fork"}:
            items.append(_item(event, kind=event.type, payload=payload))
    return items


def _item(event: Any, **fields: Any) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "id": event.id,
        "type": event.type,
        **fields,
    }


def _message_text(payload: dict[str, Any], content_placeholder: Any | None) -> str:
    blocks = payload.get("content")
    if blocks is None:
        return str(payload.get("text", ""))
    parts: list[str] = []
    for block in blocks:
        if block.get("type") == "text":
            parts.append(str(block.get("text", "")))
        else:
            parts.append(
                content_placeholder(block)
                if content_placeholder is not None
                else _default_content_placeholder(block)
            )
    return "\n".join(parts)


def _default_content_placeholder(block: dict[str, Any]) -> str:
    parts = [str(block.get("type", ""))]
    if block.get("name"):
        parts.append(str(block["name"]))
    if block.get("media_type"):
        parts.append(str(block["media_type"]))
    size = _content_block_size(block)
    if size > 0:
        parts.append(_format_byte_size(size))
    return f"[{': '.join(parts)}]"


def _content_block_size(block: dict[str, Any]) -> int:
    size = int(block.get("byte_size") or 0)
    if size > 0:
        return size
    source = block.get("source") or {}
    if source.get("kind") != "base64":
        return 0
    try:
        return len(base64.b64decode(str(source.get("data") or ""), validate=True))
    except ValueError:
        return 0


def _format_byte_size(size: int) -> str:
    if size >= 1024:
        return f"{(size + 1023) // 1024}kb"
    return f"{size} bytes"
