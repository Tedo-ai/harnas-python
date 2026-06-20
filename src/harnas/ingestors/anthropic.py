"""Anthropic ingestor — Messages API response -> events to append.

Mirrors `Harnas::Ingestors::Anthropic`. Always emits one
:assistant_message (even when text is empty) with the consolidated
text and stop_reason, then zero or more :tool_use events in
content-array order.
"""

from __future__ import annotations

from typing import Any

from .. import provider_carriers
from .. import usage as usage_helpers

STOP_REASON_MAP = {
    "end_turn": "end_turn",
    "max_tokens": "max_tokens",
    "tool_use": "tool_use",
    "stop_sequence": "stop_sequence",
    "refusal": "refusal",
}


class Anthropic:
    def __call__(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        content = response.get("content") or []
        stop = STOP_REASON_MAP.get(response.get("stop_reason"), "other")
        usage = self._normalize_usage(response.get("usage") or {})

        events: list[dict[str, Any]] = [self._assistant_event(content, stop, usage, response)]
        for block in content:
            if block.get("type") == "tool_use":
                events.append(self._tool_use_event(block))
        return events

    def _normalize_usage(self, wire_usage: dict[str, Any]) -> dict[str, int]:
        return usage_helpers.normalize(wire_usage)

    def _assistant_event(
        self, content: list[dict[str, Any]], stop: str, usage: dict[str, int], response: dict[str, Any]
    ) -> dict[str, Any]:
        text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        payload: dict[str, Any] = {
            "text": text,
            "stop_reason": stop,
            "usage": usage,
            "provider": "anthropic",
        }
        if response.get("model"):
            payload["model"] = str(response["model"])
        reasoning = self._reasoning_blocks(content)
        if reasoning:
            payload["reasoning"] = reasoning
        if self._carrier_data(content):
            if text:
                payload["content"] = [{
                    "type": "text",
                    "text": text,
                    "provider_parts": [
                        provider_carriers.carrier(
                            destination="anthropic.messages",
                            index=0,
                            kind="anthropic.content_block",
                            wire={"type": "text", "text": text},
                            canonical_refs=["payload.content[0]"],
                        )
                    ],
                }]
            carrier_content = [block for block in content if block.get("type") != "tool_use"]
            refs = ["payload.reasoning[0]"]
            if text:
                refs.append("payload.content[0]")
            if carrier_content:
                payload["provider_items"] = [
                    provider_carriers.carrier(
                        destination="anthropic.messages",
                        index=0,
                        kind="anthropic.content",
                        wire=carrier_content,
                        canonical_refs=refs,
                    )
                ]
        return {
            "type": "assistant_message",
            "payload": payload,
        }

    def _reasoning_blocks(self, content: list[dict[str, Any]]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for block in content:
            if block.get("type") != "thinking":
                continue
            out = {"type": "text", "text": str(block.get("thinking") or "")}
            if block.get("signature"):
                out["signature"] = str(block["signature"])
                out["provider_parts"] = [
                    provider_carriers.carrier(
                        destination="anthropic.messages",
                        index=0,
                        kind="anthropic.content_block",
                        wire=block,
                        canonical_refs=["payload.reasoning[0]"],
                    )
                ]
            blocks.append(out)
        return blocks

    def _carrier_data(self, content: list[dict[str, Any]]) -> bool:
        return any(block.get("type") == "thinking" and block.get("signature") for block in content)

    def _tool_use_event(self, block: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "tool_use",
            "payload": {
                "id": block["id"],
                "name": block["name"],
                "arguments": block.get("input") or {},
            },
        }
