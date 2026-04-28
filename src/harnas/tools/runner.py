"""Tool Runner — dispatches a :tool_use event and appends :tool_result.

Mirrors `Harnas::Tools::Runner`. Catches Exception from the tool
handler and records it as a failure ToolResult.
"""

from __future__ import annotations

from typing import Any

from ..log import Log
from .registry import Registry


class Runner:
    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    def run(self, tool_use_event, into_log: Log) -> None:
        payload = tool_use_event.payload
        try:
            tool = self._registry[payload["name"]]
            output = tool(payload.get("arguments") or {})
            into_log.append(
                type="tool_result",
                payload={
                    "tool_use_id": payload["id"],
                    "output": str(output),
                    "error": None,
                },
            )
        except Exception as e:  # noqa: BLE001 — mirrors Ruby's StandardError catch
            into_log.append(
                type="tool_result",
                payload={
                    "tool_use_id": payload["id"],
                    "output": None,
                    "error": f"{type(e).__name__}: {e}",
                },
            )
