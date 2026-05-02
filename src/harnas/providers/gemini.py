"""Live Google Gemini generateContent provider."""

from __future__ import annotations

from typing import Any, Callable

from .errors import ProviderError
from .http import post_json

GEMINI_ENDPOINT_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider:
    def __init__(
        self,
        api_key: str,
        *,
        endpoint_base: str = GEMINI_ENDPOINT_BASE,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.api_key = api_key
        self.endpoint_base = endpoint_base
        self.opener = opener

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]:
        model = request.get("model")
        if not isinstance(model, str) or model == "":
            raise ProviderError("Gemini request must include 'model'")
        body = dict(request)
        del body["model"]
        return post_json(
            f"{self.endpoint_base}/{model}:generateContent",
            {
                "x-goog-api-key": self.api_key,
                "content-type": "application/json",
                "accept": "application/json",
            },
            body,
            opener=self.opener,
        )
