"""Conformance fixture runner.

Mirrors `Harnas::Conformance::Runner`. Loads a fixture's manifest,
provider script, inputs, and expected log; runs the AgentLoop
against the scripted provider; diffs the resulting Log against
expected-log.jsonl.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from ..agent_loop import AgentLoop
from ..session import Session
from ..tools.registry import Registry
from ..tools.runner import Runner
from ..tools.tool import Tool
from .scripted_provider import ScriptedProvider
from .scripted_stream_provider import ScriptedStreamProvider

STRATEGY_CLASSES = {
    "Compaction::MarkerTail": ("..strategies.compaction.marker_tail", "MarkerTail"),
}


@dataclass
class Result:
    fixture: str
    passed: bool
    actual: list[dict[str, Any]]
    expected: list[dict[str, Any]]
    diff: dict[str, Any] | None

    def summary(self) -> str:
        if self.passed:
            return f"{self.fixture}  ok ({len(self.actual)} events)"
        return f"{self.fixture}  FAIL at seq {self.diff['at_seq']}"


def run(fixture_dir: str) -> Result:
    manifest = json.loads(_read(os.path.join(fixture_dir, "manifest.json")))
    script, streaming = _load_provider_script(fixture_dir)
    inputs = json.loads(_read(os.path.join(fixture_dir, "inputs.json")))
    expected = _load_expected(os.path.join(fixture_dir, "expected-log.jsonl"))

    actual = _run_agent(manifest, script, inputs, streaming=streaming)
    diff = _first_mismatch(actual, expected)
    return Result(
        fixture=os.path.basename(fixture_dir.rstrip("/")),
        passed=diff is None,
        actual=actual,
        expected=expected,
        diff=diff,
    )


def _run_agent(
    manifest: dict[str, Any],
    script: list,
    inputs: list[str],
    streaming: bool = False,
) -> list[dict[str, Any]]:
    registry = _build_registry(manifest.get("tools", []))
    projection, provider, ingestor = _build_pipeline(manifest, script, registry, streaming)
    runner = Runner(registry) if registry.size > 0 else None
    session = Session.create(metadata={"manifest_name": manifest["name"]})

    _install_strategies(session, manifest.get("strategies", []))

    for text in inputs:
        session.log.append(type="user_message", payload={"text": text})
        AgentLoop(
            session=session,
            projection=projection,
            provider=provider,
            ingestor=ingestor,
            stream_provider=provider if streaming else None,
            runner=runner,
            max_turns=3,
        ).run()

    return _serialize_log(session.log)


def _load_provider_script(fixture_dir: str) -> tuple[list, bool]:
    stream_path = os.path.join(fixture_dir, "provider-script-stream.json")
    if os.path.exists(stream_path):
        return json.loads(_read(stream_path)), True
    return json.loads(_read(os.path.join(fixture_dir, "provider-script.json"))), False


def _install_strategies(session: Session, strategies_spec: list[dict[str, Any]]) -> None:
    import importlib
    for strategy in strategies_spec:
        name = strategy["name"]
        if name not in STRATEGY_CLASSES:
            raise NotImplementedError(f"strategy '{name}' not yet implemented in the Python port")
        module_path, class_name = STRATEGY_CLASSES[name]
        module = importlib.import_module(module_path, package="harnas.conformance")
        klass = getattr(module, class_name)
        config = strategy.get("config", {})
        session.install(klass, **config)


def _build_pipeline(
    manifest: dict[str, Any],
    script: list,
    registry: Registry,
    streaming: bool = False,
):
    """Map manifest provider.kind -> projection + ingestor classes."""
    kind = manifest["provider"]["kind"]
    model = manifest["provider"].get("model", "test")
    max_tokens = manifest["provider"].get("max_tokens", 1024)
    system = manifest.get("system")

    if kind in ("anthropic", "mock"):
        from ..projections.anthropic import Anthropic as AnthropicProjection
        from ..ingestors.anthropic import Anthropic as AnthropicIngestor
        projection = AnthropicProjection(
            model=model, max_tokens=max_tokens, system=system, registry=registry
        )
        ingestor = AnthropicIngestor()
    elif kind == "openai":
        from ..projections.openai import OpenAI as OpenAIProjection
        from ..ingestors.openai import OpenAI as OpenAIIngestor
        projection = OpenAIProjection(model=model, system=system, registry=registry)
        ingestor = OpenAIIngestor()
    elif kind == "gemini":
        from ..projections.gemini import Gemini as GeminiProjection
        from ..ingestors.gemini import Gemini as GeminiIngestor
        projection = GeminiProjection(model=model, system=system, registry=registry)
        ingestor = GeminiIngestor()
    else:
        raise NotImplementedError(f"provider kind '{kind}' not yet implemented in the Python port")

    provider = ScriptedStreamProvider(script) if streaming else ScriptedProvider(script)
    return projection, provider, ingestor


def _build_registry(tools_spec: list[dict[str, Any]]) -> Registry:
    registry = Registry()
    for tool_def in tools_spec:
        handler_name = tool_def["handler"]
        registry.register(Tool(
            name=tool_def["name"],
            description=tool_def["description"],
            input_schema=tool_def["input_schema"],
            handler=_conformance_stub_handler(handler_name),
        ))
    return registry


def _conformance_stub_handler(handler_name: str):
    """Returns a callable producing the normative conformance-stub
    output (spec/conformance/README.md): compact JSON for the args.
    """
    def stub(args: dict[str, Any]) -> str:
        return f"[conformance stub: {handler_name}({json.dumps(args, separators=(',', ':'))})]"
    return stub


def _load_expected(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(_normalize(json.loads(line)))
    return rows


def _serialize_log(log) -> list[dict[str, Any]]:
    return [_normalize({"seq": e.seq, "type": e.type, "payload": e.payload}) for e in log]


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def _first_mismatch(actual: list, expected: list) -> dict[str, Any] | None:
    upper = max(len(actual), len(expected))
    for i in range(upper):
        a = actual[i] if i < len(actual) else None
        e = expected[i] if i < len(expected) else None
        if a != e:
            return {"at_seq": i, "actual": a, "expected": e}
    return None


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()
