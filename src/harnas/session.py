"""Session — id + Log + metadata bundle."""

from __future__ import annotations

import uuid
import json
from dataclasses import dataclass, field
from typing import Any

from .hooks import Hooks
from .log import Log
from .event import Event

SESSION_HEADER_KEY = "__session__"


@dataclass
class Session:
    """Bundles a stable id with one Log and optional metadata.

    Mirrors `Harnas::Session`.
    """

    id: str
    log: Log = field(default_factory=Log)
    metadata: dict[str, Any] = field(default_factory=dict)
    hooks: Hooks = field(default_factory=Hooks)

    @classmethod
    def create(cls, metadata: dict[str, Any] | None = None) -> "Session":
        return cls(id=f"ses_{uuid.uuid4()}", log=Log(), metadata=metadata or {})

    def install(self, strategy: Any, **config: Any) -> Any:
        return strategy.install(self, **config)

    def fork(self, at_seq: int) -> "Session":
        if not isinstance(at_seq, int):
            raise ValueError("at_seq must be an int")
        if at_seq < 0 or at_seq >= self.log.size:
            raise ValueError("at_seq out of range")

        forked = Session.create(metadata={
            **self.metadata,
            "forked_from": self.id,
            "forked_at_seq": at_seq,
        })
        for event in list(self.log)[: at_seq + 1]:
            forked.log._events.append(event)
        return forked

    def save(self, path: str) -> "Session":
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({
                SESSION_HEADER_KEY: True,
                "id": self.id,
                "metadata": self.metadata,
            }, separators=(",", ":"), ensure_ascii=False))
            fh.write("\n")
            for event in self.log:
                fh.write(json.dumps({
                    "seq": event.seq,
                    "id": event.id,
                    "type": event.type,
                    "payload": event.payload,
                }, separators=(",", ":"), ensure_ascii=False))
                fh.write("\n")
        return self

    @classmethod
    def load(cls, path: str) -> "Session":
        rows: list[dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        if not rows:
            raise ValueError("session file is empty")
        header = rows[0]
        if not header.get(SESSION_HEADER_KEY):
            raise ValueError("missing session header")

        log = Log()
        for row in rows[1:]:
            log._events.append(Event(
                seq=row["seq"],
                id=row["id"],
                type=row["type"],
                payload=row["payload"],
            ))
        return cls(id=header["id"], log=log, metadata=header.get("metadata", {}))
