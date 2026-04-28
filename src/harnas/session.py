"""Session — id + Log + metadata bundle."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from .log import Log


@dataclass
class Session:
    """Bundles a stable id with one Log and optional metadata.

    Mirrors `Harnas::Session`.
    """

    id: str
    log: Log = field(default_factory=Log)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, metadata: dict[str, Any] | None = None) -> "Session":
        return cls(id=f"ses_{uuid.uuid4()}", log=Log(), metadata=metadata or {})
