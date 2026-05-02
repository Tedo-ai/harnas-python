"""Provider retry policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    delay_ms: int = 0


class RetryPolicy:
    def __init__(
        self,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        retryable_http: set[int] | None = None,
        backoff_ms: Callable[[int], int] | None = None,
    ) -> None:
        if not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.max_attempts = max_attempts
        self.retryable_http = set(retryable_http or DEFAULT_RETRYABLE_HTTP)
        self.backoff_ms = backoff_ms or (lambda attempt: 250 * (2 ** (attempt - 1)))

    def decide(self, error: Exception, attempt: int) -> RetryDecision:
        if attempt >= self.max_attempts or not self.retryable(error):
            return RetryDecision(retry=False)
        return RetryDecision(retry=True, delay_ms=self.backoff_ms(attempt))

    def retryable(self, error: Exception) -> bool:
        status = getattr(error, "status", None)
        if status is not None:
            return status in self.retryable_http
        if isinstance(error, (TimeoutError, ConnectionError, OSError)):
            return True
        text = f"{type(error).__module__}.{type(error).__name__} {error}".lower()
        return any(
            marker in text
            for marker in (
                "connection reset",
                "connection refused",
                "timeout",
                "temporarily unavailable",
            )
        )
