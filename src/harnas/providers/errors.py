"""Provider error types."""

from __future__ import annotations


class ProviderError(Exception):
    """Base provider error."""


class HTTPError(ProviderError):
    def __init__(self, status: int, body: object) -> None:
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")
