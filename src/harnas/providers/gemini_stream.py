"""Live Gemini streaming provider."""

from __future__ import annotations

from typing import Any, Callable

from .errors import ProviderError
from .gemini import GEMINI_ENDPOINT_BASE
from .streaming import GeminiStreamState, run_stream


class GeminiStreamProvider:
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

    def __call__(self, request: dict[str, Any], emit: Callable[[dict[str, Any]], None]) -> None:
        model = request.get("model")
        if not isinstance(model, str) or model == "":
            raise ProviderError("Gemini request must include 'model'")
        body = dict(request)
        del body["model"]
        run_stream(
            f"{self.endpoint_base}/{model}:streamGenerateContent?alt=sse",
            {
                "x-goog-api-key": self.api_key,
                "content-type": "application/json",
                "accept": "text/event-stream",
            },
            body,
            GeminiStreamState(emit),
            opener=self.opener,
        )
