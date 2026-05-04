"""Conformance fixture runner.

Mirrors `Harnas::Conformance::Runner`. Loads a fixture's manifest,
provider script, inputs, and expected log; runs the AgentLoop
against the scripted provider; diffs the resulting Log against
expected-log.jsonl.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any

from ..agent_loop import AgentLoop
from ..session import Session
from ..tools.registry import Registry
from ..tools.runner import Runner
from ..tools.tool import Tool
from ..observation import DeltaLogger
from .scripted_provider import ScriptedProvider
from .scripted_stream_provider import ScriptedStreamProvider

STRATEGY_CLASSES = {
    "Compaction::MarkerTail": ("..strategies.compaction.marker_tail", "MarkerTail"),
    "Compaction::ToolOutputCap": ("..strategies.compaction.tool_output_cap", "ToolOutputCap"),
    "Permission::DenyByName": ("..strategies.permission.deny_by_name", "DenyByName"),
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
    expected_deltas_path = os.path.join(fixture_dir, "expected-deltas.jsonl")
    expected_strategy_events_path = os.path.join(fixture_dir, "expected-strategy-events.jsonl")

    actual, actual_deltas, actual_strategy_events = _run_agent_with_sidecars(
        manifest,
        script,
        inputs,
        streaming=streaming,
        expected_deltas_path=expected_deltas_path,
        expected_strategy_events_path=expected_strategy_events_path,
    )
    diff = _first_mismatch(actual, expected)
    if diff is None and os.path.exists(expected_deltas_path):
        diff = _first_mismatch(actual_deltas, _load_expected(expected_deltas_path))
    if diff is None and os.path.exists(expected_strategy_events_path):
        diff = _first_mismatch(
            actual_strategy_events,
            _load_expected(expected_strategy_events_path),
        )
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
    return _serialize_log(run_session(manifest, script, inputs, streaming=streaming).log)


def _run_agent_with_sidecars(
    manifest: dict[str, Any],
    script: list,
    inputs: list[str],
    streaming: bool = False,
    expected_deltas_path: str | None = None,
    expected_strategy_events_path: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    needs_deltas = expected_deltas_path and os.path.exists(expected_deltas_path)
    needs_strategy_events = (
        expected_strategy_events_path
        and os.path.exists(expected_strategy_events_path)
    )
    if not needs_deltas and not needs_strategy_events:
        return _run_agent(manifest, script, inputs, streaming=streaming), [], []
    with tempfile.TemporaryDirectory(prefix="harnas-deltas") as tmp:
        delta_path = os.path.join(tmp, "session.deltas.jsonl")
        strategy_events_path = os.path.join(tmp, "session.strategy-events.jsonl")
        session = run_session(
            manifest,
            script,
            inputs,
            streaming=streaming,
            delta_path=delta_path if needs_deltas else None,
            strategy_events_path=strategy_events_path if needs_strategy_events else None,
        )
        return (
            _serialize_log(session.log),
            _load_expected(delta_path) if needs_deltas else [],
            _load_expected(strategy_events_path) if needs_strategy_events else [],
        )


def run_session(
    manifest: dict[str, Any],
    script: list,
    inputs: list[str],
    streaming: bool = False,
    session: Session | None = None,
    delta_path: str | None = None,
    strategy_events_path: str | None = None,
) -> Session:
    registry = _build_registry(manifest.get("tools", []))
    projection, provider, ingestor = _build_pipeline(manifest, script, registry, streaming)
    runner = Runner(registry) if registry.size > 0 else None
    session = session or Session.create(metadata={"manifest_name": manifest["name"]})
    if delta_path is not None:
        DeltaLogger(delta_path, session.observation)
    if strategy_events_path is not None:
        StrategyEventCollector(strategy_events_path, session.observation)

    _install_strategies(session, manifest.get("strategies", []))
    _install_hooks(session, manifest.get("hooks", []))

    for input_item in inputs:
        if isinstance(input_item, dict) and "compact" in input_item:
            compact = input_item["compact"]
            session.log.append(
                type="compact",
                payload={
                    "replaces": compact["replaces"],
                    "summary": compact["summary"],
                },
            )
            continue

        if isinstance(input_item, dict) and "revert" in input_item:
            session.log.append(type="revert", payload={"revokes": input_item["revert"]})
            continue

        if isinstance(input_item, dict) and "fork" in input_item:
            at_seq = input_item["fork"]["at_seq"]
            parent = session
            forked = parent.fork(at_seq=at_seq)
            _verify_fork(parent, forked, at_seq)
            session = forked
            continue

        text = input_item["user"] if isinstance(input_item, dict) else input_item
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

    return session


def _verify_fork(parent: Session, forked: Session, at_seq: int) -> None:
    expected_prefix = _serialize_log(list(parent.log)[: at_seq + 1])
    actual_prefix = _serialize_log(forked.log)
    if actual_prefix != expected_prefix:
        raise RuntimeError("fork prefix mismatch")
    if forked.metadata.get("forked_from") != parent.id:
        raise RuntimeError("forked_from mismatch")
    if forked.metadata.get("forked_at_seq") != at_seq:
        raise RuntimeError("forked_at_seq mismatch")


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
        before = session.hooks.handlers()
        session.install(klass, **config)
        _mark_new_handlers(
            session,
            before,
            name=name,
            on_error=strategy.get("on_error", "isolate"),
            source="strategy",
        )


def _install_hooks(session: Session, hooks_spec: list[dict[str, Any]]) -> None:
    handlers = _conformance_hook_handlers()
    for hook in hooks_spec:
        name = hook["handler"]
        if name not in handlers:
            raise RuntimeError(f"hook handler {name!r} not in hook_handlers")
        handler = handlers[name]

        def invoke(_handler=handler, _config=dict(hook.get("config", {})), **ctx):
            return _handler(**ctx, config=_config)

        session.hooks.on(
            hook["point"].removeprefix(":"),
            invoke,
            name=name,
            on_error=hook.get("on_error", "isolate"),
            source="hook",
        )


def _mark_new_handlers(
    session: Session,
    before: dict[str, list],
    *,
    name: str,
    on_error: str,
    source: str,
) -> None:
    after = session.hooks.handlers()
    for point, handlers in after.items():
        previous = before.get(point, [])
        for handler in handlers:
            if handler not in previous:
                session.hooks.off(point, handler)
                session.hooks.on(
                    point,
                    handler,
                    name=name,
                    on_error=on_error,
                    source=source,
                )


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
    output (spec/conformance/README.md): canonical compact JSON for
    the args.
    """
    def stub(args: dict[str, Any]) -> str:
        if handler_name == "conformance.raise_error":
            raise RuntimeError("conformance tool error")
        encoded = json.dumps(args, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        return f"[conformance stub: {handler_name}({encoded})]"
    return stub


def _conformance_hook_handlers():
    def audit_post_tool_use(*, session, tool_use, tool_result, **_):
        session.log.append(
            type="annotation",
            payload={
                "kind": "conformance.hook",
                "data": {
                    "tool_use_id": tool_use.payload["id"],
                    "result_seq": tool_result.seq,
                },
            },
        )

    def raise_hook(**_):
        raise RuntimeError("conformance hook failure")

    return {
        "conformance.audit_post_tool_use": audit_post_tool_use,
        "conformance.raise_hook": raise_hook,
    }


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


class StrategyEventCollector:
    def __init__(self, path: str, observation) -> None:
        self.path = path
        self.index = 0
        observation.subscribe(self)

    def __call__(self, event_name: str, payload: dict[str, Any]) -> None:
        if event_name not in {"strategy_started", "strategy_completed"}:
            return
        with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({
                "index": self.index,
                "event": event_name,
                "payload": _normalize(payload),
            }, separators=(",", ":"), ensure_ascii=False))
            fh.write("\n")
        self.index += 1
