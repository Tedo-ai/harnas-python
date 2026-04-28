"""Tool — a registered, invocable capability with declared input shape."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    """Mirrors `Harnas::Tools::Tool`. The Registry treats anything
    with name / description / input_schema / __call__ as a tool, but
    this is the canonical shape."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], str]

    def __call__(self, arguments: dict[str, Any]) -> str:
        return self.handler(arguments)
