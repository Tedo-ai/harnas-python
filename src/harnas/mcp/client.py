"""Shared MCP client helpers and factory."""

from __future__ import annotations

from typing import Any, Callable, Protocol
import sys

PROTOCOL_VERSION = "2024-11-05"
CLIENT_NAME = "harnas-python"
CLIENT_VERSION = "0.19.4"
DEFAULT_TIMEOUT = 30.0


class Client(Protocol):
    server_name: str
    degraded: bool

    def initialize_session(self) -> None: ...
    def tools(self) -> list[dict[str, Any]]: ...
    def tool_handlers(self) -> dict[str, Callable[..., str]]: ...
    def call_tool(self, name: str, arguments: dict[str, Any]) -> str: ...
    def close(self) -> None: ...


class ClientBehavior:
    server_name: str
    degraded: bool
    degraded_error: Exception | None
    _tools_cache: list[dict[str, Any]] | None

    def tools(self) -> list[dict[str, Any]]:
        if self._tools_cache is not None:
            return list(self._tools_cache)
        try:
            self.initialize_session()
            from .tool_adapter import from_mcp

            self._tools_cache = [
                from_mcp(tool, server_name=self.server_name)
                for tool in self.list_tools()
            ]
            return list(self._tools_cache)
        except Exception as error:  # noqa: BLE001 - degraded startup is intentional
            self.degraded = True
            self.degraded_error = error
            self._tools_cache = []
            print(
                f"Harnas MCP {self.server_name} degraded: {type(error).__name__}: {error}",
                file=sys.stderr,
            )
            return []

    def tool_handlers(self) -> dict[str, Callable[..., str]]:
        def handler(arguments: dict[str, Any], config: dict[str, Any] | None = None) -> str:
            config = config or {}
            return self.call_tool(str(config["mcp_tool_name"]), arguments)

        return {f"mcp_passthrough.{self.server_name}": handler}

    def _degraded_error(self) -> Exception | None:
        if self.degraded:
            from .errors import TransportError

            return TransportError(
                f"MCP server {self.server_name!r} is in degraded state; tools were not loaded."
            )
        return None


def request_payload(*, id: int | None, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if id is not None:
        payload["id"] = id
    return payload


def initialize_params() -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
        "capabilities": {},
    }


def connect(
    server_name: str,
    *,
    url: str | None = None,
    command: str | None = None,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Client:
    if url is not None:
        from .http_client import HttpClient

        return HttpClient(url=url, server_name=server_name, headers=headers, timeout=timeout)
    if command is not None:
        from .stdio_client import StdioClient

        return StdioClient(command=command, args=args or [], server_name=server_name, env=env, timeout=timeout)
    raise ValueError("mcp.connect: must provide either url or command")
