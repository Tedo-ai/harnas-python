"""Agent Manifest loader for the Python Harnas implementation."""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .ingestors.anthropic import Anthropic as AnthropicIngestor
from .ingestors.gemini import Gemini as GeminiIngestor
from .ingestors.openai import OpenAI as OpenAIIngestor
from .projections.anthropic import Anthropic as AnthropicProjection
from .projections.gemini import Gemini as GeminiProjection
from .projections.openai import OpenAI as OpenAIProjection
from .session import Session
from .tools.registry import Registry
from .tools.runner import Runner
from .tools.tool import Tool

SUPPORTED_VERSIONS = {"0.1"}
PROVIDER_KINDS = {"anthropic", "openai", "gemini", "mock"}


class ManifestError(Exception):
    """Base class for manifest loading errors."""


class ValidationError(ManifestError):
    """Raised when a manifest violates the v0.1 schema shape."""


class UnsupportedVersionError(ManifestError):
    """Raised when harnas_version is not supported."""


class UnknownProviderError(ManifestError):
    """Raised when provider.kind is unknown."""


class UnknownStrategyError(ManifestError):
    """Raised when a canonical strategy name is not implemented."""


class UnresolvedHandlerError(ManifestError):
    """Raised when a tool or strategy handler cannot be resolved."""


@dataclass
class Loaded:
    name: str
    session: Session
    projection: Callable[[Any], dict[str, Any]]
    provider: Callable[..., Any]
    ingestor: Callable[[dict[str, Any]], list[dict[str, Any]]]
    registry: Registry
    strategies: list["StrategyInstallation"]
    hooks: list["HookInstallation"]
    stream_provider: Callable[..., Any] | None = None

    def install_strategies(self) -> list[Any]:
        installed = [strategy.install(self.session) for strategy in self.strategies]
        installed.extend(hook.install(self.session) for hook in self.hooks)
        return installed

    def runner(self) -> Runner:
        return Runner(self.registry)

    def with_session(self, session: Session) -> "Loaded":
        return Loaded(
            name=self.name,
            session=session,
            projection=self.projection,
            provider=self.provider,
            ingestor=self.ingestor,
            registry=self.registry,
            strategies=self.strategies,
            hooks=self.hooks,
            stream_provider=self.stream_provider,
        )


@dataclass
class StrategyInstallation:
    klass: type
    config: dict[str, Any]
    name: str
    on_error: str = "isolate"

    def install(self, session: Session) -> Any:
        before = {
            point: list(handlers)
            for point, handlers in session.hooks.handlers().items()
        }
        result = self.klass.install(session, **self.config)
        added = _new_handlers(before, session.hooks.handlers())
        for point, handler in added:
            session.hooks.off(point, handler)
            session.hooks.on(
                point,
                handler,
                on_error=self.on_error,
                name=self.name,
                source="strategy",
            )
        return result


@dataclass
class HookInstallation:
    point: str
    handler: Callable[..., Any]
    name: str
    config: dict[str, Any]
    on_error: str = "isolate"

    def install(self, session: Session) -> Any:
        callable_handler = self._callable()
        return session.hooks.on(
            self.point,
            callable_handler,
            on_error=self.on_error,
            name=self.name,
            source="hook",
        )

    def _callable(self) -> Callable[..., Any]:
        def invoke(**ctx: Any) -> Any:
            return self.handler(**ctx, config=self.config)

        return invoke


def load(
    source: str | Path | dict[str, Any],
    *,
    tool_handlers: dict[str, Callable[[dict[str, Any]], str]] | None = None,
    strategy_handlers: dict[str, Callable[..., Any]] | None = None,
    api_keys: dict[str, str | None] | None = None,
    providers: dict[str, Callable[..., Any]] | None = None,
    stream_providers: dict[str, Callable[..., Any]] | None = None,
    hook_handlers: dict[str, Callable[..., Any]] | None = None,
) -> Loaded:
    manifest = parse_source(source)
    validate(manifest)
    registry = build_registry(manifest["tools"], tool_handlers or {})
    provider_bundle = build_provider(
        manifest["provider"],
        registry=registry,
        system=manifest.get("system"),
        api_keys=api_keys or {},
        providers=providers or {},
        stream_providers=stream_providers or {},
    )
    strategies = build_strategies(
        manifest["strategies"],
        strategy_handlers=strategy_handlers or {},
        provider_bundle=provider_bundle,
    )
    hooks = build_hooks(manifest.get("hooks", []), hook_handlers=hook_handlers or {})
    return Loaded(
        name=manifest["name"],
        session=Session.create(metadata={"manifest_name": manifest["name"]}),
        projection=provider_bundle["projection"],
        provider=provider_bundle["provider"],
        stream_provider=provider_bundle["stream_provider"],
        ingestor=provider_bundle["ingestor"],
        registry=registry,
        strategies=strategies,
        hooks=hooks,
    )


def parse_source(source: str | Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(source, dict):
        return json.loads(json.dumps(source))
    text = str(source)
    if text.lstrip().startswith("{") or "\n" in text:
        return json.loads(text)
    with open(text, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate(manifest: dict[str, Any]) -> None:
    _reject_unknown(manifest, {"harnas_version", "name", "system", "provider", "tools", "strategies", "hooks"}, "")
    _require(manifest, ["harnas_version", "name", "provider", "tools", "strategies"], "manifest")
    if manifest["harnas_version"] not in SUPPORTED_VERSIONS:
        raise UnsupportedVersionError(
            f"manifest version {manifest['harnas_version']!r} not in supported {sorted(SUPPORTED_VERSIONS)!r}"
        )
    if not isinstance(manifest["name"], str) or manifest["name"] == "":
        raise ValidationError("name must be a non-empty string")
    if "system" in manifest and (not isinstance(manifest["system"], str) or manifest["system"] == ""):
        raise ValidationError("system must be a non-empty string when present")
    _validate_provider(manifest["provider"])
    _validate_tools(manifest["tools"])
    _validate_strategies(manifest["strategies"])
    _validate_hooks(manifest.get("hooks", []))


def _validate_provider(provider: Any) -> None:
    if not isinstance(provider, dict):
        raise ValidationError("provider must be an object")
    _reject_unknown(provider, {"kind", "model", "max_tokens", "thinking_budget"}, "provider")
    _require(provider, ["kind", "max_tokens"], "provider")
    if provider["kind"] not in PROVIDER_KINDS:
        raise UnknownProviderError(f"unknown provider kind: {provider['kind']!r}")
    if provider["kind"] != "mock" and not provider.get("model"):
        raise ValidationError(f"provider.model is required for provider {provider['kind']!r}")
    if not isinstance(provider["max_tokens"], int) or provider["max_tokens"] < 1:
        raise ValidationError("provider.max_tokens must be an integer >= 1")


def _validate_tools(tools: Any) -> None:
    if not isinstance(tools, list):
        raise ValidationError("tools must be an array")
    seen: set[str] = set()
    for index, tool in enumerate(tools):
        if not isinstance(tool, dict):
            raise ValidationError(f"tools[{index}] must be an object")
        _reject_unknown(tool, {"name", "handler", "description", "input_schema"}, f"tools[{index}]")
        _require(tool, ["name", "handler", "description", "input_schema"], f"tools[{index}]")
        if not tool["name"]:
            raise ValidationError(f"tools[{index}].name must not be empty")
        if tool["name"] in seen:
            raise ValidationError(f"duplicate tool name: {tool['name']!r}")
        seen.add(tool["name"])
        if not tool["handler"]:
            raise ValidationError(f"tools[{index}].handler must not be empty")
        if not isinstance(tool["input_schema"], dict):
            raise ValidationError(f"tools[{index}].input_schema must be an object")


def _validate_strategies(strategies: Any) -> None:
    if not isinstance(strategies, list):
        raise ValidationError("strategies must be an array")
    for index, strategy in enumerate(strategies):
        if not isinstance(strategy, dict):
            raise ValidationError(f"strategies[{index}] must be an object")
        _reject_unknown(strategy, {"name", "config", "on_error"}, f"strategies[{index}]")
        _require(strategy, ["name"], f"strategies[{index}]")
        name = strategy["name"]
        if "::" not in name:
            raise ValidationError(f"strategy name {name!r} is not canonical")
        _validate_on_error(strategy.get("on_error", "isolate"), f"strategies[{index}].on_error")


def _validate_hooks(hooks: Any) -> None:
    if not isinstance(hooks, list):
        raise ValidationError("hooks must be an array")
    for index, hook in enumerate(hooks):
        if not isinstance(hook, dict):
            raise ValidationError(f"hooks[{index}] must be an object")
        _reject_unknown(hook, {"point", "handler", "config", "on_error"}, f"hooks[{index}]")
        _require(hook, ["point", "handler"], f"hooks[{index}]")
        if not isinstance(hook["point"], str) or not hook["point"]:
            raise ValidationError(f"hooks[{index}].point must be a non-empty string")
        if not isinstance(hook["handler"], str) or not hook["handler"]:
            raise ValidationError(f"hooks[{index}].handler must be a non-empty string")
        if "config" in hook and not isinstance(hook["config"], dict):
            raise ValidationError(f"hooks[{index}].config must be an object")
        _validate_on_error(hook.get("on_error", "isolate"), f"hooks[{index}].on_error")


def _validate_on_error(value: Any, label: str) -> None:
    if value not in {"isolate", "fail_turn"}:
        raise ValidationError(f"{label} must be 'isolate' or 'fail_turn'")


def _reject_unknown(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        prefix = f"{label}." if label else ""
        raise ValidationError(f"unknown field: {prefix}{unknown[0]}")


def _require(value: dict[str, Any], keys: list[str], label: str) -> None:
    for key in keys:
        if key not in value:
            raise ValidationError(f"{label} missing required field {key!r}")


def build_registry(
    tools_spec: list[dict[str, Any]],
    tool_handlers: dict[str, Callable[[dict[str, Any]], str]],
) -> Registry:
    registry = Registry()
    for tool_def in tools_spec:
        handler_name = tool_def["handler"]
        if handler_name not in tool_handlers:
            raise UnresolvedHandlerError(f"tool handler {handler_name!r} not in tool_handlers")
        registry.register(Tool(
            name=tool_def["name"],
            description=tool_def["description"],
            input_schema=tool_def["input_schema"],
            handler=tool_handlers[handler_name],
        ))
    return registry


def build_provider(
    provider_spec: dict[str, Any],
    *,
    registry: Registry,
    system: str | None,
    api_keys: dict[str, str | None],
    providers: dict[str, Callable[..., Any]],
    stream_providers: dict[str, Callable[..., Any]],
) -> dict[str, Any]:
    kind = provider_spec["kind"]
    projection = projection_for(provider_spec, registry, system)
    provider = provider_for(kind, api_keys, providers)
    stream_provider = stream_provider_for(kind, api_keys, stream_providers)
    ingestor = ingestor_for(kind)
    return {
        "projection": projection,
        "provider": provider,
        "stream_provider": stream_provider,
        "ingestor": ingestor,
    }


def projection_for(provider: dict[str, Any], registry: Registry | None, system: str | None):
    kind = provider["kind"]
    if kind in ("mock", "anthropic"):
        return AnthropicProjection(
            model=provider.get("model", "mock-test"),
            max_tokens=provider["max_tokens"],
            registry=registry,
            system=system,
        )
    if kind == "openai":
        return OpenAIProjection(model=provider["model"], registry=registry, system=system)
    if kind == "gemini":
        return GeminiProjection(
            model=provider["model"],
            registry=registry,
            system=system,
            thinking_budget=provider.get("thinking_budget", 0),
        )
    raise UnknownProviderError(f"unknown provider kind: {kind!r}")


def ingestor_for(kind: str):
    if kind in ("mock", "anthropic"):
        return AnthropicIngestor()
    if kind == "openai":
        return OpenAIIngestor()
    if kind == "gemini":
        return GeminiIngestor()
    raise UnknownProviderError(f"unknown provider kind: {kind!r}")


def provider_for(kind: str, api_keys: dict[str, str | None], providers: dict[str, Callable[..., Any]]):
    if kind in providers:
        return providers[kind]
    if kind == "mock":
        from .providers.mock import MockProvider
        return MockProvider()
    key = api_key_for(kind, api_keys)
    if not key:
        raise ManifestError(f"api_keys[{kind!r}] is required for provider {kind}")
    if kind == "anthropic":
        from .providers.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=key)
    if kind == "openai":
        from .providers.openai import OpenAIProvider
        return OpenAIProvider(api_key=key)
    if kind == "gemini":
        from .providers.gemini import GeminiProvider
        return GeminiProvider(api_key=key)
    raise UnknownProviderError(f"unknown provider kind: {kind!r}")


def stream_provider_for(
    kind: str,
    api_keys: dict[str, str | None],
    stream_providers: dict[str, Callable[..., Any]],
):
    if kind in stream_providers:
        return stream_providers[kind]
    if kind == "mock":
        return None
    key = api_key_for(kind, api_keys)
    if not key:
        raise ManifestError(f"api_keys[{kind!r}] is required for stream provider {kind}")
    if kind == "anthropic":
        from .providers.anthropic_stream import AnthropicStreamProvider
        return AnthropicStreamProvider(api_key=key)
    if kind == "openai":
        from .providers.openai_stream import OpenAIStreamProvider
        return OpenAIStreamProvider(api_key=key)
    if kind == "gemini":
        from .providers.gemini_stream import GeminiStreamProvider
        return GeminiStreamProvider(api_key=key)
    raise UnknownProviderError(f"unknown provider kind: {kind!r}")


def api_key_for(kind: str, explicit: dict[str, str | None]) -> str | None:
    return explicit.get(kind) or os.environ.get(f"{kind.upper()}_API_KEY")


STRATEGY_CLASSES = {
    "Compaction::MarkerTail": ("harnas.strategies.compaction.marker_tail", "MarkerTail"),
    "Compaction::ToolOutputCap": ("harnas.strategies.compaction.tool_output_cap", "ToolOutputCap"),
    "Compaction::TokenMarkerTail": ("harnas.strategies.compaction.token_marker_tail", "TokenMarkerTail"),
    "Compaction::SummaryTail": ("harnas.strategies.compaction.summary_tail", "SummaryTail"),
    "Permission::DenyByName": ("harnas.strategies.permission.deny_by_name", "DenyByName"),
    "Permission::AlwaysAllow": ("harnas.strategies.permission.always_allow", "AlwaysAllow"),
    "Permission::HumanApproval": ("harnas.strategies.permission.human_approval", "HumanApproval"),
}
CALLABLE_CONFIG_FIELDS = {"Permission::HumanApproval": ["prompt"]}
IMPLICIT_BUNDLE_FIELDS = {"Compaction::SummaryTail": ["projection", "provider", "ingestor"]}


def build_strategies(
    strategies_spec: list[dict[str, Any]],
    *,
    strategy_handlers: dict[str, Callable[..., Any]],
    provider_bundle: dict[str, Any],
) -> list[StrategyInstallation]:
    installations: list[StrategyInstallation] = []
    for strategy in strategies_spec:
        name = strategy["name"]
        if name not in STRATEGY_CLASSES:
            raise UnknownStrategyError(f"unknown canonical strategy: {name!r}")
        module_name, class_name = STRATEGY_CLASSES[name]
        module = importlib.import_module(module_name)
        klass = getattr(module, class_name)
        config = dict(strategy.get("config", {}))
        for field in CALLABLE_CONFIG_FIELDS.get(name, []):
            if field in config:
                handler_name = config[field]
                if handler_name not in strategy_handlers:
                    raise UnresolvedHandlerError(
                        f"strategy handler {handler_name!r} not in strategy_handlers"
                    )
                config[field] = strategy_handlers[handler_name]
        for field in IMPLICIT_BUNDLE_FIELDS.get(name, []):
            config[field] = provider_bundle[field]
        installations.append(
            StrategyInstallation(
                klass=klass,
                config=config,
                name=name,
                on_error=strategy.get("on_error", "isolate"),
            )
        )
    return installations


def build_hooks(
    hooks_spec: list[dict[str, Any]],
    *,
    hook_handlers: dict[str, Callable[..., Any]],
) -> list[HookInstallation]:
    installations: list[HookInstallation] = []
    for hook in hooks_spec:
        handler_name = hook["handler"]
        if handler_name not in hook_handlers:
            raise UnresolvedHandlerError(f"hook handler {handler_name!r} not in hook_handlers")
        installations.append(
            HookInstallation(
                point=hook["point"].removeprefix(":"),
                handler=hook_handlers[handler_name],
                name=handler_name,
                config=dict(hook.get("config", {})),
                on_error=hook.get("on_error", "isolate"),
            )
        )
    return installations


def _new_handlers(
    before: dict[str, list[Callable]],
    after: dict[str, list[Callable]],
) -> list[tuple[str, Callable]]:
    added: list[tuple[str, Callable]] = []
    for point, handlers in after.items():
        previous = before.get(point, [])
        for handler in handlers:
            if handler not in previous:
                added.append((point, handler))
    return added
