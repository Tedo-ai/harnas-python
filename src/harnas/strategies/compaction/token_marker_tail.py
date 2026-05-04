"""TokenMarkerTail compaction strategy."""

from __future__ import annotations

from ... import hooks as global_hooks
from ...actions import compact as compact_action
from ...compaction import helpers
from ..observation import observe_strategy


class TokenMarkerTail:
    DEFAULT_SUMMARY_FORMAT = "[compacted $N earlier messages (~$E tokens -> threshold $T)]"

    @classmethod
    def install(
        cls,
        session=None,
        max_tokens: int = 100_000,
        threshold: float = 0.85,
        keep_recent: int = 10,
        summary_format: str = DEFAULT_SUMMARY_FORMAT,
    ):
        instance = cls(
            max_tokens=max_tokens,
            threshold=threshold,
            keep_recent=keep_recent,
            summary_format=summary_format,
        )
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_projection", instance.on_pre_projection)
        return instance.on_pre_projection

    def __init__(
        self,
        *,
        max_tokens: int,
        threshold: float,
        keep_recent: int,
        summary_format: str = DEFAULT_SUMMARY_FORMAT,
    ) -> None:
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive int")
        if not isinstance(threshold, (int, float)) or threshold <= 0 or threshold > 1:
            raise ValueError("threshold must be in (0.0, 1.0]")
        if not isinstance(keep_recent, int) or keep_recent < 0:
            raise ValueError("keep_recent must be a non-negative int")
        self._max_tokens = max_tokens
        self._threshold = threshold
        self._keep_recent = keep_recent
        self._summary_format = summary_format

    def on_pre_projection(self, *, session) -> None:
        return observe_strategy(
            session,
            name="Compaction::TokenMarkerTail",
            hook_point="pre_projection",
            body=lambda: self._on_pre_projection(session=session),
        )

    def _on_pre_projection(self, *, session) -> None:
        messages = helpers.message_events(session.log)
        estimated = helpers.estimate_tokens(messages)
        trigger_tokens = int(self._max_tokens * self._threshold)
        if estimated <= trigger_tokens:
            return

        count = len(messages) - self._keep_recent
        if count <= 0:
            return
        candidate_seqs = [event.seq for event in messages[:count]]
        safe_seqs = helpers.tool_pair_safe_range(session.log, candidate_seqs)
        if not safe_seqs:
            return
        compact_action.call(
            session,
            replaces=safe_seqs,
            summary=(
                self._summary_format
                .replace("$N", str(len(safe_seqs)))
                .replace("$E", str(estimated))
                .replace("$T", str(trigger_tokens))
            ),
        )
