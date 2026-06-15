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
import copy
from dataclasses import dataclass
from typing import Any

from ..agent_loop import AgentLoop
from ..attachments import MemoryStore
from ..manifest import _effective_tool_config
from ..session import Session
from ..tools.registry import Registry
from ..tools.runner import Runner
from ..tools.snapshot import descriptors as tool_descriptors
from ..tools.tool import Tool
from ..observation import DeltaLogger
from .. import projection
from .scripted_provider import ScriptedProvider
from .scripted_stream_provider import ScriptedStreamProvider

STRATEGY_CLASSES = {
    "Compaction::MarkerTail": ("..strategies.compaction.marker_tail", "MarkerTail"),
    "Compaction::ToolOutputCap": ("..strategies.compaction.tool_output_cap", "ToolOutputCap"),
    "Permission::DenyByName": ("..strategies.permission.deny_by_name", "DenyByName"),
    "sandbox/write": ("..strategies.sandbox.write", "Write"),
    "sandbox/network": ("..strategies.sandbox.network", "Network"),
    "credential/proxy": ("..strategies.credential.proxy", "Proxy"),
    "guard/repetition": ("..strategies.guard.repetition", "Repetition"),
    "guard/timeout": ("..strategies.guard.timeout", "Timeout"),
    "guard/health": ("..strategies.guard.health", "Health"),
    "guard/cost_budget": ("..strategies.guard.cost_budget", "CostBudget"),
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
    if os.path.exists(os.path.join(fixture_dir, "expected-projections.jsonl")):
        return _run_projection_fixture(fixture_dir)

    manifest = json.loads(_read(os.path.join(fixture_dir, "manifest.json")))
    manifest.pop("fixture_version_added", None)
    manifest = _resolve_fixture_paths(manifest, fixture_dir)
    script, streaming = _load_provider_script(fixture_dir)
    inputs = json.loads(_read(os.path.join(fixture_dir, "inputs.json")))
    expected = _load_expected(os.path.join(fixture_dir, "expected-log.jsonl"))
    expected_deltas_path = os.path.join(fixture_dir, "expected-deltas.jsonl")
    expected_strategy_events_path = os.path.join(fixture_dir, "expected-strategy-events.jsonl")
    expected_spawn_children_path = os.path.join(fixture_dir, "expected-spawn-children.json")
    expected_tool_descriptors_path = os.path.join(fixture_dir, "expected-tool-descriptors.json")

    cwd = os.getcwd()
    try:
        os.chdir(fixture_dir)
        actual, actual_deltas, actual_strategy_events, actual_tool_descriptors = _run_agent_with_sidecars(
            manifest,
            script,
            inputs,
            streaming=streaming,
            expected_deltas_path=expected_deltas_path,
            expected_strategy_events_path=expected_strategy_events_path,
            expected_spawn_children_path=expected_spawn_children_path,
        )
    finally:
        os.chdir(cwd)
    diff = _first_mismatch(actual, expected)
    if diff is None and os.path.exists(expected_deltas_path):
        diff = _first_mismatch(actual_deltas, _load_expected(expected_deltas_path))
    if diff is None and os.path.exists(expected_strategy_events_path):
        diff = _first_mismatch(
            actual_strategy_events,
            _load_expected(expected_strategy_events_path),
        )
    if diff is None and os.path.exists(expected_tool_descriptors_path):
        diff = _first_mismatch(
            actual_tool_descriptors,
            json.loads(_read(expected_tool_descriptors_path)),
        )
    if diff is None:
        diff = _credential_proxy_secret_diff(actual, fixture_dir)
    if diff is None:
        diff = _isolation_repeat_diff(
            fixture_dir,
            manifest,
            script,
            inputs,
            streaming,
            expected,
        )
    return Result(
        fixture=os.path.basename(fixture_dir.rstrip("/")),
        passed=diff is None,
        actual=actual,
        expected=expected,
        diff=diff,
    )


def _isolation_repeat_diff(
    fixture_dir: str,
    manifest: dict[str, Any],
    script: list,
    inputs: list,
    streaming: bool,
    expected: list[dict[str, Any]],
) -> dict[str, Any] | None:
    path = os.path.join(fixture_dir, "isolation.json")
    if not os.path.exists(path):
        return None
    repeat = int(json.loads(_read(path)).get("repeat", 1))
    if repeat < 2:
        return None
    cwd = os.getcwd()
    try:
        os.chdir(fixture_dir)
        for index in range(1, repeat):
            actual, _actual_deltas, _actual_strategy_events, _actual_tool_descriptors = _run_agent_with_sidecars(
                manifest,
                script,
                inputs,
                streaming=streaming,
            )
            diff = _first_mismatch(actual, expected)
            if diff is not None:
                return {
                    "at_seq": f"repeat {index + 1}",
                    "actual": diff,
                    "expected": None,
                }
    finally:
        os.chdir(cwd)
    return None


def _run_projection_fixture(fixture_dir: str) -> Result:
    sessions, root = _load_fixture_sessions(os.path.join(fixture_dir, "sessions"))
    expected = _load_expected(os.path.join(fixture_dir, "expected-log.jsonl"))
    actual = _serialize_log(root.log)
    diff = _first_mismatch(actual, expected)
    if diff is None:
        diff = _first_projection_mismatch(
            _load_expected(os.path.join(fixture_dir, "expected-projections.jsonl")),
            sessions,
        )
    return Result(
        fixture=os.path.basename(fixture_dir.rstrip("/")),
        passed=diff is None,
        actual=actual,
        expected=expected,
        diff=diff,
    )


def _load_fixture_sessions(dir_path: str) -> tuple[dict[str, Session], Session]:
    sessions: dict[str, Session] = {}
    root: Session | None = None
    for name in sorted(os.listdir(dir_path)):
        if not name.endswith(".jsonl"):
            continue
        session = Session.load(os.path.join(dir_path, name))
        sessions[session.id] = session
        if session.parent_session_id is None:
            if root is not None:
                raise ValueError(f"multiple root sessions in {dir_path}")
            root = session
    if root is None:
        raise ValueError(f"no root session in {dir_path}")
    return sessions, root


def _first_projection_mismatch(
    rows: list[dict[str, Any]],
    sessions: dict[str, Session],
) -> dict[str, Any] | None:
    for index, row in enumerate(rows):
        actual = _evaluate_projection(row["projection"], row["input"], sessions)
        expected = row["output"]
        if _normalize(actual) == _normalize(expected):
            continue
        return {"at_seq": f"projection {index}", "actual": actual, "expected": expected}
    return None


def _evaluate_projection(name: str, input_session_id: str, sessions: dict[str, Session]) -> Any:
    if name == "delegation_tree":
        return projection.delegation_tree(input_session_id, runtime=sessions)
    if name == "open_children":
        return projection.open_children(input_session_id, runtime=sessions)
    if name == "descendant_timeline":
        return projection.descendant_timeline(input_session_id, runtime=sessions)
    if name == "descendant_usage":
        return projection.descendant_usage(input_session_id, runtime=sessions)
    raise ValueError(f"unknown projection {name!r}")


def fixture_version(spec_root: str) -> str | None:
    path = os.path.join(spec_root, "VERSION")
    if not os.path.isfile(path):
        return None
    for line in _read(path).splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "fixtures_version":
            return value.strip()
    return None


def _run_agent(
    manifest: dict[str, Any],
    script: list,
    inputs: list[str],
    streaming: bool = False,
    attachment_store: Any | None = None,
) -> list[dict[str, Any]]:
    return _serialize_log(
        run_session(
            manifest, script, inputs, streaming=streaming, attachment_store=attachment_store
        ).log
    )


def _run_agent_with_sidecars(
    manifest: dict[str, Any],
    script: list,
    inputs: list[str],
    streaming: bool = False,
    expected_deltas_path: str | None = None,
    expected_strategy_events_path: str | None = None,
    expected_spawn_children_path: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    needs_deltas = expected_deltas_path and os.path.exists(expected_deltas_path)
    needs_strategy_events = (
        expected_strategy_events_path
        and os.path.exists(expected_strategy_events_path)
    )
    needs_spawn_children = (
        expected_spawn_children_path
        and os.path.exists(expected_spawn_children_path)
    )
    attachment_store = _load_attachment_store(".")
    if not needs_deltas and not needs_strategy_events and not needs_spawn_children:
        session = run_session(
            manifest, script, inputs, streaming=streaming, attachment_store=attachment_store
        )
        return _serialize_log(session.log), [], [], session.metadata.get("tools", [])
    with tempfile.TemporaryDirectory(prefix="harnas-deltas") as tmp:
        delta_path = os.path.join(tmp, "session.deltas.jsonl")
        strategy_events_path = os.path.join(tmp, "session.strategy-events.jsonl")
        session = run_session(
            manifest,
            script,
            inputs,
            streaming=streaming,
            delta_path=delta_path if needs_deltas else None,
            attachment_store=attachment_store,
            strategy_events_path=strategy_events_path if needs_strategy_events else None,
        )
        if needs_spawn_children:
            _verify_spawn_children(session, expected_spawn_children_path)
        return (
            _serialize_log(session.log),
            _load_expected(delta_path) if needs_deltas else [],
            _load_expected(strategy_events_path) if needs_strategy_events else [],
            session.metadata.get("tools", []),
        )


def run_session(
    manifest: dict[str, Any],
    script: list,
    inputs: list[str],
    streaming: bool = False,
    session: Session | None = None,
    delta_path: str | None = None,
    strategy_events_path: str | None = None,
    attachment_store: Any | None = None,
) -> Session:
    registry = _build_registry(manifest.get("tools", []))
    projection, provider, ingestor = _build_pipeline(
        manifest, script, registry, streaming, attachment_store or _load_attachment_store(".")
    )
    runner = Runner(registry) if registry.size > 0 else None
    session = session or Session.create(metadata={
        "manifest_name": manifest["name"],
        "manifest": json.loads(json.dumps(manifest, ensure_ascii=False)),
    })
    session.metadata["tools"] = tool_descriptors(registry)
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

        if isinstance(input_item, dict) and "save_load" in input_item:
            with tempfile.TemporaryDirectory(prefix="harnas-save-load") as tmp:
                path = os.path.join(tmp, "session.jsonl")
                session.save(path)
                ids_before = [event.id for event in session.log]
                session = Session.load(path)
                ids_after = [event.id for event in session.log]
                if ids_before != ids_after:
                    raise RuntimeError(
                        f"event id preservation mismatch: before={ids_before} after={ids_after}"
                    )
                if _normalize(session.metadata.get("manifest")) != _normalize(manifest):
                    raise RuntimeError("manifest snapshot mismatch")
            continue

        if isinstance(input_item, dict) and "append_events" in input_item:
            for event in input_item["append_events"]:
                session.log.append(type=event["type"], payload=_normalize(event["payload"]))
            continue

        if isinstance(input_item, dict) and "content" in input_item:
            session.log.append(type="user_message", payload={"content": input_item["content"]})
        else:
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
            provider_kind=manifest["provider"]["kind"],
        ).run()
        if runner is not None and runner.child_sessions:
            session.metadata["spawn_child_sessions"] = runner.child_sessions

    return session


def _verify_spawn_children(session: Session, path: str) -> None:
    spec = json.loads(_read(path))
    spawn = next(
        (
            event for event in session.log
            if event.type == "agent_spawn" and event.payload.get("task") == spec["task"]
        ),
        None,
    )
    if spawn is None:
        raise RuntimeError(f"missing agent_spawn for task {spec['task']}")
    child_id = spawn.payload["child_session_id"]
    child = session.metadata.get("spawn_child_sessions", {}).get(child_id)
    if child is None:
        raise RuntimeError(f"missing child Session {child_id}")
    if (
        child.parent_session_id != session.id
        or child.spawn_id != spawn.payload["spawn_id"]
        or child.spawned_by_event_id != spawn.payload["spawned_by_event_id"]
    ):
        raise RuntimeError("child reciprocity mismatch")
    if not child.root_session_id or not child.delegation_chain:
        raise RuntimeError("child delegation metadata missing")
    first = child.log[0] if child.log.size else None
    if (
        first is None
        or first.type != "user_message"
        or first.payload.get("text") != spec["child_initial_user_text"]
    ):
        raise RuntimeError("child initial user_message mismatch")


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
    attachment_store: Any | None = None,
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
            model=model,
            max_tokens=max_tokens,
            system=system,
            registry=registry,
            attachment_store=attachment_store,
            provider_kind=kind,
            capabilities=manifest["provider"].get("capabilities", {}),
            capability_mismatch_behavior=manifest["provider"].get(
                "capability_mismatch_behavior", "metadata_fallback"
            ),
        )
        ingestor = AnthropicIngestor()
    elif kind == "openai":
        from ..projections.openai import OpenAI as OpenAIProjection
        from ..ingestors.openai import OpenAI as OpenAIIngestor
        projection = OpenAIProjection(
            model=model,
            system=system,
            registry=registry,
            attachment_store=attachment_store,
            provider_kind=kind,
            capabilities=manifest["provider"].get("capabilities", {}),
            capability_mismatch_behavior=manifest["provider"].get(
                "capability_mismatch_behavior", "metadata_fallback"
            ),
        )
        ingestor = OpenAIIngestor()
    elif kind == "gemini":
        from ..projections.gemini import Gemini as GeminiProjection
        from ..ingestors.gemini import Gemini as GeminiIngestor
        projection = GeminiProjection(
            model=model,
            system=system,
            registry=registry,
            attachment_store=attachment_store,
            provider_kind=kind,
            capabilities=manifest["provider"].get("capabilities", {}),
            capability_mismatch_behavior=manifest["provider"].get(
                "capability_mismatch_behavior", "metadata_fallback"
            ),
        )
        ingestor = GeminiIngestor()
    else:
        raise NotImplementedError(f"provider kind '{kind}' not yet implemented in the Python port")

    provider = ScriptedStreamProvider(script) if streaming else ScriptedProvider(script)
    return projection, provider, ingestor


def _load_attachment_store(directory: str):
    store = MemoryStore()
    path = os.path.join(directory, "attachments.json")
    if not os.path.exists(path):
        return store
    for spec in json.loads(_read(path)):
        with open(os.path.join(directory, spec["path"]), "rb") as fh:
            store.put(fh.read(), spec["media_type"])
    return store


def _build_registry(tools_spec: list[dict[str, Any]]) -> Registry:
    registry = Registry()
    for tool_def in tools_spec:
        handler_name = tool_def["handler"]
        handler = _tool_handler(handler_name)
        registry.register(Tool(
            name=tool_def["name"],
            description=tool_def["description"],
            input_schema=tool_def["input_schema"],
            handler=handler,
            config=_effective_tool_config(tool_def),
            handler_name=handler_name,
        ))
    return registry


def _tool_handler(handler_name: str):
    if handler_name == "harnas.builtin.load_skill":
        return _builtin_load_skill_handler()
    if handler_name in {
        "harnas.builtin.read_file",
        "harnas.builtin.write_file",
        "harnas.builtin.edit_file",
    }:
        return _builtin_handler(handler_name)
    if handler_name == "harnas.builtin.bash_session":
        return _builtin_bash_session_handler()
    if handler_name == "harnas.builtin.fetch_url":
        return _fixture_fetch_url_handler()
    return _conformance_stub_handler(handler_name)


def _builtin_handler(handler_name: str):
    from ..tools.builtin import handlers

    return handlers()[handler_name]


def _builtin_load_skill_handler():
    from ..tools.builtin import load_skill

    return load_skill


def _builtin_bash_session_handler():
    from ..tools.builtin import bash_session

    return bash_session


def _fixture_fetch_url_handler():
    def fetch_url(args: dict[str, Any]) -> str:
        if args.get("url") == "https://api.example.com/data":
            headers = args.get("headers") or {}
            if headers.get("Authorization") != "Bearer SECRET-DO-NOT-LOG":
                raise RuntimeError("fetch_url missing credential proxy Authorization header")
            return "fetched OK"
        encoded = json.dumps(args, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        return f"[conformance stub: harnas.builtin.fetch_url({encoded})]"

    return fetch_url


def _conformance_stub_handler(handler_name: str):
    """Returns a callable producing the normative conformance-stub
    output (spec/conformance/README.md): canonical compact JSON for
    the args.
    """
    def stub(args: dict[str, Any], *, config: dict[str, Any] | None = None) -> str:
        if handler_name == "conformance.raise_error":
            raise RuntimeError("conformance tool error")
        if handler_name == "conformance.echo_config":
            encoded_config = json.dumps(
                config or {},
                separators=(",", ":"),
                sort_keys=True,
                ensure_ascii=False,
            )
            return f"[conformance config: {encoded_config}]"
        encoded = json.dumps(args, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
        return f"[conformance stub: {handler_name}({encoded})]"
    return stub


def _resolve_fixture_paths(manifest: dict[str, Any], fixture_dir: str) -> dict[str, Any]:
    updated = copy.deepcopy(manifest)
    for tool in updated.get("tools", []):
        config = tool.get("config")
        if not isinstance(config, dict):
            continue
        skills_dir = config.get("skills_dir")
        if isinstance(skills_dir, str) and not os.path.isabs(skills_dir):
            config["skills_dir"] = os.path.abspath(os.path.join(fixture_dir, skills_dir))
        cwd = config.get("cwd")
        if isinstance(cwd, str) and not os.path.isabs(cwd):
            config["cwd"] = os.path.abspath(os.path.join(fixture_dir, cwd))
    return updated


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
        "conformance.audit_post_tool_use_variant": audit_post_tool_use,
        "conformance.raise_hook": raise_hook,
        "conformance.raise_hook_variant": raise_hook,
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
    return [
        _normalize({
            "seq": e.seq,
            "timestamp": e.timestamp,
            "type": e.type,
            "payload": e.payload,
        })
        for e in log
    ]


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
        if not _wildcard_match(a, e):
            return {"at_seq": i, "actual": a, "expected": e}
    return None


def _wildcard_match(actual: Any, expected: Any) -> bool:
    actual = _normalize_actual_for_expected(actual, expected)
    if "<generated>" not in json.dumps(expected, ensure_ascii=False):
        return actual == expected
    return _wildcard_value_match(actual, expected)


def _normalize_actual_for_expected(actual: Any, expected: Any) -> Any:
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return actual
    actual = dict(actual)
    if "timestamp" not in expected:
        actual.pop("timestamp", None)
    return actual


def _wildcard_value_match(actual: Any, expected: Any) -> bool:
    if expected == "<generated>":
        return actual is not None and actual != ""
    if isinstance(actual, dict) and isinstance(expected, dict):
        if sorted(actual.keys()) != sorted(expected.keys()):
            return False
        return all(_wildcard_value_match(actual[key], value) for key, value in expected.items())
    if isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            return False
        return all(_wildcard_value_match(a, e) for a, e in zip(actual, expected))
    return actual == expected


def _credential_proxy_secret_diff(actual: list[dict[str, Any]], fixture_dir: str) -> dict[str, Any] | None:
    if os.path.basename(fixture_dir.rstrip("/")) != "with-credential-proxy-injection":
        return None
    serialized = "\n".join(
        json.dumps(event, separators=(",", ":"), ensure_ascii=False)
        for event in actual
    )
    if "SECRET-DO-NOT-LOG" not in serialized:
        return None
    return {
        "at_seq": "redaction",
        "actual": "serialized log contains SECRET-DO-NOT-LOG",
        "expected": "serialized log must not contain SECRET-DO-NOT-LOG",
    }


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
