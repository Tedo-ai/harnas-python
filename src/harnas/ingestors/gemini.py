"""Gemini ingestor — generateContent response -> events to append.

Mirrors `Harnas::Ingestors::Gemini`. Synthesizes a deterministic
per-instance id for each :tool_use (gemini.<name>.<counter>) so
repeated calls don't collide. Emits an :annotation event right
after each :tool_use whenever the matching functionCall part
carries a thoughtSignature.
"""

from __future__ import annotations

from typing import Any

FINISH_REASON_MAP = {
    "STOP": "end_turn",
    "MAX_TOKENS": "max_tokens",
    "SAFETY": "refusal",
    "RECITATION": "refusal",
    "OTHER": "other",
}

THOUGHT_SIGNATURE_KIND = "gemini.thought_signature"


class Gemini:
    def __init__(self) -> None:
        self._tool_call_counter = 0

    def __call__(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = response.get("candidates") or []
        if not candidates:
            raise ValueError("response has no candidates")

        candidate = candidates[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        stop = self._resolve_stop_reason(candidate.get("finishReason"), parts)
        usage = self._normalize_usage(response.get("usageMetadata") or {})

        events: list[dict[str, Any]] = [self._assistant_event(parts, stop, usage)]
        for part in parts:
            fn_call = part.get("functionCall")
            if not fn_call:
                continue
            events.append(self._tool_use_event(fn_call))
            sig = part.get("thoughtSignature")
            if sig:
                events.append(self._signature_annotation(fn_call.get("name", ""), sig))
        return events

    def _assistant_event(self, parts: list[dict[str, Any]], stop: str, usage: dict[str, int]) -> dict[str, Any]:
        text = "".join(p.get("text", "") for p in parts if "text" in p)
        payload: dict[str, Any] = {"text": text, "stop_reason": stop, "usage": usage}
        reasoning = self._reasoning_blocks(parts)
        if reasoning:
            payload["reasoning"] = reasoning
        return {
            "type": "assistant_message",
            "payload": payload,
        }

    def _reasoning_blocks(self, parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for part in parts:
            thought = part.get("thought") or part.get("thoughtSummary") or part.get("thought_summary")
            if isinstance(thought, str) and thought:
                blocks.append({"type": "text", "text": thought})
        return blocks

    def _tool_use_event(self, call: dict[str, Any]) -> dict[str, Any]:
        name = str(call.get("name", ""))
        return {
            "type": "tool_use",
            "payload": {
                "id": self._synthesize_id(name),
                "name": name,
                "arguments": call.get("args") or {},
            },
        }

    def _synthesize_id(self, name: str) -> str:
        synth = f"gemini.{name}.{self._tool_call_counter}"
        self._tool_call_counter += 1
        return synth

    def _signature_annotation(self, name: str, signature: str) -> dict[str, Any]:
        return {
            "type": "annotation",
            "payload": {
                "kind": THOUGHT_SIGNATURE_KIND,
                "data": {"name": name, "signature": signature},
            },
        }

    def _resolve_stop_reason(self, wire_finish: Any, parts: list[dict[str, Any]]) -> str:
        if any("functionCall" in p for p in parts):
            return "tool_use"
        return FINISH_REASON_MAP.get(wire_finish, "other")

    def _normalize_usage(self, wire_usage: dict[str, Any]) -> dict[str, int]:
        return {
            "input_tokens": wire_usage.get("promptTokenCount", 0),
            "output_tokens": wire_usage.get("candidatesTokenCount", 0),
        }
