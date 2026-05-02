"""Live OpenAI Chat Completions provider."""

from __future__ import annotations

from typing import Any, Callable

from .http import post_json

OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider:
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

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]:
        return post_json(
            self.endpoint,
            {
                "authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
                "accept": "application/json",
            },
            request,
            opener=self.opener,
        )
