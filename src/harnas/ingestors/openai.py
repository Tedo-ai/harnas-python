"""OpenAI ingestor — Chat Completions response -> events to append.

Mirrors `Harnas::Ingestors::OpenAI`. Always emits one
:assistant_message (possibly with empty text), then one :tool_use
per tool_calls entry.
"""

from __future__ import annotations

import json
from typing import Any

from .. import provider_carriers
from .. import usage as usage_helpers

FINISH_REASON_MAP = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "content_filter": "refusal",
}


class OpenAI:
    def __call__(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        choices = response.get("choices") or []
        if not choices:
            raise ValueError("response has no choices")

        choice = choices[0]
        message = choice.get("message") or {}
        stop = FINISH_REASON_MAP.get(choice.get("finish_reason"), "other")
        usage = self._normalize_usage(response.get("usage") or {})

        payload: dict[str, Any] = {
            "text": str(message.get("content") or ""),
            "stop_reason": stop,
            "usage": usage,
            "provider": "openai",
            "model": str(response.get("model") or ""),
        }
        reasoning = self._reasoning_blocks(message)
        if reasoning:
            payload["reasoning"] = reasoning
        if self._carrier_data(message):
            if payload["text"]:
                payload["content"] = [{
                    "type": "text",
                    "text": payload["text"],
                    "provider_parts": [
                        provider_carriers.carrier(
                            destination="openai.chat_completions",
                            index=0,
                            kind="openai.message_content",
                            wire={"content": payload["text"]},
                            canonical_refs=["payload.content[0]"],
                        )
                    ],
                }]
            payload["provider_items"] = [
                provider_carriers.carrier(
                    destination="openai.chat_completions",
                    index=0,
                    kind="openai.chat_message",
                    wire=message,
                    canonical_refs=[
                        *(["payload.content[0]"] if payload["text"] else []),
                        "payload.reasoning[0]",
                    ],
                )
            ]

        events: list[dict[str, Any]] = [{"type": "assistant_message", "payload": payload}]
        for call in message.get("tool_calls") or []:
            events.append(self._tool_use_event(call))
        return events

    def _normalize_usage(self, wire_usage: dict[str, Any]) -> dict[str, int]:
        return usage_helpers.normalize(wire_usage)

    def _tool_use_event(self, call: dict[str, Any]) -> dict[str, Any]:
        fn = call.get("function") or {}
        return {
            "type": "tool_use",
            "payload": {
                "id": str(call.get("id", "")),
                "name": str(fn.get("name", "")),
                "arguments": self._parse_arguments(fn.get("arguments")),
            },
        }

    def _parse_arguments(self, raw: Any) -> dict[str, Any]:
        if raw is None or raw == "":
            return {}
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _reasoning_blocks(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        reasoning = message.get("reasoning")
        if isinstance(reasoning, str) and reasoning:
            blocks.append({"type": "text", "text": reasoning})
        for detail in message.get("reasoning_details") or []:
            if not isinstance(detail, dict):
                continue
            text = detail.get("text") or detail.get("reasoning") or detail.get("content")
            if isinstance(text, str) and text:
                out: dict[str, Any] = {"type": "text", "text": text}
                if self._reasoning_detail_carrier_data(detail):
                    out["provider_parts"] = [
                        provider_carriers.carrier(
                            destination="openai.chat_completions",
                            index=len(blocks),
                            kind="openai.reasoning_detail",
                            wire=detail,
                            canonical_refs=[f"payload.reasoning[{len(blocks)}]"],
                        )
                    ]
                blocks.append(out)
        return blocks

    def _carrier_data(self, message: dict[str, Any]) -> bool:
        return any(
            isinstance(detail, dict) and self._reasoning_detail_carrier_data(detail)
            for detail in message.get("reasoning_details") or []
        )

    def _reasoning_detail_carrier_data(self, detail: dict[str, Any]) -> bool:
        return any(key not in {"type", "text", "reasoning", "content"} for key in detail)
