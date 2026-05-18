"""Live Ollama streaming provider using the OpenAI-compatible endpoint."""

from __future__ import annotations

from typing import Any, Callable

from .ollama import ollama_chat_endpoint
from .streaming import OpenAIStreamState, run_stream


class OllamaStreamProvider:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.endpoint = ollama_chat_endpoint(base_url)
        self.opener = opener

    def __call__(self, request: dict[str, Any], emit: Callable[[dict[str, Any]], None]) -> None:
        body = dict(request)
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
        run_stream(
            self.endpoint,
            {
                "content-type": "application/json",
                "accept": "text/event-stream",
            },
            body,
            OpenAIStreamState(emit),
            opener=self.opener,
        )

