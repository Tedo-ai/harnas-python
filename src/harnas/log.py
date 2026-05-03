"""Log — append-only sequence of Events."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterator

from .event import Event


class Log:
    """Append-only event log. The substrate the spec is built around.

    Mirrors `Harnas::Log`. Iteration is in seq order; ids are minted
    at append time and never reused.
    """

    def __init__(self, observation: Any | None = None) -> None:
        self._events: list[Event] = []
        self.observation = observation

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self) -> Iterator[Event]:
        return iter(self._events)

    def __getitem__(self, index: int) -> Event:
        return self._events[index]

    @property
    def size(self) -> int:
        return len(self._events)

    def append(self, type: str, payload: dict[str, Any]) -> Event:
        """Append a new Event. Returns the event with seq + id assigned."""
        seq = len(self._events)
        digest = hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:12]
        event = Event(seq=seq, id=f"evt_{seq}_{digest}", type=type, payload=payload)
        self._events.append(event)
        if self.observation is not None:
            self.observation.emit("event_appended", event=event, log_size=len(self._events))
        return event

    def reverse_each(self) -> Iterator[Event]:
        return iter(reversed(self._events))

    # JSONL persistence (mirrors Harnas::Log#save / .load), included for
    # parity with the Ruby reference. Not exercised by the conformance
    # fixtures themselves but useful for inspection during development.

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            for event in self._events:
                fh.write(json.dumps({
                    "seq": event.seq,
                    "id": event.id,
                    "type": event.type,
                    "payload": event.payload,
                }))
                fh.write("\n")

    @classmethod
    def load(cls, path: str) -> "Log":
        log = cls()
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                log._events.append(Event(
                    seq=row["seq"],
                    id=row["id"],
                    type=row["type"],
                    payload=row["payload"],
                ))
        return log
