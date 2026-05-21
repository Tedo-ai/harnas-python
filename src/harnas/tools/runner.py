"""Tool Runner — dispatches a :tool_use event and appends :tool_result.

Mirrors `Harnas::Tools::Runner`. Catches Exception from the tool
handler and records it as a failure ToolResult.
"""

from __future__ import annotations

import json
import uuid
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
            if tool.handler_name == "harnas.builtin.spawn_agent":
                self._run_spawn_agent(tool_use_event, into_log)
                return
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

    def _run_spawn_agent(self, tool_use_event, into_log: Log) -> None:
        payload = tool_use_event.payload
        args = payload.get("arguments") or {}
        task = args.get("task")
        if not task:
            raise ValueError("missing required argument: task")
        spawn_id = f"spn_{uuid.uuid4()}"
        child_session_id = f"ses_{uuid.uuid4()}"
        metadata = {}
        if args.get("label"):
            metadata["label"] = args["label"]
        if args.get("role"):
            metadata["role"] = args["role"]
        overrides = {}
        if "tools_deny" in args:
            overrides["tools_deny"] = args["tools_deny"]
        into_log.append(
            type="agent_spawn",
            payload={
                "spawn_id": spawn_id,
                "child_session_id": child_session_id,
                "spawned_by_event_id": tool_use_event.id,
                "spawn_mode": "new",
                "task": task,
                "capabilities": {"inherit": True, "overrides": overrides},
                "join_policy": args.get("join_policy") or "async",
                "metadata": metadata,
                "retry_of_spawn_id": None,
            },
        )
        into_log.append(
            type="tool_result",
            payload={
                "tool_use_id": payload["id"],
                "output": json.dumps(
                    {
                        "spawn_id": spawn_id,
                        "child_session_id": child_session_id,
                        "status": "spawned",
                    },
                    separators=(",", ":"),
                ),
                "error": None,
            },
        )
