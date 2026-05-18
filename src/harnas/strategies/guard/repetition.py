"""Anti-loop repetition guard."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from ... import hooks as global_hooks


class Repetition:
    @classmethod
    def install(
        cls,
        session=None,
        max_consecutive_failures: int = 3,
        max_identical_calls: int = 5,
        max_consecutive_rejections: int = 3,
    ):
        instance = cls(max_consecutive_failures, max_identical_calls, max_consecutive_rejections)
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_tool_use", instance.on_pre_tool_use)
        target_hooks.on("post_tool_use", instance.on_post_tool_use)
        return instance.on_post_tool_use

    def __init__(
        self,
        max_consecutive_failures: int,
        max_identical_calls: int,
        max_consecutive_rejections: int,
    ) -> None:
        self.max_consecutive_failures = max_consecutive_failures
        self.max_identical_calls = max_identical_calls
        self.max_consecutive_rejections = max_consecutive_rejections
        self.consecutive_failures = 0
        self.consecutive_rejections = 0
        self.calls: dict[str, int] = defaultdict(int)

    def on_pre_tool_use(self, *, session, tool_use, **_: Any) -> None:
        key = self._call_key(tool_use)
        self.calls[key] += 1
        if self.calls[key] >= self.max_identical_calls:
            self._fire(session, "identical_calls", tool_use, self.calls[key])

    def on_post_tool_use(self, *, session, tool_use, tool_result, **_: Any) -> None:
        if tool_result is not None and tool_result.payload.get("error") is not None:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.max_consecutive_failures:
                self._fire(session, "consecutive_failures", tool_use, self.consecutive_failures)
        else:
            self.consecutive_failures = 0
        approval = (tool_result.payload.get("approval") or {}) if tool_result is not None else {}
        if approval.get("decision") == "rejected":
            self.consecutive_rejections += 1
            if self.consecutive_rejections >= self.max_consecutive_rejections:
                self._fire(session, "consecutive_rejections", tool_use, self.consecutive_rejections)
        else:
            self.consecutive_rejections = 0

    def _call_key(self, tool_use) -> str:
        args = json.dumps(tool_use.payload.get("arguments") or {}, separators=(",", ":"), sort_keys=True)
        return f"{tool_use.payload.get('name')}:{hashlib.sha256(args.encode()).hexdigest()}"

    def _fire(self, session, trigger: str, tool_use, count: int) -> None:
        session.log.append(
            type="runtime_error",
            payload={
                "source": "strategy",
                "handler": "guard/repetition",
                "error_class": "Harnas::RepetitionGuard",
                "message": "repetition_guard",
                "reason": "repetition_guard",
                "trigger": trigger,
                "tool": tool_use.payload.get("name"),
                "count": count,
                "terminal": True,
            },
        )
