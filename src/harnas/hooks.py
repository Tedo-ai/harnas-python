"""Hooks — bidirectional intervention bus.

Mirrors `Harnas::Hooks`. Module-level handler registry keyed by
hook point (a string in Python; Symbol in Ruby). With no handlers
registered for a point, invoke returns an empty list.
"""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Callable

_handlers: dict[str, list[Callable]] = defaultdict(list)


def on(point: str, handler: Callable) -> Callable:
    _handlers[point].append(handler)
    return handler


def off(point: str, handler: Callable) -> None:
    if point in _handlers and handler in _handlers[point]:
        _handlers[point].remove(handler)


def invoke(point: str, **ctx: Any) -> list:
    returns = []
    for handler in list(_handlers.get(point, [])):
        try:
            r = handler(**ctx)
        except Exception:  # noqa: BLE001
            continue
        if r is not None:
            returns.append(r)
    return returns


def reset() -> None:
    _handlers.clear()


@contextmanager
def scoped():
    """Snapshot the registry, run the block, restore on exit."""
    saved = {k: list(v) for k, v in _handlers.items()}
    try:
        yield
    finally:
        _handlers.clear()
        for k, v in saved.items():
            _handlers[k] = list(v)


def handlers() -> dict[str, list[Callable]]:
    return dict(_handlers)
