from harnas.tools.registry import Registry
from harnas.tools.tool import Tool
from harnas.tools import snapshot


def test_descriptors_export_registry_tools_with_config():
    registry = Registry()
    registry.register(Tool(
        name="load_skill",
        handler_name="harnas.builtin.load_skill",
        description="Load a skill",
        input_schema={"type": "object"},
        config={"skills_dir": "/tmp/skills"},
        handler=lambda _args: "ok",
    ))

    assert snapshot.descriptors(registry) == [{
        "name": "load_skill",
        "handler": "harnas.builtin.load_skill",
        "description": "Load a skill",
        "input_schema": {"type": "object"},
        "config": {"skills_dir": "/tmp/skills"},
    }]
