"""HumanApproval permission strategy."""

from __future__ import annotations

from typing import Callable

from ... import hooks as global_hooks
from ...event import Event
from ..observation import observe_strategy


class HumanApproval:
    DEFAULT_DENIAL_REASON = "human declined"

    @classmethod
    def install(
        cls,
        session=None,
        *,
        prompt: Callable[[Event], bool],
        denial_reason: str = DEFAULT_DENIAL_REASON,
    ):
        instance = cls(prompt=prompt, denial_reason=denial_reason)
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_tool_use", instance.on_pre_tool_use)
        return instance.on_pre_tool_use

    def __init__(
        self,
        *,
        prompt: Callable[[Event], bool],
        denial_reason: str = DEFAULT_DENIAL_REASON,
    ) -> None:
        if not callable(prompt):
            raise ValueError("prompt must be callable")
        if not isinstance(denial_reason, str):
            raise ValueError("denial_reason must be a string")
        self._prompt = prompt
        self._denial_reason = denial_reason

    def on_pre_tool_use(self, *, tool_use, session=None, **_):
        if session is not None:
            return observe_strategy(
                session,
                name="Permission::HumanApproval",
                hook_point="pre_tool_use",
                body=lambda: self._approval_decision(tool_use),
            )
        return self._approval_decision(tool_use)

    def _approval_decision(self, tool_use):
        if self._prompt(tool_use):
            return {"allow": True}
        return {"allow": False, "reason": self._denial_reason}
