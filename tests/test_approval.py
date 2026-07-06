"""Async approval primitive (spec 07-permission R7-R11)."""

import pytest

from harnas import approval
from harnas.session import Session
from harnas.tools.registry import Registry
from harnas.tools.runner import Runner
from harnas.tools.tool import Tool


def _session_with_tool_use(tool_use_id="toolu_t1"):
    session = Session.create()
    session.log.append(
        type="tool_use",
        payload={"id": tool_use_id, "name": "get_current_time", "arguments": {}},
    )
    registry = Registry()
    registry.register(
        Tool(
            name="get_current_time",
            description="time",
            input_schema={"type": "object", "properties": {}},
            handler=lambda args: "12:00",
        )
    )
    return session, Runner(registry)


def test_approve_appends_resolution_then_executes_exactly_once():
    session, runner = _session_with_tool_use()
    approval.approve(session=session, runner=runner, tool_use_id="toolu_t1", resolved_by="tester")

    events = list(session.log)
    assert events[-2].type == "approval_resolved"
    assert events[-2].payload["decision"] == "approved"
    assert events[-2].payload["resolved_by"] == "tester"
    assert events[-1].type == "tool_result"
    assert events[-1].payload["output"] == "12:00"

    with pytest.raises(ValueError, match="exactly once"):
        approval.approve(session=session, runner=runner, tool_use_id="toolu_t1")


def test_deny_synthesizes_rejection_with_envelope():
    session, _runner = _session_with_tool_use()
    approval.deny(session=session, tool_use_id="toolu_t1", reason="operator said no",
                  resolved_by="tester")

    events = list(session.log)
    assert events[-2].payload["decision"] == "denied"
    assert events[-1].payload["error"] == "denied by approval: operator said no"
    assert events[-1].payload["approval"]["decision"] == "rejected"
    assert events[-1].payload["approval"]["rule_matched"] == "operator said no"


def test_unknown_tool_use_errors():
    session, runner = _session_with_tool_use()
    with pytest.raises(ValueError, match="no tool_use"):
        approval.approve(session=session, runner=runner, tool_use_id="missing")
