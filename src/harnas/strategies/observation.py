"""Observation helpers for strategy invocation."""

from __future__ import annotations

from typing import Any, Callable


def observe_strategy(
    session,
    *,
    name: str,
    hook_point: str,
    body: Callable[[], Any],
) -> Any:
    observation = session.observation
    observation.emit("strategy_started", name=name, hook_point=hook_point)
    before = len(session.log)
    try:
        result = body()
        if len(session.log) > before:
            effect = "mutated"
        elif isinstance(result, dict) and result.get("allow") is False:
            effect = "refused"
        else:
            effect = "noop"
        observation.emit(
            "strategy_completed",
            name=name,
            hook_point=hook_point,
            effect=effect,
        )
        return result
    except Exception:
        observation.emit(
            "strategy_completed",
            name=name,
            hook_point=hook_point,
            effect="error",
        )
        raise
