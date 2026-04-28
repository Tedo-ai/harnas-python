"""Session — id + Log + metadata bundle."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from .hooks import Hooks
from .log import Log


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
