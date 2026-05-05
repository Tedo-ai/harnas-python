"""Tool — a registered, invocable capability with declared input shape."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Callable


@dataclass
class Tool:
    """Mirrors `Harnas::Tools::Tool`. The Registry treats anything
    with name / description / input_schema / __call__ as a tool, but
    this is the canonical shape."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., str]
    config: dict[str, Any] | None = None

    def __call__(self, arguments: dict[str, Any]) -> str:
        if _accepts_config(self.handler):
            return self.handler(arguments, config=self.config or {})
        return self.handler(arguments)


def _accepts_config(handler: Callable[..., Any]) -> bool:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return False
    return any(
        param.kind == inspect.Parameter.VAR_KEYWORD or name == "config"
        for name, param in signature.parameters.items()
    )
