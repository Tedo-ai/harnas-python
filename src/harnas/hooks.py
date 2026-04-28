"""Hooks — bidirectional intervention bus.

Mirrors `Harnas::Hooks`. `Hooks` instances are scoped to a Session;
module-level functions remain as a backward-compatible process-global
registry for direct tests and ad-hoc use.
"""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Callable

class Hooks:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def on(self, point: str, handler: Callable) -> Callable:
        self._handlers[point].append(handler)
        return handler

    def off(self, point: str, handler: Callable) -> None:
        if point in self._handlers and handler in self._handlers[point]:
            self._handlers[point].remove(handler)

    def invoke(self, point: str, **ctx: Any) -> list:
        returns = []
        for handler in list(self._handlers.get(point, [])):
            try:
                r = handler(**ctx)
            except Exception:  # noqa: BLE001
                continue
            if r is not None:
                returns.append(r)
        return returns

    def reset(self) -> None:
        self._handlers.clear()

    @contextmanager
    def scoped(self):
        """Snapshot the registry, run the block, restore on exit."""
        saved = {k: list(v) for k, v in self._handlers.items()}
        try:
            yield
        finally:
            self._handlers.clear()
            for k, v in saved.items():
                self._handlers[k] = list(v)

    def handlers(self) -> dict[str, list[Callable]]:
        return dict(self._handlers)


_default = Hooks()


def on(point: str, handler: Callable) -> Callable:
    return _default.on(point, handler)


def off(point: str, handler: Callable) -> None:
    _default.off(point, handler)


def invoke(point: str, **ctx: Any) -> list:
    return _default.invoke(point, **ctx)


def reset() -> None:
    _default.reset()


@contextmanager
def scoped():
    with _default.scoped():
        yield


def handlers() -> dict[str, list[Callable]]:
    return _default.handlers()
