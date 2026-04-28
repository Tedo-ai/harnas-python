"""Scripted streaming provider for conformance fixtures."""

from __future__ import annotations

from typing import Any, Callable


class Exhausted(Exception):
    """Raised when the script has no more streams to deliver."""


class ScriptedStreamProvider:
    def __init__(self, streams: list[list[dict[str, Any]]]) -> None:
        self._streams = list(streams)
        self.call_count = 0

    def __call__(
        self,
        _request: dict[str, Any],
        emit: Callable[[dict[str, Any]], None],
    ) -> None:
        if not self._streams:
            raise Exhausted("no more scripted streams")
        self.call_count += 1
        stream = self._streams.pop(0)
        for event in stream:
            emit(event)
