"""Tool-boundary write sandbox strategy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ... import hooks as global_hooks
from ...hooks import TurnFailed


class Write:
    DEFAULT_ALLOW = ["."]
    WRITE_TOOLS = {"write_file", "edit_file"}

    @classmethod
    def install(
        cls,
        session=None,
        allow: list[str] | None = None,
        deny: list[str] | None = None,
    ):
        instance = cls(allow=allow or cls.DEFAULT_ALLOW, deny=deny or [])
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_tool_use", instance.on_pre_tool_use)
        return instance.on_pre_tool_use

    def __init__(self, allow: list[str], deny: list[str]) -> None:
        self._allow_labels = list(allow)
        self._deny_labels = list(deny)
        self._allow = [self._normalize(path) for path in self._allow_labels]
        self._deny = [self._normalize(path) for path in self._deny_labels]
        self._consecutive_violations = 0

    def on_pre_tool_use(self, *, session, tool_use, **_: Any) -> dict[str, Any]:
        if tool_use.payload["name"] not in self.WRITE_TOOLS:
            return {"allow": True}
        path = (tool_use.payload.get("arguments") or {}).get("path")
        if not path:
            return {"allow": True}
        normalized = self._normalize(path)
        if self._allowed(normalized) and not self._denied(normalized):
            self._consecutive_violations = 0
            return {"allow": True}
        self._consecutive_violations += 1
        if self._consecutive_violations >= 3:
            session.log.append(
                type="runtime_error",
                payload={
                    "source": "strategy",
                    "handler": "sandbox/write",
                    "error_class": "Harnas::SandboxViolation",
                    "message": "sandbox_violation_limit",
                    "reason": "sandbox_violation_limit",
                    "terminal": True,
                },
            )
            raise TurnFailed("sandbox_violation_limit")
        return {"allow": False, "reason": self._message(path)}

    def _normalize(self, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            path = Path.cwd() / path
        return str(path.resolve(strict=False))

    def _allowed(self, path: str) -> bool:
        return any(path == prefix or path.startswith(prefix + "/") for prefix in self._allow)

    def _denied(self, path: str) -> bool:
        return any(path == prefix or path.startswith(prefix + "/") for prefix in self._deny)

    def _message(self, path: str) -> str:
        return (
            f"Write to '{path}' is not permitted. "
            f"Allowed paths: {self._format(self._allow_labels)}. "
            f"Denied paths: {self._format(self._deny_labels)}."
        )

    def _format(self, values: list[str]) -> str:
        return "[" + ", ".join(f"'{value}'" for value in values) + "]"
