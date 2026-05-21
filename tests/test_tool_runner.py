import json

from harnas.log import Log
from harnas.tools.registry import Registry
from harnas.tools.runner import Runner
from harnas.tools.tool import Tool


def test_spawn_agent_appends_spawn_receipt():
    registry = Registry()
    registry.register(
        Tool(
            name="spawn_agent",
            description="spawn",
            input_schema={},
            handler=lambda _args: "unreachable",
            handler_name="harnas.builtin.spawn_agent",
        )
    )
    log = Log()
    tool_use = log.append(
        "tool_use",
        {
            "id": "call_spawn",
            "name": "spawn_agent",
            "arguments": {
                "task": "Audit this",
                "label": "Explorer",
                "role": "explorer",
            },
        },
    )

    Runner(registry).run(tool_use, into_log=log)

    assert log[1].type == "agent_spawn"
    assert log[1].payload["task"] == "Audit this"
    assert log[1].payload["spawned_by_event_id"] == tool_use.id
    assert log[2].type == "tool_result"
    output = json.loads(log[2].payload["output"])
    assert output["spawn_id"] == log[1].payload["spawn_id"]
