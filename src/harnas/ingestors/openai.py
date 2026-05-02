"""OpenAI ingestor — Chat Completions response -> events to append.

Mirrors `Harnas::Ingestors::OpenAI`. Always emits one
:assistant_message (possibly with empty text), then one :tool_use
per tool_calls entry.
"""

from __future__ import annotations

import json
from typing import Any

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
        }
        reasoning = self._reasoning_blocks(message)
        if reasoning:
            payload["reasoning"] = reasoning

        events: list[dict[str, Any]] = [{"type": "assistant_message", "payload": payload}]
        for call in message.get("tool_calls") or []:
            events.append(self._tool_use_event(call))
        return events

    def _normalize_usage(self, wire_usage: dict[str, Any]) -> dict[str, int]:
        return {
            "input_tokens": wire_usage.get("prompt_tokens", 0),
            "output_tokens": wire_usage.get("completion_tokens", 0),
        }

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
                blocks.append({"type": "text", "text": text})
        return blocks
