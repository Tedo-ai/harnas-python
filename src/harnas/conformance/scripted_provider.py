"""ScriptedProvider — returns pre-recorded responses in order.

Mirrors `Harnas::Conformance::ScriptedProvider`. Used by the
fixture runner to replay a deterministic stream of provider
responses into an AgentLoop.
"""

from __future__ import annotations

from typing import Any


class Exhausted(Exception):
    """Raised when the script has no more responses to deliver."""


class ProviderHTTPError(Exception):
    def __init__(self, status: int, body: Any) -> None:
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")


class RequestMismatch(Exception):
    """Raised when a fixture's expected request does not match."""


class ScriptedProvider:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def __call__(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self._responses:
            raise Exhausted("no more scripted responses")
        self.call_count += 1
        response = self._responses.pop(0)
        if "expect_request" in response:
            expected = _normalize(response["expect_request"])
            actual = _normalize(request)
            if actual != expected:
                raise RequestMismatch(
                    f"request does not match expected: {actual!r} != {expected!r}"
                )
            response = response["response"]
        if "error" in response:
            error = response["error"]
            raise ProviderHTTPError(error["status"], error["body"])
        return response


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value
