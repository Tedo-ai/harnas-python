"""Observation bus and optional streaming sidecar logger."""

from __future__ import annotations

import json
from typing import Any, Callable


Subscriber = Callable[[str, dict[str, Any]], None]


class Observation:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, subscriber: Subscriber) -> Subscriber:
        self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers = [s for s in self._subscribers if s is not subscriber]

    def emit(self, event_name: str, **payload: Any) -> None:
        for subscriber in list(self._subscribers):
            try:
                subscriber(event_name, payload)
            except Exception:
                pass


class DeltaLogger:
    STREAM_EVENT_TYPES = {
        "assistant_turn_started",
        "assistant_text_delta",
        "tool_use_begin",
        "tool_use_argument_delta",
        "tool_use_end",
        "assistant_turn_completed",
        "assistant_turn_failed",
    }

    def __init__(self, path: str, observation: Observation) -> None:
        self.path = path
        self.index = 0
        self.subscriber = observation.subscribe(self)

    def __call__(self, event_name: str, payload: dict[str, Any]) -> None:
        if event_name != "stream_event":
            return
        event = payload.get("event")
        if event is None or event.type not in self.STREAM_EVENT_TYPES:
            return
        with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({
                "index": self.index,
                "type": event.type,
                "payload": event.payload,
            }, separators=(",", ":"), ensure_ascii=False))
            fh.write("\n")
        self.index += 1


class CostTracker:
    def __init__(
        self,
        observation: Observation,
        *,
        threshold: int | None = None,
        on_threshold: Callable[[dict[str, int]], None] | None = None,
    ) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.turns = 0
        self._threshold = threshold
        self._on_threshold = on_threshold
        self._threshold_fired = False
        self.subscriber = observation.subscribe(self)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def usage(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "turns": self.turns,
        }

    def __call__(self, event_name: str, payload: dict[str, Any]) -> None:
        if event_name != "event_appended":
            return
        event = payload.get("event")
        if event is None or event.type != "assistant_message":
            return
        usage = event.payload.get("usage") or {}
        self.input_tokens += int(usage.get("input_tokens") or 0)
        self.output_tokens += int(usage.get("output_tokens") or 0)
        self.turns += 1
        if (
            self._threshold is not None
            and not self._threshold_fired
            and self.total_tokens >= self._threshold
        ):
            self._threshold_fired = True
            if self._on_threshold is not None:
                self._on_threshold(self.usage())
