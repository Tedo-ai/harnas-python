"""Convenience runtime assembly helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agent import Agent
from .agent_loop import DEFAULT_MAX_TURNS, AgentLoop
from . import manifest as manifest_loader
from .session import Session


@dataclass
class Runtime:
    loaded: manifest_loader.Loaded

    @classmethod
    def build(
        cls,
        *,
        manifest: str | dict[str, Any],
        session_path: str | None = None,
        resume: bool = False,
        metadata: dict[str, Any] | None = None,
        **options: Any,
    ) -> "Runtime":
        loaded = manifest_loader.load(manifest, **options)
        session = Session.load(session_path) if resume and session_path else loaded.session
        if metadata:
            session.metadata.update(metadata)
        loaded = loaded.with_session(session)
        return cls(loaded=loaded)

    @property
    def session(self) -> Session:
        return self.loaded.session

    @property
    def registry(self):
        return self.loaded.registry

    def runner(self):
        return self.loaded.runner()

    def loop(self, *, max_turns: int = DEFAULT_MAX_TURNS) -> AgentLoop:
        return AgentLoop(
            session=self.loaded.session,
            projection=self.loaded.projection,
            provider=self.loaded.provider,
            ingestor=self.loaded.ingestor,
            runner=self.loaded.runner(),
            max_turns=max_turns,
        )

    def agent(self, *, max_turns: int = DEFAULT_MAX_TURNS) -> Agent:
        return Agent(
            name=self.loaded.name,
            session=self.loaded.session,
            projection=self.loaded.projection,
            provider=self.loaded.provider,
            ingestor=self.loaded.ingestor,
            stream_provider=self.loaded.stream_provider,
            runner=self.loaded.runner() if self.loaded.registry.size > 0 else None,
            max_turns=max_turns,
        )

    def save(self, path: str) -> Session:
        return self.session.save(path)
