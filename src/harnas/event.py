"""Event — the canonical Log entry shape."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Event:
    """One entry in a Log.

    Mirrors `Harnas::Event` (Ruby Data class). `type` is a string in
    the canonical Log vocabulary (e.g. "user_message", "tool_use").
    """

    seq: int
    id: str
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
