"""Hooks — bidirectional intervention bus.

Mirrors `Harnas::Hooks`. `Hooks` instances are scoped to a Session;
module-level functions remain as a backward-compatible process-global
registry for direct tests and ad-hoc use.
"""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Callable


class TurnFailed(Exception):
    """Raised internally when a fail_turn hook aborts the turn."""


class Hooks:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._metadata: dict[Callable, dict[str, Any]] = {}

    def on(
        self,
        point: str,
        handler: Callable,
        *,
        on_error: str = "isolate",
        name: str | None = None,
        source: str = "hook",
    ) -> Callable:
        self._handlers[point].append(handler)
        self._metadata[handler] = {
            "on_error": on_error,
            "name": name or getattr(handler, "__name__", handler.__class__.__name__),
            "source": source,
        }
        return handler

    def off(self, point: str, handler: Callable) -> None:
        if point in self._handlers and handler in self._handlers[point]:
            self._handlers[point].remove(handler)
        self._metadata.pop(handler, None)

    def invoke(self, point: str, **ctx: Any) -> list:
        returns = []
        for handler in list(self._handlers.get(point, [])):
            try:
                r = handler(**ctx)
            except Exception:  # noqa: BLE001
                self._handle_failure(handler, point, ctx)
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
        saved_metadata = dict(self._metadata)
        try:
            yield
        finally:
            self._handlers.clear()
            for k, v in saved.items():
                self._handlers[k] = list(v)
            self._metadata = dict(saved_metadata)

    def handlers(self) -> dict[str, list[Callable]]:
        return dict(self._handlers)

    def _handle_failure(self, handler: Callable, point: str, ctx: dict[str, Any]) -> None:
        metadata = self._metadata.get(handler, {})
        error = ctx.get("__error__")
        session = ctx.get("session")
        observation = getattr(session, "observation", None)
        if observation is not None:
            observation.emit(
                "hook_handler_failed",
                point=point,
                handler=metadata.get("name") or getattr(handler, "__name__", str(handler)),
            )
        if metadata.get("on_error") != "fail_turn":
            return
        # The active exception is available via sys.exc_info inside this handler.
        import sys

        exc = sys.exc_info()[1] or error or RuntimeError("hook handler failed")
        if session is not None:
            session.log.append(
                type="runtime_error",
                payload={
                    "source": metadata.get("source", "hook"),
                    "handler": metadata.get("name") or getattr(handler, "__name__", str(handler)),
                    "error_class": type(exc).__name__,
                    "message": str(exc),
                    "terminal": True,
                },
            )
        raise TurnFailed(str(exc)) from exc


_default = Hooks()


def on(point: str, handler: Callable, **metadata: Any) -> Callable:
    return _default.on(point, handler, **metadata)


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
