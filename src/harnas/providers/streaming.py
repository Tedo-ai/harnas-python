"""SSE streaming state machines for live providers."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from .errors import ProviderError
from .http import stream_sse


class StreamState:
    def __init__(self, emit: Callable[[dict[str, Any]], None]) -> None:
        self.emit = emit
        self.turn_id = f"turn_{uuid.uuid4().hex[:12]}"
        self.text_parts: list[str] = []
        self.stop = "other"
        self.usage: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0}

    def start(self) -> None:
        self.emit({"type": "assistant_turn_started", "payload": {"turn_id": self.turn_id}})

    def emit_text(self, chunk: str) -> None:
        if chunk == "":
            return
        self.text_parts.append(chunk)
        self.emit({
            "type": "assistant_text_delta",
            "payload": {"turn_id": self.turn_id, "chunk": chunk},
        })

    def complete(self) -> None:
        self.emit({
            "type": "assistant_turn_completed",
            "payload": {
                "turn_id": self.turn_id,
                "stop_reason": self.stop,
                "usage": self.usage,
            },
        })
        self.emit({
            "type": "assistant_message",
            "payload": {
                "text": "".join(self.text_parts),
                "stop_reason": self.stop,
                "usage": self.usage,
            },
        })

    def fail(self, error: Exception) -> None:
        self.emit({
            "type": "assistant_turn_failed",
            "payload": {"turn_id": self.turn_id, "error": str(error)},
        })


class ToolState:
    def __init__(self, tool_id: str = "", name: str = "") -> None:
        self.id = tool_id
        self.name = name
        self.arg_chunks: list[str] = []
        self.arguments: dict[str, Any] = {}
        self.emitted_begin = False


class AnthropicStreamState(StreamState):
    def __init__(self, emit: Callable[[dict[str, Any]], None]) -> None:
        super().__init__(emit)
        self.tools: dict[int, ToolState] = {}

    def data(self, raw: str) -> None:
        payload = _loads(raw)
        event_type = payload.get("type")
        if event_type == "content_block_start":
            block = _as_dict(payload.get("content_block"))
            if block.get("type") == "tool_use":
                index = int(payload.get("index") or 0)
                tool = ToolState(str(block.get("id") or ""), str(block.get("name") or ""))
                tool.emitted_begin = True
                self.tools[index] = tool
                self.emit({
                    "type": "tool_use_begin",
                    "payload": {
                        "turn_id": self.turn_id,
                        "tool_use_id": tool.id,
                        "name": tool.name,
                    },
                })
        elif event_type == "content_block_delta":
            delta = _as_dict(payload.get("delta"))
            if delta.get("type") == "text_delta":
                self.emit_text(str(delta.get("text") or ""))
            elif delta.get("type") == "input_json_delta":
                tool = self.tools.get(int(payload.get("index") or 0))
                if tool is not None:
                    chunk = str(delta.get("partial_json") or "")
                    tool.arg_chunks.append(chunk)
                    self.emit({
                        "type": "tool_use_argument_delta",
                        "payload": {
                            "turn_id": self.turn_id,
                            "tool_use_id": tool.id,
                            "chunk": chunk,
                        },
                    })
        elif event_type == "content_block_stop":
            tool = self.tools.get(int(payload.get("index") or 0))
            if tool is not None:
                tool.arguments = _parse_arguments(tool.arg_chunks)
                self.emit({
                    "type": "tool_use_end",
                    "payload": {
                        "turn_id": self.turn_id,
                        "tool_use_id": tool.id,
                        "arguments": tool.arguments,
                    },
                })
        elif event_type == "message_delta":
            delta = _as_dict(payload.get("delta"))
            if delta.get("stop_reason"):
                self.stop = _anthropic_stop(str(delta["stop_reason"]))
            usage = _as_dict(payload.get("usage"))
            if usage:
                self.usage = {
                    "input_tokens": usage.get("input_tokens", self.usage["input_tokens"]),
                    "output_tokens": usage.get("output_tokens", self.usage["output_tokens"]),
                }

    def complete(self) -> None:
        super().complete()
        for index in sorted(self.tools):
            tool = self.tools[index]
            self.emit({
                "type": "tool_use",
                "payload": {"id": tool.id, "name": tool.name, "arguments": tool.arguments},
            })


class OpenAIStreamState(StreamState):
    def __init__(self, emit: Callable[[dict[str, Any]], None]) -> None:
        super().__init__(emit)
        self.tools: dict[int, ToolState] = {}

    def data(self, raw: str) -> None:
        payload = _loads(raw)
        usage = _as_dict(payload.get("usage"))
        if usage:
            self.usage = {
                "input_tokens": usage.get("prompt_tokens", self.usage["input_tokens"]),
                "output_tokens": usage.get("completion_tokens", self.usage["output_tokens"]),
            }
        choices = payload.get("choices") or []
        choice = _as_dict(choices[0]) if choices else {}
        delta = _as_dict(choice.get("delta"))
        if delta:
            self._handle_delta(delta)
        finish = choice.get("finish_reason")
        if finish:
            self.stop = _openai_stop(str(finish))
            for tool in self.tools.values():
                tool.arguments = _parse_arguments(tool.arg_chunks)
                self.emit({
                    "type": "tool_use_end",
                    "payload": {
                        "turn_id": self.turn_id,
                        "tool_use_id": tool.id,
                        "arguments": tool.arguments,
                    },
                })

    def _handle_delta(self, delta: dict[str, Any]) -> None:
        self.emit_text(str(delta.get("content") or ""))
        for raw_call in delta.get("tool_calls") or []:
            call = _as_dict(raw_call)
            index = int(call.get("index") or 0)
            tool = self.tools.setdefault(index, ToolState())
            if call.get("id"):
                tool.id = str(call["id"])
            function = _as_dict(call.get("function"))
            if function.get("name"):
                tool.name = str(function["name"])
            if tool.id and tool.name and not tool.emitted_begin:
                tool.emitted_begin = True
                self.emit({
                    "type": "tool_use_begin",
                    "payload": {
                        "turn_id": self.turn_id,
                        "tool_use_id": tool.id,
                        "name": tool.name,
                    },
                })
            if function.get("arguments"):
                chunk = str(function["arguments"])
                tool.arg_chunks.append(chunk)
                self.emit({
                    "type": "tool_use_argument_delta",
                    "payload": {
                        "turn_id": self.turn_id,
                        "tool_use_id": tool.id,
                        "chunk": chunk,
                    },
                })

    def complete(self) -> None:
        super().complete()
        for index in sorted(self.tools):
            tool = self.tools[index]
            self.emit({
                "type": "tool_use",
                "payload": {"id": tool.id, "name": tool.name, "arguments": tool.arguments},
            })


class GeminiStreamState(StreamState):
    def __init__(self, emit: Callable[[dict[str, Any]], None]) -> None:
        super().__init__(emit)
        self.tools: list[ToolState] = []

    def data(self, raw: str) -> None:
        payload = _loads(raw)
        candidates = payload.get("candidates") or []
        candidate = _as_dict(candidates[0]) if candidates else {}
        content = _as_dict(candidate.get("content"))
        for part_raw in content.get("parts") or []:
            part = _as_dict(part_raw)
            if part.get("text"):
                self.emit_text(str(part["text"]))
            function_call = _as_dict(part.get("functionCall"))
            if function_call:
                tool = ToolState(
                    f"gemini_fc_{len(self.tools)}",
                    str(function_call.get("name") or ""),
                )
                tool.arguments = _as_dict(function_call.get("args"))
                self.tools.append(tool)
                self.emit({
                    "type": "tool_use_begin",
                    "payload": {
                        "turn_id": self.turn_id,
                        "tool_use_id": tool.id,
                        "name": tool.name,
                    },
                })
                self.emit({
                    "type": "tool_use_end",
                    "payload": {
                        "turn_id": self.turn_id,
                        "tool_use_id": tool.id,
                        "arguments": tool.arguments,
                    },
                })
        if candidate.get("finishReason"):
            self.stop = _gemini_stop(str(candidate["finishReason"]))
        usage = _as_dict(payload.get("usageMetadata"))
        if usage:
            self.usage = {
                "input_tokens": usage.get("promptTokenCount", self.usage["input_tokens"]),
                "output_tokens": usage.get("candidatesTokenCount", self.usage["output_tokens"]),
            }

    def complete(self) -> None:
        super().complete()
        for tool in self.tools:
            self.emit({
                "type": "tool_use",
                "payload": {"id": tool.id, "name": tool.name, "arguments": tool.arguments},
            })


def run_stream(
    endpoint: str,
    headers: dict[str, str],
    body: dict[str, Any],
    state: StreamState,
    *,
    opener: Callable[..., Any] | None = None,
) -> None:
    state.start()
    try:
        stream_sse(endpoint, headers, body, state.data, opener=opener)  # type: ignore[attr-defined]
    except Exception as error:
        state.fail(error)
        raise
    state.complete()


def _loads(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_arguments(chunks: list[str]) -> dict[str, Any]:
    if not chunks:
        return {}
    try:
        parsed = json.loads("".join(chunks))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _anthropic_stop(stop: str) -> str:
    return {
        "end_turn": "end_turn",
        "max_tokens": "max_tokens",
        "tool_use": "tool_use",
        "stop_sequence": "stop_sequence",
        "refusal": "refusal",
    }.get(stop, "other")


def _openai_stop(stop: str) -> str:
    return {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "function_call": "tool_use",
        "content_filter": "refusal",
    }.get(stop, "other")


def _gemini_stop(stop: str) -> str:
    return {
        "STOP": "end_turn",
        "MAX_TOKENS": "max_tokens",
        "SAFETY": "refusal",
        "RECITATION": "refusal",
        "OTHER": "other",
    }.get(stop, "other")
