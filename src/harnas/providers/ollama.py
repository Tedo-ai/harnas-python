"""Live Ollama provider using Ollama's OpenAI-compatible endpoint."""

from __future__ import annotations

import os
from typing import Any, Callable

from .http import post_json

OLLAMA_BASE_URL = "http://localhost:11434/v1"


def ollama_chat_endpoint(base_url: str | None = None) -> str:
    base = (base_url or os.environ.get("OLLAMA_BASE_URL") or OLLAMA_BASE_URL).rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


class OllamaProvider:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.endpoint = ollama_chat_endpoint(base_url)
        self.opener = opener

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]:
        return post_json(
            self.endpoint,
            {
                "content-type": "application/json",
                "accept": "application/json",
            },
            request,
            opener=self.opener,
        )

