"""Storage adapter seam and law-facing default adapters."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .event import Event

STORAGE_CONFLICT = "storage_conflict"


@dataclass(frozen=True)
class SessionHeader:
    id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_session_id: str | None = None
    root_session_id: str | None = None
    spawn_id: str | None = None
    spawned_by_event_id: str | None = None
    delegation_chain: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class EventDraft:
    id: str
    timestamp: str
    type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EventRow:
    seq: int
    id: str
    timestamp: str | None
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    content_hash: str | None = None


class StorageConflictError(RuntimeError):
    def __init__(self, *, expected_next_seq: int, current_next_seq: int) -> None:
        self.reason = STORAGE_CONFLICT
        self.current_next_seq = current_next_seq
        super().__init__(f"{STORAGE_CONFLICT}: expected next seq {expected_next_seq}, current next seq {current_next_seq}")


class MemoryStorageAdapter:
    def __init__(self, header: SessionHeader | None = None, events: list[EventRow] | None = None) -> None:
        self._header = header
        self._events = list(events or [])

    def load_session(self) -> SessionHeader | None:
        return copy.deepcopy(self._header)

    def save_header(self, header: SessionHeader) -> None:
        self._header = copy.deepcopy(header)

    def append_event(self, draft: EventDraft, *, expected_next_seq: int | None = None) -> EventRow:
        self._check_expected(expected_next_seq)
        row = EventRow(
            seq=len(self._events),
            id=draft.id,
            timestamp=draft.timestamp,
            type=draft.type,
            payload=copy.deepcopy(draft.payload),
        )
        self._events.append(row)
        return copy.deepcopy(row)

    def events_since(self, cursor: int | None) -> list[EventRow]:
        start = 0 if cursor is None else cursor + 1
        return copy.deepcopy(self._events[start:])

    def _check_expected(self, expected_next_seq: int | None) -> None:
        if expected_next_seq is not None and expected_next_seq != len(self._events):
            raise StorageConflictError(expected_next_seq=expected_next_seq, current_next_seq=len(self._events))


class FileStorageAdapter:
    def __init__(self, path: str | Path, header: SessionHeader | None = None) -> None:
        self.path = Path(path)
        self.initial_header = header

    def load_session(self) -> SessionHeader | None:
        if not self._readable():
            return self.initial_header
        header, _ = self._read_all()
        return header

    def save_header(self, header: SessionHeader) -> None:
        _, rows = self._read_all() if self._readable() else (None, [])
        self._write_all(header, rows)

    def append_event(self, draft: EventDraft, *, expected_next_seq: int | None = None) -> EventRow:
        header, rows = self._read_all() if self._readable() else (self.initial_header, [])
        if expected_next_seq is not None and expected_next_seq != len(rows):
            raise StorageConflictError(expected_next_seq=expected_next_seq, current_next_seq=len(rows))
        row = EventRow(
            seq=len(rows),
            id=draft.id,
            timestamp=draft.timestamp,
            type=draft.type,
            payload=copy.deepcopy(draft.payload),
        )
        self._write_all(header, [*rows, row])
        return row

    def events_since(self, cursor: int | None) -> list[EventRow]:
        if not self._readable():
            return []
        _, rows = self._read_all()
        start = 0 if cursor is None else cursor + 1
        return rows[start:]

    def _readable(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def _read_all(self) -> tuple[SessionHeader, list[EventRow]]:
        rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not rows:
            raise ValueError("session file is empty")
        if not rows[0].get("__session__"):
            raise ValueError("missing session header")
        return self._header_from_dict(rows[0]), [self._row_from_dict(row, idx) for idx, row in enumerate(rows[1:])]

    def _write_all(self, header: SessionHeader | None, rows: list[EventRow]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        if header is not None:
            lines.append(json.dumps(self._header_to_dict(header), separators=(",", ":"), ensure_ascii=False))
        lines.extend(json.dumps(self._row_to_dict(row), separators=(",", ":"), ensure_ascii=False) for row in rows)
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _header_from_dict(self, row: dict[str, Any]) -> SessionHeader:
        return SessionHeader(
            id=row["id"],
            metadata=row.get("metadata", {}),
            parent_session_id=row.get("parent_session_id"),
            root_session_id=row.get("root_session_id"),
            spawn_id=row.get("spawn_id"),
            spawned_by_event_id=row.get("spawned_by_event_id"),
            delegation_chain=row.get("delegation_chain") or [],
        )

    def _row_from_dict(self, row: dict[str, Any], expected_seq: int) -> EventRow:
        if row["seq"] != expected_seq:
            raise ValueError(f"invalid event seq at row {expected_seq}: got {row['seq']}, want {expected_seq}")
        return EventRow(
            seq=row["seq"],
            id=row["id"],
            timestamp=row.get("timestamp"),
            type=row["type"],
            payload=row.get("payload", {}),
            content_hash=row.get("content_hash"),
        )

    def _header_to_dict(self, header: SessionHeader) -> dict[str, Any]:
        out: dict[str, Any] = {"__session__": True, "id": header.id, "metadata": header.metadata}
        for key in ("parent_session_id", "root_session_id", "spawn_id", "spawned_by_event_id"):
            value = getattr(header, key)
            if value is not None:
                out[key] = value
        if header.delegation_chain:
            out["delegation_chain"] = header.delegation_chain
        return out

    def _row_to_dict(self, row: EventRow) -> dict[str, Any]:
        out: dict[str, Any] = {
            "seq": row.seq,
            "id": row.id,
            "timestamp": row.timestamp,
            "type": row.type,
            "payload": row.payload,
        }
        if row.content_hash is not None:
            out["content_hash"] = row.content_hash
        return out


def event_row_from_event(event: Event) -> EventRow:
    return EventRow(seq=event.seq, id=event.id, timestamp=event.timestamp, type=event.type, payload=event.payload)
