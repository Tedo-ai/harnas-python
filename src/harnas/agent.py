"""Agent facade for driving a Session through AgentLoop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .agent_loop import DEFAULT_MAX_TURNS, AgentLoop
from . import manifest as manifest_loader
from .session import Session


@dataclass(frozen=True)
class Response:
    text: str
    stop_reason: str | None
    usage: dict[str, Any]
    log: Any


class Agent:
    def __init__(
        self,
        *,
        name: str,
        session: Session,
        projection: Callable[[Any], dict[str, Any]],
        provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        ingestor: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None,
        stream_provider: Callable[[dict[str, Any], Callable[[dict[str, Any]], None]], None] | None = None,
        runner: Any | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> None:
        self.name = name
        self.session = session
        self.projection = projection
        self.provider = provider
        self.ingestor = ingestor
        self.stream_provider = stream_provider
        self.runner = runner
        self.max_turns = max_turns

    @classmethod
    def from_manifest(
        cls,
        source: str | dict[str, Any],
        *,
        api_keys: dict[str, str | None] | None = None,
        tool_handlers: dict[str, Callable[[dict[str, Any]], str]] | None = None,
        strategy_handlers: dict[str, Callable[..., Any]] | None = None,
        providers: dict[str, Callable[..., Any]] | None = None,
        stream_providers: dict[str, Callable[..., Any]] | None = None,
    ) -> "Agent":
        loaded = manifest_loader.load(
            source,
            api_keys=api_keys,
            tool_handlers=tool_handlers,
            strategy_handlers=strategy_handlers,
            providers=providers,
            stream_providers=stream_providers,
        )
        loaded.install_strategies()
        return cls(
            name=loaded.name,
            session=loaded.session,
            projection=loaded.projection,
            provider=loaded.provider,
            ingestor=loaded.ingestor,
            stream_provider=loaded.stream_provider,
            runner=loaded.runner() if loaded.registry.size > 0 else None,
            max_turns=DEFAULT_MAX_TURNS,
        )

    def chat(self, text: str) -> Response:
        self._append_user_message(text)
        AgentLoop(
            session=self.session,
            projection=self.projection,
            provider=self.provider,
            ingestor=self.ingestor,
            runner=self.runner,
            max_turns=self.max_turns,
        ).run()
        return self._build_response()

    def stream(self, text: str, on_delta: Callable[[Any], None] | None = None) -> Response:
        if self.stream_provider is None:
            return self.chat(text)

        self._append_user_message(text)
        AgentLoop(
            session=self.session,
            projection=self.projection,
            provider=self.provider,
            ingestor=self.ingestor,
            stream_provider=self.stream_provider,
            runner=self.runner,
            max_turns=self.max_turns,
            on_stream_event=on_delta,
        ).run()
        return self._build_response()

    def from_session(self, session: Session) -> "Agent":
        return self.__class__(
            name=self.name,
            session=session,
            projection=self.projection,
            provider=self.provider,
            ingestor=self.ingestor,
            stream_provider=self.stream_provider,
            runner=self.runner,
            max_turns=self.max_turns,
        )

    @property
    def log(self):
        return self.session.log

    def _append_user_message(self, text: str) -> None:
        self.session.log.append(type="user_message", payload={"text": text})

    def _build_response(self) -> Response:
        last = next(
            (event for event in self.session.log.reverse_each() if event.type == "assistant_message"),
            None,
        )
        if last is None:
            return Response(text="", stop_reason=None, usage={}, log=self.log)
        return Response(
            text=str(last.payload.get("text", "")),
            stop_reason=last.payload.get("stop_reason"),
            usage=last.payload.get("usage", {}),
            log=self.log,
        )
