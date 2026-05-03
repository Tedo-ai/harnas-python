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
