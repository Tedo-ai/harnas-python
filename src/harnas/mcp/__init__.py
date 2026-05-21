"""Model Context Protocol adapters for Harnas."""

from .client import Client, connect
from .content import flatten
from .errors import MCPError, StartupError, TimeoutError, TransportError
from .http_client import HttpClient
from .stdio_client import StdioClient
from .tool_adapter import from_mcp

__all__ = [
    "Client",
    "HttpClient",
    "MCPError",
    "StartupError",
    "StdioClient",
    "TimeoutError",
    "TransportError",
    "connect",
    "flatten",
    "from_mcp",
]

