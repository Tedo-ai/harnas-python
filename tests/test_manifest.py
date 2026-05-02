import json

import pytest

from harnas import manifest
from harnas.agent import Agent


def basic_manifest(**overrides):
    data = {
        "harnas_version": "0.1",
        "name": "py-loader",
        "provider": {"kind": "mock", "model": "mock-test", "max_tokens": 128},
        "tools": [],
        "strategies": [],
    }
    data.update(overrides)
    return data


def test_load_manifest_builds_runtime_bundle(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(basic_manifest(
        system="You are terse.",
        tools=[{
            "name": "echo",
            "handler": "test.echo",
            "description": "Echo text.",
            "input_schema": {"type": "object"},
        }],
    )), encoding="utf-8")

    loaded = manifest.load(path, tool_handlers={"test.echo": lambda args: args["text"]})

    assert loaded.name == "py-loader"
    assert loaded.session.metadata["manifest_name"] == "py-loader"
    assert loaded.registry.size == 1
    assert loaded.projection(loaded.session.log)["system"] == "You are terse."


def test_agent_from_manifest_runs_mock_provider(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(basic_manifest()), encoding="utf-8")

    agent = Agent.from_manifest(str(path))
    response = agent.chat("hello")

    assert response.text == "ok"
    assert [event.type for event in agent.log] == ["user_message", "assistant_message"]


@pytest.mark.parametrize(
    "payload,error_type",
    [
        ({"name": "missing"}, manifest.ValidationError),
        (basic_manifest(harnas_version="9.9"), manifest.UnsupportedVersionError),
        (basic_manifest(provider={"kind": "fiction", "max_tokens": 1}), manifest.UnknownProviderError),
        (basic_manifest(system=""), manifest.ValidationError),
        (basic_manifest(extra=True), manifest.ValidationError),
    ],
)
def test_manifest_validation_errors(payload, error_type):
    with pytest.raises(error_type):
        manifest.load(payload)


def test_load_manifest_rejects_unresolved_tool_handler():
    payload = basic_manifest(tools=[{
        "name": "echo",
        "handler": "missing.echo",
        "description": "Echo text.",
        "input_schema": {"type": "object"},
    }])

    with pytest.raises(manifest.UnresolvedHandlerError):
        manifest.load(payload)
