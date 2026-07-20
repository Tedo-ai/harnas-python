"""SSE streaming state machines for live providers."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from ..usage import normalize as normalize_usage
from .errors import ProviderProtocolError, ProviderStreamError
from .http import stream_sse


class StreamState:
    def __init__(self, provider: str, emit: Callable[[dict[str, Any]], None]) -> None:
        self.provider = provider
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
                "usage": normalize_usage(self.usage),
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
        super().__init__("anthropic", emit)
        self.tools: dict[int, ToolState] = {}
        self.open_blocks: dict[int, str] = {}
        self.message_started = False
        self.message_stopped = False
        self.stop_seen = False

    def data(self, raw: str) -> None:
        payload = _loads(raw, self.provider)
        event_type = payload.get("type")
        if not isinstance(event_type, str) or event_type == "":
            raise _protocol(self.provider, "invalid_frame", "SSE event is missing type")
        if event_type == "error":
            error = _as_dict(payload.get("error"))
            error_type = str(error.get("type") or "")
            raise ProviderStreamError(
                self.provider,
                error_type,
                str(error.get("message") or ""),
                request_id=str(payload.get("request_id") or ""),
                status=_anthropic_error_status(error_type),
            )
        if event_type == "ping":
            return
        if event_type == "message_start":
            if self.message_started:
                raise _protocol(self.provider, "duplicate_start", "duplicate message_start event")
            if self.message_stopped:
                raise _protocol(self.provider, "invalid_order", "message_start arrived after message_stop")
            self.message_started = True
            usage = _as_dict(_as_dict(payload.get("message")).get("usage"))
            self._merge_usage(usage)
        elif event_type == "content_block_start":
            self._require_active(event_type)
            index = int(payload.get("index") or 0)
            if index in self.open_blocks:
                raise _protocol(self.provider, "duplicate_block_start", "duplicate content_block_start index")
            block = _as_dict(payload.get("content_block"))
            block_type = str(block.get("type") or "")
            if block_type == "":
                raise _protocol(self.provider, "invalid_frame", "content block is missing type")
            self.open_blocks[index] = block_type
            if block_type == "tool_use":
                tool = ToolState(str(block.get("id") or ""), str(block.get("name") or ""))
                if not tool.id or not tool.name:
                    raise _protocol(self.provider, "invalid_tool", "tool_use block requires id and name")
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
            self._require_active(event_type)
            index = int(payload.get("index") or 0)
            block_type = self.open_blocks.get(index)
            if block_type is None:
                raise _protocol(self.provider, "invalid_order", "content_block_delta has no open block")
            delta = _as_dict(payload.get("delta"))
            if delta.get("type") == "text_delta":
                if block_type == "tool_use":
                    raise _protocol(self.provider, "invalid_frame", "text delta arrived for tool_use block")
                self.emit_text(str(delta.get("text") or ""))
            elif delta.get("type") == "input_json_delta":
                tool = self.tools.get(index)
                if tool is None:
                    raise _protocol(self.provider, "invalid_frame", "input_json_delta arrived outside tool_use block")
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
            else:
                raise _protocol(self.provider, "invalid_frame", "unknown content block delta type")
        elif event_type == "content_block_stop":
            self._require_active(event_type)
            index = int(payload.get("index") or 0)
            if index not in self.open_blocks:
                raise _protocol(self.provider, "invalid_order", "content_block_stop has no open block")
            del self.open_blocks[index]
            tool = self.tools.get(index)
            if tool is not None:
                tool.arguments = _parse_arguments(tool.arg_chunks, self.provider)
                self.emit({
                    "type": "tool_use_end",
                    "payload": {
                        "turn_id": self.turn_id,
                        "tool_use_id": tool.id,
                        "arguments": tool.arguments,
                    },
                })
        elif event_type == "message_delta":
            self._require_active(event_type)
            delta = _as_dict(payload.get("delta"))
            if delta.get("stop_reason"):
                if self.stop_seen:
                    raise _protocol(self.provider, "duplicate_terminal", "duplicate stop_reason")
                self.stop = _anthropic_stop(str(delta["stop_reason"]))
                self.stop_seen = True
            usage = _as_dict(payload.get("usage"))
            if usage:
                self._merge_usage(usage)
        elif event_type == "message_stop":
            if not self.message_started:
                raise _protocol(self.provider, "invalid_order", "message_stop arrived before message_start")
            if self.message_stopped:
                raise _protocol(self.provider, "duplicate_terminal", "duplicate message_stop event")
            if self.open_blocks:
                raise _protocol(self.provider, "incomplete_block", "message_stop arrived with an open content block")
            if not self.stop_seen:
                raise _protocol(self.provider, "missing_stop_reason", "message_stop arrived without stop_reason")
            self.message_stopped = True

    def complete(self) -> None:
        if not self.message_started:
            raise _protocol(self.provider, "missing_start", "stream ended before message_start")
        if not self.message_stopped:
            raise _protocol(self.provider, "missing_terminal", "stream ended before message_stop")
        if not self.stop_seen:
            raise _protocol(self.provider, "missing_stop_reason", "stream ended without stop_reason")
        super().complete()
        for index in sorted(self.tools):
            tool = self.tools[index]
            self.emit({
                "type": "tool_use",
                "payload": {"id": tool.id, "name": tool.name, "arguments": tool.arguments},
            })

    def _require_active(self, event_type: str) -> None:
        if not self.message_started:
            raise _protocol(self.provider, "invalid_order", f"{event_type} arrived before message_start")
        if self.message_stopped:
            raise _protocol(self.provider, "invalid_order", f"{event_type} arrived after message_stop")

    def _merge_usage(self, usage: dict[str, Any]) -> None:
        if "input_tokens" in usage:
            self.usage["input_tokens"] = usage["input_tokens"]
        if "output_tokens" in usage:
            self.usage["output_tokens"] = usage["output_tokens"]


class OpenAIStreamState(StreamState):
    def __init__(self, emit: Callable[[dict[str, Any]], None]) -> None:
        super().__init__("openai", emit)
        self.tools: dict[int, ToolState] = {}
        self.finish_seen = False
        self.done_seen = False

    def data(self, raw: str) -> None:
        if raw == "[DONE]":
            if self.done_seen:
                raise _protocol(self.provider, "duplicate_terminal", "duplicate [DONE] sentinel")
            self.done_seen = True
            return
        if self.done_seen:
            raise _protocol(self.provider, "invalid_order", "data arrived after [DONE]")
        payload = _loads(raw, self.provider)
        wire_error = _as_dict(payload.get("error"))
        if wire_error:
            error_type = str(wire_error.get("type") or wire_error.get("code") or "")
            raise ProviderStreamError(
                self.provider,
                error_type,
                str(wire_error.get("message") or ""),
                request_id=str(payload.get("request_id") or ""),
                status=int(wire_error.get("status") or 0),
            )
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
            if self.finish_seen:
                raise _protocol(self.provider, "invalid_order", "delta arrived after finish_reason")
            self._handle_delta(delta)
        finish = choice.get("finish_reason")
        if finish:
            if self.finish_seen:
                raise _protocol(self.provider, "duplicate_terminal", "duplicate finish_reason")
            self.finish_seen = True
            self.stop = _openai_stop(str(finish))
            for tool in self.tools.values():
                if not tool.emitted_begin:
                    raise _protocol(self.provider, "invalid_tool", "tool call completed without id and name")
                tool.arguments = _parse_arguments(tool.arg_chunks, self.provider)
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
                if not tool.emitted_begin:
                    raise _protocol(self.provider, "invalid_tool", "tool arguments arrived before id and name")
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
        if not self.done_seen:
            raise _protocol(self.provider, "missing_terminal", "stream ended before [DONE]")
        if not self.finish_seen:
            raise _protocol(self.provider, "missing_finish_reason", "stream ended without finish_reason")
        super().complete()
        for index in sorted(self.tools):
            tool = self.tools[index]
            self.emit({
                "type": "tool_use",
                "payload": {"id": tool.id, "name": tool.name, "arguments": tool.arguments},
            })


class GeminiStreamState(StreamState):
    def __init__(self, emit: Callable[[dict[str, Any]], None]) -> None:
        super().__init__("gemini", emit)
        self.tools: list[ToolState] = []
        self.finish_seen = False

    def data(self, raw: str) -> None:
        payload = _loads(raw, self.provider)
        wire_error = _as_dict(payload.get("error"))
        if wire_error:
            error_type = str(wire_error.get("status") or wire_error.get("type") or "")
            raise ProviderStreamError(
                self.provider,
                error_type,
                str(wire_error.get("message") or ""),
                request_id=str(payload.get("request_id") or ""),
                status=int(wire_error.get("code") or 0),
            )
        if self.finish_seen:
            raise _protocol(self.provider, "invalid_order", "data arrived after finishReason")
        candidates = payload.get("candidates") or []
        candidate = _as_dict(candidates[0]) if candidates else {}
        content = _as_dict(candidate.get("content"))
        for part_raw in content.get("parts") or []:
            part = _as_dict(part_raw)
            if part.get("text"):
                self.emit_text(str(part["text"]))
            function_call = _as_dict(part.get("functionCall"))
            if function_call:
                name = str(function_call.get("name") or "")
                if not name:
                    raise _protocol(self.provider, "invalid_tool", "functionCall requires name")
                tool = ToolState(
                    f"gemini_fc_{len(self.tools)}",
                    name,
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
            if self.finish_seen:
                raise _protocol(self.provider, "duplicate_terminal", "duplicate finishReason")
            self.finish_seen = True
            self.stop = _gemini_stop(str(candidate["finishReason"]))
        usage = _as_dict(payload.get("usageMetadata"))
        if usage:
            self.usage = {
                "input_tokens": usage.get("promptTokenCount", self.usage["input_tokens"]),
                "output_tokens": usage.get("candidatesTokenCount", self.usage["output_tokens"]),
            }

    def complete(self) -> None:
        if not self.finish_seen:
            raise _protocol(self.provider, "missing_terminal", "stream ended before finishReason")
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
        state.complete()
    except Exception as error:
        state.fail(error)
        raise


def _loads(raw: str, provider: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise _protocol(provider, "invalid_json", f"invalid SSE JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise _protocol(provider, "invalid_frame", "SSE payload must be an object")
    return parsed


def _parse_arguments(chunks: list[str], provider: str) -> dict[str, Any]:
    if not chunks:
        return {}
    try:
        parsed = json.loads("".join(chunks))
    except json.JSONDecodeError as error:
        raise _protocol(provider, "invalid_tool_arguments", f"tool arguments are not valid JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise _protocol(provider, "invalid_tool_arguments", "tool arguments must be a JSON object")
    return parsed


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


def _protocol(provider: str, reason: str, message: str) -> ProviderProtocolError:
    return ProviderProtocolError(provider, reason, message)


def _anthropic_error_status(error_type: str) -> int:
    return {
        "invalid_request_error": 400,
        "authentication_error": 401,
        "billing_error": 402,
        "permission_error": 403,
        "not_found_error": 404,
        "request_too_large": 413,
        "rate_limit_error": 429,
        "api_error": 500,
        "timeout_error": 504,
        "overloaded_error": 529,
    }.get(error_type, 0)
