"""Provider-carrier helpers for the two-layer Log model."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def carrier(
    *,
    destination: str,
    index: int,
    kind: str,
    wire: Any,
    canonical_refs: list[str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "carrier_destination": destination,
        "index": index,
        "kind": kind,
        "wire": wire,
    }
    if canonical_refs:
        out["canonical_refs"] = canonical_refs
    return out


def wire(carriers: Any, destination: str) -> Any | None:
    for raw in carriers or []:
        if not isinstance(raw, dict):
            continue
        if raw.get("carrier_destination") == destination and "wire" in raw:
            return deepcopy(raw["wire"])
    return None


def wires(carriers: Any, destination: str) -> list[Any] | None:
    value = wire(carriers, destination)
    return value if isinstance(value, list) else None


def part_wire(block: dict[str, Any], destination: str) -> dict[str, Any] | None:
    value = wire(block.get("provider_parts"), destination)
    return value if isinstance(value, dict) else None
