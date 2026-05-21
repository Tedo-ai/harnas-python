"""Cross-session projection helpers for delegated agent sessions."""

from __future__ import annotations

from typing import Any, Protocol

from .session import Session


class SessionResolver(Protocol):
    def load_session(self, session_id: str) -> Session: ...


def delegation_tree(session_id: str, *, runtime: Any) -> dict[str, Any]:
    return _build_tree(session_id, runtime, set())


def open_children(session_id: str, *, runtime: Any) -> list[str]:
    session = _load_session(session_id, runtime)
    open_spawn_ids: list[str] = []
    for spawn in _agent_spawns(session):
        _validate_child_link(session, spawn, runtime)
        spawn_id = spawn.payload["spawn_id"]
        if _agent_result_for_spawn(session, spawn_id) is None:
            open_spawn_ids.append(spawn_id)
    return open_spawn_ids


def descendant_timeline(session_id: str, *, runtime: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for session in _collect_descendants(session_id, runtime, set()):
        for event in session.log:
            rows.append({
                "session_id": session.id,
                "seq": event.seq,
                "id": event.id,
                "type": event.type,
                "payload": event.payload,
                "timestamp": str(event.payload.get("timestamp", "")),
            })
    return sorted(rows, key=lambda row: (row["timestamp"], row["session_id"], row["seq"]))


def descendant_usage(session_id: str, *, runtime: Any) -> dict[str, int]:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for session in _collect_descendants(session_id, runtime, set()):
        for event in session.log:
            if event.type in {"assistant_message", "agent_result"}:
                _add_usage(totals, event.payload.get("usage") or {})
    return totals


def _build_tree(session_id: str, runtime: Any, visiting: set[str]) -> dict[str, Any]:
    if session_id in visiting:
        raise ValueError(f"delegation cycle detected at {session_id}")
    visiting.add(session_id)
    session = _load_session(session_id, runtime)
    children = []
    for spawn in _agent_spawns(session):
        _validate_child_link(session, spawn, runtime)
        child = _build_tree(spawn.payload["child_session_id"], runtime, visiting)
        result = _agent_result_for_spawn(session, spawn.payload["spawn_id"])
        status_event = _last_status_for_spawn(session, spawn.payload["spawn_id"])
        status = (
            result.payload.get("status") if result is not None else None
        ) or (
            status_event.payload.get("status") if status_event is not None else None
        ) or "open"
        children.append({
            "spawn_id": spawn.payload["spawn_id"],
            "child_session_id": spawn.payload["child_session_id"],
            "task": spawn.payload.get("task"),
            "join_policy": spawn.payload.get("join_policy", "async"),
            "metadata": spawn.payload.get("metadata", {}),
            "status": status,
            "result": result.payload.get("result") if result is not None else None,
            "error": result.payload.get("error") if result is not None else None,
            "children": child["children"],
        })
    visiting.remove(session_id)
    return {"session_id": session.id, "children": children}


def _collect_descendants(session_id: str, runtime: Any, visiting: set[str]) -> list[Session]:
    if session_id in visiting:
        raise ValueError(f"delegation cycle detected at {session_id}")
    visiting.add(session_id)
    session = _load_session(session_id, runtime)
    sessions = [session]
    for spawn in _agent_spawns(session):
        _validate_child_link(session, spawn, runtime)
        sessions.extend(_collect_descendants(spawn.payload["child_session_id"], runtime, visiting))
    visiting.remove(session_id)
    return sessions


def _load_session(session_id: str, runtime: Any) -> Session:
    if isinstance(runtime, dict):
        return runtime[session_id]
    return runtime.load_session(session_id)


def _agent_spawns(session: Session):
    return [event for event in session.log if event.type == "agent_spawn"]


def _validate_child_link(parent: Session, spawn: Any, runtime: Any) -> None:
    child = _load_session(spawn.payload["child_session_id"], runtime)
    if child.parent_session_id == parent.id and child.spawn_id == spawn.payload["spawn_id"]:
        return
    raise ValueError(
        f"broken delegation link parent={parent.id} spawn={spawn.payload['spawn_id']}"
    )


def _agent_result_for_spawn(session: Session, spawn_id: str):
    results = [
        event for event in session.log
        if event.type == "agent_result" and event.payload.get("spawn_id") == spawn_id
    ]
    if len(results) > 1:
        raise ValueError(f"multiple agent_result events for spawn_id {spawn_id}")
    return results[0] if results else None


def _last_status_for_spawn(session: Session, spawn_id: str):
    statuses = [
        event for event in session.log
        if event.type == "agent_status" and event.payload.get("spawn_id") == spawn_id
    ]
    return statuses[-1] if statuses else None


def _add_usage(totals: dict[str, int], usage: dict[str, Any]) -> None:
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total = int(usage.get("total_tokens") or prompt + completion)
    totals["prompt_tokens"] += prompt
    totals["completion_tokens"] += completion
    totals["total_tokens"] += total
