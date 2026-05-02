"""Composable wrappers for tool handlers."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, TextIO

from ..log import Log

ToolHandler = Callable[[dict[str, Any]], str]


def timed(handler: ToolHandler, *, name: str | None = None) -> ToolHandler:
    def wrapped(args: dict[str, Any]) -> str:
        _ = (name, time.monotonic())
        return handler(args)

    return wrapped


def logged(
    handler: ToolHandler,
    *,
    name: str | None = None,
    io: TextIO | None = None,
    preview_bytes: int = 80,
) -> ToolHandler:
    output = io or sys.stderr
    label = name or "?"

    def wrapped(args: dict[str, Any]) -> str:
        print(f"[tool {label}] call args={_preview(args, preview_bytes)}", file=output)
        try:
            result = handler(args)
        except Exception as error:
            print(f"[tool {label}] err  {type(error).__name__}: {error}", file=output)
            raise
        print(f"[tool {label}] ok   result={_preview(result, preview_bytes)}", file=output)
        return result

    return wrapped


def retried(
    handler: ToolHandler,
    *,
    attempts: int = 3,
    on: tuple[type[BaseException], ...] = (Exception,),
    backoff_ms: Callable[[int], int] | None = None,
) -> ToolHandler:
    if not isinstance(attempts, int) or attempts < 1:
        raise ValueError("attempts must be >= 1")
    backoff = backoff_ms or (lambda attempt: 100 * (2 ** attempt))

    def wrapped(args: dict[str, Any]) -> str:
        attempt_index = 0
        while True:
            try:
                return handler(args)
            except on:
                attempt_index += 1
                if attempt_index >= attempts:
                    raise
                delay = backoff(attempt_index - 1)
                if delay > 0:
                    time.sleep(delay / 1000)

    return wrapped


class RateLimitExceeded(Exception):
    pass


class RateLimiter:
    def __init__(self, *, per_minute: int) -> None:
        if not isinstance(per_minute, int) or per_minute <= 0:
            raise ValueError("per_minute must be a positive int")
        self.per_minute = per_minute
        self._timestamps: list[float] = []

    def wrap(self, handler: ToolHandler) -> ToolHandler:
        def wrapped(args: dict[str, Any]) -> str:
            self._admit()
            return handler(args)

        return wrapped

    def _admit(self) -> None:
        now = time.monotonic()
        self._timestamps = [ts for ts in self._timestamps if ts >= now - 60]
        if len(self._timestamps) >= self.per_minute:
            raise RateLimitExceeded(f"rate limit: {self.per_minute} per minute")
        self._timestamps.append(now)


class StaleReadError(Exception):
    pass


class StaleReadGuard:
    ANNOTATION_KIND = "stale_read_guard.hash"

    def __init__(self, *, log: Log, strict: bool = True, require_read: bool = True) -> None:
        self.log = log
        self.strict = strict
        self.require_read = require_read

    def wrap_read(self, handler: ToolHandler) -> ToolHandler:
        def wrapped(args: dict[str, Any]) -> str:
            result = handler(args)
            path = args.get("path")
            if path:
                self._record_hash(str(path), _sha256(result))
            return result

        return wrapped

    def wrap_edit(self, handler: ToolHandler) -> ToolHandler:
        return self._wrap_mutating(handler, action="edit")

    def wrap_write(self, handler: ToolHandler) -> ToolHandler:
        return self._wrap_mutating(handler, action="write")

    def last_hash_for(self, path: str) -> str | None:
        for event in self.log.reverse_each():
            if event.type != "annotation":
                continue
            payload = event.payload
            if payload.get("kind") != self.ANNOTATION_KIND:
                continue
            data = payload.get("data") or {}
            if data.get("path") == path:
                return data.get("sha256")
        return None

    def known(self, path: str) -> bool:
        return self.last_hash_for(path) is not None

    def _wrap_mutating(self, handler: ToolHandler, *, action: str) -> ToolHandler:
        def wrapped(args: dict[str, Any]) -> str:
            path = args.get("path")
            if path:
                self._check_fresh(str(path), action=action)
            result = handler(args)
            if path and Path(str(path)).exists():
                self._record_hash(str(path), _sha256(Path(str(path)).read_text()))
            return result

        return wrapped

    def _record_hash(self, path: str, digest: str) -> None:
        self.log.append(
            type="annotation",
            payload={
                "kind": self.ANNOTATION_KIND,
                "data": {"path": path, "sha256": digest},
            },
        )

    def _check_fresh(self, path: str, *, action: str) -> None:
        previous = self.last_hash_for(path)
        if previous is None:
            if self.require_read:
                self._fire(path, action=action, reason="never_read")
            return
        current = _sha256(Path(path).read_text()) if Path(path).exists() else None
        if current != previous:
            self._fire(path, action=action, reason="drifted")

    def _fire(self, path: str, *, action: str, reason: str) -> None:
        if not self.strict:
            return
        if reason == "never_read":
            raise StaleReadError(
                f"StaleReadGuard: refuse to {action} {path} - never read; call read_file first"
            )
        raise StaleReadError(
            f"StaleReadGuard: refuse to {action} {path} - disk content drifted since the last read"
        )


def _preview(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else f"{text[:limit]}..."


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
