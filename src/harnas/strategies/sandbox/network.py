"""Tool-boundary network sandbox strategy."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from ... import hooks as global_hooks
from ...hooks import TurnFailed


class Network:
    NETWORK_TOOLS = {"fetch_url"}

    @classmethod
    def install(
        cls,
        session=None,
        allow: list[str] | None = None,
        deny: list[str] | None = None,
    ):
        instance = cls(allow=allow or [], deny=deny or [])
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_tool_use", instance.on_pre_tool_use)
        return instance.on_pre_tool_use

    def __init__(self, allow: list[str], deny: list[str]) -> None:
        self._allow = list(allow)
        self._deny = list(deny)
        self._consecutive_violations = 0

    def on_pre_tool_use(self, *, session, tool_use, **_: Any) -> dict[str, Any]:
        if tool_use.payload["name"] not in self.NETWORK_TOOLS:
            return {"allow": True}
        host = self._host((tool_use.payload.get("arguments") or {}).get("url"))
        if host is None:
            return {"allow": True}
        if self._allowed(host) and host not in self._deny:
            self._consecutive_violations = 0
            return {"allow": True}
        self._consecutive_violations += 1
        if self._consecutive_violations >= 3:
            session.log.append(
                type="runtime_error",
                payload={
                    "source": "strategy",
                    "handler": "sandbox/network",
                    "error_class": "Harnas::SandboxViolation",
                    "message": "sandbox_network_violation_limit",
                    "reason": "sandbox_network_violation_limit",
                    "terminal": True,
                },
            )
            raise TurnFailed("sandbox_network_violation_limit")
        return {"allow": False, "reason": self._message(host)}

    def _host(self, value: Any) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return urlparse(value).hostname
        except ValueError:
            return None

    def _allowed(self, host: str) -> bool:
        return not self._allow or host in self._allow

    def _message(self, host: str) -> str:
        return (
            f"Network call to '{host}' is not permitted. "
            f"Allowed hosts: {self._format(self._allow)}."
        )

    def _format(self, values: list[str]) -> str:
        return "[" + ", ".join(f"'{value}'" for value in values) + "]"
