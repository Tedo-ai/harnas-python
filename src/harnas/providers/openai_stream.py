"""Live OpenAI streaming provider."""

from __future__ import annotations

from typing import Any, Callable

from .openai import OPENAI_ENDPOINT
from .streaming import OpenAIStreamState, run_stream


class OpenAIStreamProvider:
    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = OPENAI_ENDPOINT,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.opener = opener

    def __call__(self, request: dict[str, Any], emit: Callable[[dict[str, Any]], None]) -> None:
        body = dict(request)
        body["stream"] = True
        run_stream(
            self.endpoint,
            {
                "authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
                "accept": "text/event-stream",
            },
            body,
            OpenAIStreamState(emit),
            opener=self.opener,
        )
