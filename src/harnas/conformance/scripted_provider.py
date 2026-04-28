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


class ScriptedProvider:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def __call__(self, _request: dict[str, Any]) -> dict[str, Any]:
        if not self._responses:
            raise Exhausted("no more scripted responses")
        self.call_count += 1
        response = self._responses.pop(0)
        if "error" in response:
            error = response["error"]
            raise ProviderHTTPError(error["status"], error["body"])
        return response
