"""OpenAI projection — Log -> Chat Completions request body.

Mirrors `Harnas::Projections::OpenAI`. Folds :tool_use into the
preceding assistant message's tool_calls; emits :tool_result as
{role: "tool", tool_call_id, content}.
"""

from __future__ import annotations

import json
from typing import Any

from .. import mutations
from .. import content_blocks
from ..attachments import AttachmentStore
from ..log import Log


class OpenAI:
    def __init__(
        self,
        model: str,
        registry: Any | None = None,
        system: str | None = None,
        attachment_store: AttachmentStore | None = None,
    ) -> None:
        self._model = model
        self._registry = registry
        self._system = system
        self._attachment_store = attachment_store

    def __call__(self, log: Log) -> dict[str, Any]:
        effective = mutations.apply(log)
        messages = self._build_messages(effective)
        if self._system:
            messages = [{"role": "system", "content": self._system}, *messages]

        request: dict[str, Any] = {"model": self._model, "messages": messages}
        if self._registry is not None and self._registry.size > 0:
            request["tools"] = self._tool_descriptors()
        return request

    def _build_messages(self, events: list) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for evt in events:
            self._append_event(messages, evt)
        return messages

    def _append_event(self, messages: list[dict[str, Any]], evt) -> None:
        match evt.type:
            case "user_message" | "summary":
                messages.append({"role": "user", "content": self._content(evt.payload)})
            case "assistant_message":
                messages.append({"role": "assistant", "content": self._content(evt.payload)})
            case "tool_use":
                self._merge_tool_use(messages, evt)
            case "tool_result":
                content = evt.payload.get("error") or str(evt.payload.get("output", ""))
                messages.append({
                    "role": "tool",
                    "tool_call_id": evt.payload["tool_use_id"],
                    "content": content,
                })

    def _merge_tool_use(self, messages: list[dict[str, Any]], evt) -> None:
        wire_call = {
            "id": evt.payload["id"],
            "type": "function",
            "function": {
                "name": evt.payload["name"],
                "arguments": json.dumps(
                    evt.payload.get("arguments") or {},
                    separators=(",", ":"),
                    sort_keys=True,
                    ensure_ascii=False,
                ),
            },
        }
        prev = messages[-1] if messages else None
        if prev and prev.get("role") == "assistant":
            prev.setdefault("tool_calls", []).append(wire_call)
            if prev.get("content") == "":
                prev["content"] = None
        else:
            messages.append({"role": "assistant", "content": None, "tool_calls": [wire_call]})

    def _content(self, payload: dict[str, Any]) -> Any:
        blocks = content_blocks.from_payload(payload)
        if len(blocks) == 1 and blocks[0].get("type") == "text":
            return str(blocks[0].get("text", ""))
        rendered = []
        for block in blocks:
            match block.get("type"):
                case "text":
                    rendered.append({"type": "text", "text": str(block.get("text", ""))})
                case "image":
                    rendered.append({"type": "image_url", "image_url": {"url": self._image_url(block)}})
                case _:
                    raise ValueError(f"unsupported OpenAI content block type: {block.get('type')}")
        return rendered

    def _image_url(self, block: dict[str, Any]) -> str:
        source = dict(block.get("source") or {})
        if source.get("kind") == "url":
            return str(source.get("url", ""))
        resolved = content_blocks.resolve_data(block, self._attachment_store)
        return f"data:{resolved['media_type']};base64,{resolved['data']}"

    def _tool_descriptors(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in self._registry.tools
        ]
