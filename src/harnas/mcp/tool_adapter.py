"""Translate MCP tool descriptors to Harnas manifest tools."""

from __future__ import annotations

from typing import Any


def from_mcp(mcp_tool: dict[str, Any], *, server_name: str) -> dict[str, Any]:
    original_name = str(mcp_tool["name"])
    return {
        "name": f"{server_name}.{original_name}",
        "description": str(mcp_tool.get("description") or ""),
        "input_schema": mcp_tool.get("inputSchema") or {},
        "handler": f"mcp_passthrough.{server_name}",
        "config": {
            "mcp_server_name": server_name,
            "mcp_tool_name": original_name,
        },
    }

