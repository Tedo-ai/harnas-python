"""Live Anthropic Messages API provider."""

from __future__ import annotations

from typing import Any, Callable

from .http import post_json

ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


class AnthropicProvider:
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

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]:
        return post_json(
            self.endpoint,
            {
                "x-api-key": self.api_key,
                "anthropic-version": self.api_version,
                "content-type": "application/json",
                "accept": "application/json",
            },
            request,
            opener=self.opener,
        )
