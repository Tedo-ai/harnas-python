"""Anthropic projection — Log -> Messages API request body.

Mirrors `Harnas::Projections::Anthropic`. Adjacent events by the same
role collapse into a single wire message; a group of one text block
uses the legacy plain-string form so simple bodies stay simple (and
recorded text-only fixtures match byte-for-byte).
"""

from __future__ import annotations

from typing import Any

from .. import mutations
from ..log import Log


class Anthropic:
    DEFAULT_MAX_TOKENS = 1024

    def __init__(
        self,
        model: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        registry: Any | None = None,
        system: str | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._registry = registry
        self._system = system

    def __call__(self, log: Log) -> dict[str, Any]:
        effective = mutations.apply(log)
        messages = self._group_messages(effective)

        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": messages,
        }
        if self._system:
            request["system"] = self._system
        if self._registry is not None and self._registry.size > 0:
            request["tools"] = self._tool_descriptors()
        return request

    def _group_messages(self, events: list) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for evt in events:
            translated = self._translate(evt)
            if translated is None:
                continue
            role, block = translated
            if current and current["role"] == role:
                current["blocks"].append(block)
            else:
                if current is not None:
                    groups.append(current)
                current = {"role": role, "blocks": [block]}
        if current is not None:
            groups.append(current)
        return [self._finalize(g["role"], g["blocks"]) for g in groups]

    def _finalize(self, role: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
        if len(blocks) == 1 and blocks[0].get("type") == "text":
            return {"role": role, "content": blocks[0]["text"]}
        return {"role": role, "content": blocks}

    def _translate(self, evt) -> tuple[str, dict[str, Any]] | None:
        match evt.type:
            case "user_message" | "summary":
                return ("user", {"type": "text", "text": evt.payload["text"]})
            case "assistant_message":
                text = evt.payload.get("text", "")
                if not text:
                    return None
                return ("assistant", {"type": "text", "text": text})
            case "tool_use":
                return ("assistant", {
                    "type": "tool_use",
                    "id": evt.payload["id"],
                    "name": evt.payload["name"],
                    "input": evt.payload.get("arguments", {}),
                })
            case "tool_result":
                block: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": evt.payload["tool_use_id"],
                }
                if evt.payload.get("error"):
                    block["content"] = evt.payload["error"]
                    block["is_error"] = True
                else:
                    block["content"] = evt.payload.get("output", "")
                return ("user", block)
            case _:
                return None

    def _tool_descriptors(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in self._registry.tools
        ]
