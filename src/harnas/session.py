"""Session — id + Log + metadata bundle."""

from __future__ import annotations

import uuid
import json
from dataclasses import dataclass, field
from typing import Any

from .hooks import Hooks
from .log import Log
from .event import Event
from .observation import Observation

SESSION_HEADER_KEY = "__session__"


@dataclass
class Session:
    """Bundles a stable id with one Log and optional metadata.

    Mirrors `Harnas::Session`.
    """

    id: str
    log: Log = field(default_factory=Log)
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_session_id: str | None = None
    root_session_id: str | None = None
    spawn_id: str | None = None
    spawned_by_event_id: str | None = None
    delegation_chain: list[dict[str, Any]] = field(default_factory=list)
    hooks: Hooks = field(default_factory=Hooks)
    observation: Observation = field(default_factory=Observation)

    def __post_init__(self) -> None:
        self.log.observation = self.observation

    @classmethod
    def create(
        cls,
        metadata: dict[str, Any] | None = None,
        *,
        parent_session_id: str | None = None,
        root_session_id: str | None = None,
        spawn_id: str | None = None,
        spawned_by_event_id: str | None = None,
        delegation_chain: list[dict[str, Any]] | None = None,
    ) -> "Session":
        observation = Observation()
        return cls(
            id=f"ses_{uuid.uuid4()}",
            log=Log(observation=observation),
            metadata=metadata or {},
            parent_session_id=parent_session_id,
            root_session_id=root_session_id,
            spawn_id=spawn_id,
            spawned_by_event_id=spawned_by_event_id,
            delegation_chain=delegation_chain or [],
            observation=observation,
        )

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
        },
            parent_session_id=self.parent_session_id,
            root_session_id=self.root_session_id,
            spawn_id=self.spawn_id,
            spawned_by_event_id=self.spawned_by_event_id,
            delegation_chain=[dict(item) for item in self.delegation_chain],
        )
        for event in list(self.log)[: at_seq + 1]:
            forked.log._events.append(event)
        return forked

    def save(self, path: str) -> "Session":
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            header = {
                SESSION_HEADER_KEY: True,
                "id": self.id,
                "metadata": self.metadata,
            }
            if self.parent_session_id is not None:
                header["parent_session_id"] = self.parent_session_id
            if self.root_session_id is not None:
                header["root_session_id"] = self.root_session_id
            if self.spawn_id is not None:
                header["spawn_id"] = self.spawn_id
            if self.spawned_by_event_id is not None:
                header["spawned_by_event_id"] = self.spawned_by_event_id
            if self.delegation_chain:
                header["delegation_chain"] = self.delegation_chain
            fh.write(json.dumps(header, separators=(",", ":"), ensure_ascii=False))
            fh.write("\n")
            for event in self.log:
                fh.write(json.dumps({
                    "seq": event.seq,
                    "id": event.id,
                    "timestamp": event.timestamp,
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

        observation = Observation()
        log = Log(observation=observation)
        for row in rows[1:]:
            log._events.append(Event(
                seq=row["seq"],
                id=row["id"],
                type=row["type"],
                payload=row["payload"],
                timestamp=row.get("timestamp"),
            ))
        return cls(
            id=header["id"],
            log=log,
            metadata=header.get("metadata", {}),
            parent_session_id=header.get("parent_session_id"),
            root_session_id=header.get("root_session_id"),
            spawn_id=header.get("spawn_id"),
            spawned_by_event_id=header.get("spawned_by_event_id"),
            delegation_chain=header.get("delegation_chain") or [],
            observation=observation,
        )
