"""Live Anthropic streaming provider."""

from __future__ import annotations

from typing import Any, Callable

from .anthropic import ANTHROPIC_API_VERSION, ANTHROPIC_ENDPOINT
from .streaming import AnthropicStreamState, run_stream


class AnthropicStreamProvider:
    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = ANTHROPIC_ENDPOINT,
        api_version: str = ANTHROPIC_API_VERSION,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.api_version = api_version
        self.opener = opener

    def __call__(self, request: dict[str, Any], emit: Callable[[dict[str, Any]], None]) -> None:
        body = dict(request)
        body["stream"] = True
        run_stream(
            self.endpoint,
            {
                "x-api-key": self.api_key,
                "anthropic-version": self.api_version,
                "content-type": "application/json",
                "accept": "text/event-stream",
            },
            body,
            AnthropicStreamState(emit),
            opener=self.opener,
        )
