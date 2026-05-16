"""UI-neutral projection from a Harnas Log to transcript items."""

from __future__ import annotations

from typing import Any


def project(
    log: Any,
    *,
    include_tools: bool = True,
    include_errors: bool = True,
    include_annotations: bool = False,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for event in log:
        payload = event.payload
        if event.type == "user_message":
            items.append(_item(event, kind="user", role="user", text=str(payload.get("text", ""))))
        elif event.type == "assistant_message":
            items.append(_item(
                event,
                kind="assistant",
                role="assistant",
                text=str(payload.get("text", "")),
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
