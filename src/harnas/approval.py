"""Async human-in-the-loop approval (spec 07-permission R7-R11).

A run that ended with the ``awaiting_approval`` outcome left one or more
tool_use Events un-executed, each marked by an ``approval_requested`` Event.
Resolve them here BEFORE re-entering ``AgentLoop.run`` so the next provider
call sees a valid assistant -> tool_result pairing.
"""

from __future__ import annotations


def request_approval(reason: str | None = None, requested_by: str | None = None) -> dict:
    """Canonical RequestApproval action (spec 16-actions): the third
    pre_tool_use decision shape. Composition per tool_use is
    Refuse > RequestApproval > Allow."""
    return {"pending_approval": True, "reason": reason, "requested_by": requested_by}


def approve(*, session, runner, tool_use_id: str, resolved_by: str | None = None,
            reason: str | None = None) -> None:
    """Approve: append approval_resolved, then execute exactly that tool_use
    exactly once via the Runner — bypassing pre_tool_use, the decision was
    resolved by the host — and append its ordinary tool_result."""
    if runner is None:
        raise ValueError("approve requires a runner")
    tool_use = _unresolved_tool_use(session, tool_use_id)
    _append_resolution(session, tool_use_id, "approved", reason=reason, resolved_by=resolved_by)
    runner.run(tool_use, into_log=session.log, session=session)


def deny(*, session, tool_use_id: str, reason: str, resolved_by: str | None = None) -> None:
    """Deny: append approval_resolved followed by the synthesized rejection
    tool_result carrying the approval envelope."""
    _unresolved_tool_use(session, tool_use_id)
    _append_resolution(session, tool_use_id, "denied", reason=reason, resolved_by=resolved_by)
    session.log.append(
        type="tool_result",
        payload={
            "tool_use_id": tool_use_id,
            "output": None,
            "error": f"denied by approval: {reason}",
            "approval": {
                "decision": "rejected",
                "rule_matched": reason,
                "applied_diff": None,
            },
        },
    )


def _unresolved_tool_use(session, tool_use_id: str):
    tool_use = None
    for event in session.log:
        payload = event.payload
        if event.type == "tool_use" and payload.get("id") == tool_use_id:
            tool_use = event
        if event.type == "tool_result" and payload.get("tool_use_id") == tool_use_id:
            raise ValueError(
                f"tool_use {tool_use_id!r} already has a tool_result; "
                "approvals resolve exactly once"
            )
    if tool_use is None:
        raise ValueError(f"no tool_use with id {tool_use_id!r} in the session log")
    return tool_use


def _append_resolution(session, tool_use_id: str, decision: str, *,
                       reason: str | None, resolved_by: str | None) -> None:
    session.log.append(
        type="approval_resolved",
        payload={
            "tool_use_id": tool_use_id,
            "decision": decision,
            "reason": reason,
            "resolved_by": resolved_by,
        },
    )
