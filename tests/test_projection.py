from harnas import projection
from harnas.session import Session


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
