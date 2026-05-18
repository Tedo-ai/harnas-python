"""Wall-clock session timeout guard."""

from __future__ import annotations

import time

from ... import hooks as global_hooks


class Timeout:
    @classmethod
    def install(cls, session=None, timeout_seconds: int | float = 1800):
        instance = cls(timeout_seconds)
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_projection", instance.on_pre_projection)
        return instance.on_pre_projection

    def __init__(self, timeout_seconds: int | float) -> None:
        self.timeout_seconds = float(timeout_seconds)
        self.started_at = time.monotonic()
        self.checks = 0

    def on_pre_projection(self, *, session, **_) -> None:
        self.checks += 1
        if self.timeout_seconds == 0 and self.checks == 1:
            return
        if time.monotonic() - self.started_at < self.timeout_seconds:
            return
        session.log.append(
            type="runtime_error",
            payload={
                "source": "strategy",
                "handler": "guard/timeout",
                "error_class": "Harnas::TimeoutGuard",
                "message": "timeout",
                "reason": "timeout",
                "terminal": True,
            },
        )
