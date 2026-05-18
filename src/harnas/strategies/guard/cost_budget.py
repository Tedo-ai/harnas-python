"""Token budget guard."""

from __future__ import annotations

from ... import hooks as global_hooks


class CostBudget:
    @classmethod
    def install(
        cls,
        session=None,
        max_input_tokens: int | None = None,
        max_output_tokens: int | None = None,
    ):
        instance = cls(max_input_tokens, max_output_tokens)
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_projection", instance.on_pre_projection)
        return instance.on_pre_projection

    def __init__(self, max_input_tokens: int | None, max_output_tokens: int | None) -> None:
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens

    def on_pre_projection(self, *, session, **_) -> None:
        input_tokens = 0
        output_tokens = 0
        for event in session.log:
            if event.type != "assistant_message":
                continue
            usage = event.payload.get("usage") or {}
            input_tokens += int(usage.get("input_tokens") or 0)
            output_tokens += int(usage.get("output_tokens") or 0)
        if (
            (self.max_input_tokens is None or input_tokens <= self.max_input_tokens)
            and (self.max_output_tokens is None or output_tokens <= self.max_output_tokens)
        ):
            return
        session.log.append(
            type="runtime_error",
            payload={
                "source": "strategy",
                "handler": "guard/cost_budget",
                "error_class": "Harnas::BudgetExceeded",
                "message": "budget_exceeded",
                "reason": "budget_exceeded",
                "input_tokens": input_tokens,
                "max_input_tokens": self.max_input_tokens,
                "output_tokens": output_tokens,
                "max_output_tokens": self.max_output_tokens,
                "terminal": True,
            },
        )
