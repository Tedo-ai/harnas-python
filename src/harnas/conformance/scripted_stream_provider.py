"""Scripted streaming provider for conformance fixtures."""

from __future__ import annotations

from typing import Any, Callable

from .scripted_provider import ProviderHTTPError, RequestMismatch, _normalize, _request_value_equal
from harnas.providers.errors import ProviderError


class Exhausted(Exception):
    """Raised when the script has no more streams to deliver."""


class ScriptedStreamProvider:
    def __init__(self, streams: list[list[dict[str, Any]]]) -> None:
        self._streams = list(streams)
        self.call_count = 0

    def __call__(
        self,
        request: dict[str, Any],
        emit: Callable[[dict[str, Any]], None],
    ) -> None:
        if not self._streams:
            raise Exhausted("no more scripted streams")
        self.call_count += 1
        stream = self._streams.pop(0)
        if isinstance(stream, dict) and "expect_request" in stream:
            expected = _normalize(stream["expect_request"])
            actual = _normalize(request)
            if not _request_value_equal(actual, expected):
                raise RequestMismatch(
                    f"request does not match expected: {actual!r} != {expected!r}"
                )
            stream = stream["response"]
        for event in stream:
            if "error" in event:
                error = event["error"]
                emit({
                    "type": "assistant_turn_failed",
                    "payload": {
                        "turn_id": error["turn_id"],
                        "error": error["message"],
                    },
                })
                raise ProviderHTTPError(error["status"], error["body"])
            if "malformed_frame" in event:
                error = event["malformed_frame"]
                emit({
                    "type": "assistant_turn_failed",
                    "payload": {
                        "turn_id": error["turn_id"],
                        "error": error["message"],
                    },
                })
                raise ProviderError(error["message"])
            emit(event)
