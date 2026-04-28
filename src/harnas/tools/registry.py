"""Tool Registry — name -> Tool, with iteration in registration order."""

from __future__ import annotations

from .tool import Tool


class Registry:
    def __init__(self) -> None:
        self._by_name: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._by_name:
            raise ValueError(f"tool already registered: {tool.name!r}")
        self._by_name[tool.name] = tool
        return tool

    def __getitem__(self, name: str) -> Tool:
        if name not in self._by_name:
            raise KeyError(f"tool not registered: {name!r}")
        return self._by_name[name]

    def __contains__(self, name: str) -> bool:
        return name in self._by_name

    @property
    def size(self) -> int:
        return len(self._by_name)

    @property
    def tools(self) -> list[Tool]:
        return list(self._by_name.values())
