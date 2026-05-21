"""Typed MCP adapter errors."""

from __future__ import annotations


class MCPError(Exception):
    """Base MCP adapter error."""


class TransportError(MCPError):
    """JSON-RPC transport failed."""


class StartupError(TransportError):
    """MCP subprocess could not be started."""


class TimeoutError(TransportError):
    """MCP request timed out."""

