"""Provider error types."""

from __future__ import annotations


class ProviderError(Exception):
    """Base provider error."""


class HTTPError(ProviderError):
    def __init__(self, status: int, body: object) -> None:
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")


class ProviderStreamError(ProviderError):
    """A provider-signaled error inside an otherwise successful stream."""

    def __init__(
        self,
        provider: str,
        error_type: str,
        message: str,
        *,
        request_id: str = "",
        status: int = 0,
    ) -> None:
        self.provider = provider
        self.error_type = error_type
        self.request_id = request_id
        self.status = status
        suffix = f" (request_id={request_id})" if request_id else ""
        super().__init__(f"{provider} stream error {error_type}{suffix}: {message}")


class ProviderProtocolError(ProviderError):
    """A successful HTTP response that violates the provider stream protocol."""

    def __init__(self, provider: str, reason: str, message: str) -> None:
        self.provider = provider
        self.reason = reason
        super().__init__(f"{provider} stream protocol error: {message}")
