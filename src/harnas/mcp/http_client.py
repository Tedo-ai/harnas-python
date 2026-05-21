"""JSON-RPC over HTTP POST MCP transport."""

from __future__ import annotations

from typing import Any
import json
import socket
import urllib.error
import urllib.request

from .client import ClientBehavior, DEFAULT_TIMEOUT, initialize_params, request_payload
from .content import flatten
from .errors import TimeoutError, TransportError


class HttpClient(ClientBehavior):
    def __init__(
        self,
        *,
        url: str,
        server_name: str,
        timeout: float = DEFAULT_TIMEOUT,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.server_name = server_name
        self.timeout = timeout
        self.headers = dict(headers or {})
        self._next_id = 1
        self.degraded = False
        self.degraded_error: Exception | None = None
        self._tools_cache: list[dict[str, Any]] | None = None

    def initialize_session(self) -> None:
        self._request("initialize", initialize_params())
        self._notify("notifications/initialized")

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        return list(result.get("tools") or [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if error := self._degraded_error():
            raise error
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        return flatten(result.get("content"))

    def close(self) -> None:
        return None

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        raw = self._post(request_payload(id=request_id, method=method, params=params))
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as error:
            raise TransportError(f"malformed JSON response: {error}") from error
        if response.get("error") is not None:
            raise TransportError(str(response["error"]))
        return dict(response.get("result") or {})

    def _notify(self, method: str) -> None:
        self._post(request_payload(id=None, method=method, params={}))

    def _post(self, payload: dict[str, Any]) -> str:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", **self.headers}
        request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status < 200 or response.status > 299:
                    raise TransportError(f"HTTP {response.status}: {response.read().decode('utf-8')}")
                return response.read().decode("utf-8")
        except socket.timeout as error:
            raise TimeoutError(str(error)) from error
        except urllib.error.HTTPError as error:
            raise TransportError(f"HTTP {error.code}: {error.read().decode('utf-8')}") from error
        except OSError as error:
            raise TransportError(f"MCP HTTP request failed: {error}") from error
