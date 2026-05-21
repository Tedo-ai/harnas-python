from harnas import projection
from harnas.session import Session
import pytest


def test_delegation_projections():
    parent = Session(id="ses_parent")
    spawn = parent.log.append("agent_spawn", {
        "spawn_id": "spn_1",
        "child_session_id": "ses_child",
        "task": "audit",
    })
    parent.log.append("agent_status", {
        "spawn_id": "spn_1",
        "child_session_id": "ses_child",
        "status": "running",
    })
    parent.log.append("agent_result", {
        "spawn_id": "spn_1",
        "child_session_id": "ses_child",
        "status": "succeeded",
        "result": {"text": "done"},
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    })
    child = Session(
        id="ses_child",
        parent_session_id="ses_parent",
        root_session_id="ses_parent",
        spawn_id="spn_1",
        spawned_by_event_id=spawn.id,
        delegation_chain=[{"session_id": "ses_parent", "spawn_id": None}],
    )
    child.log.append("assistant_message", {
        "text": "child done",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 4, "output_tokens": 5},
    })
    runtime = {"ses_parent": parent, "ses_child": child}

    tree = projection.delegation_tree("ses_parent", runtime=runtime)

    assert tree["children"][0]["status"] == "succeeded"
    assert projection.open_children("ses_parent", runtime=runtime) == []
    assert projection.descendant_usage("ses_parent", runtime=runtime) == {
        "prompt_tokens": 5,
        "completion_tokens": 7,
        "total_tokens": 12,
    }


def test_delegation_projection_rejects_broken_child_link():
    parent = Session(id="ses_parent")
    parent.log.append("agent_spawn", {
        "spawn_id": "spn_1",
        "child_session_id": "ses_child",
        "task": "audit",
    })
    child = Session(id="ses_child", parent_session_id="ses_other", spawn_id="spn_1")

    with pytest.raises(ValueError, match="broken delegation link"):
        projection.delegation_tree(
            "ses_parent",
            runtime={"ses_parent": parent, "ses_child": child},
        )


def test_delegation_projection_rejects_duplicate_results():
    parent = Session(id="ses_parent")
    spawn = parent.log.append("agent_spawn", {
        "spawn_id": "spn_1",
        "child_session_id": "ses_child",
        "task": "audit",
    })
    parent.log.append("agent_result", {"spawn_id": "spn_1", "child_session_id": "ses_child"})
    parent.log.append("agent_result", {"spawn_id": "spn_1", "child_session_id": "ses_child"})
    child = Session(
        id="ses_child",
        parent_session_id="ses_parent",
        spawn_id="spn_1",
        spawned_by_event_id=spawn.id,
    )

    with pytest.raises(ValueError, match="multiple agent_result"):
        projection.delegation_tree(
            "ses_parent",
            runtime={"ses_parent": parent, "ses_child": child},
        )


def test_delegation_projection_rejects_cycles():
    a = Session(id="ses_a", parent_session_id="ses_b", spawn_id="spn_b")
    b = Session(id="ses_b", parent_session_id="ses_a", spawn_id="spn_a")
    a.log.append("agent_spawn", {"spawn_id": "spn_a", "child_session_id": "ses_b", "task": "b"})
    b.log.append("agent_spawn", {"spawn_id": "spn_b", "child_session_id": "ses_a", "task": "a"})

    with pytest.raises(ValueError, match="delegation cycle"):
        projection.delegation_tree("ses_a", runtime={"ses_a": a, "ses_b": b})
