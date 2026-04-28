"""MarkerTail compaction strategy.

Mirrors `Harnas::Strategies::Compaction::MarkerTail`. Drops the
oldest (count - keep_recent) message events and replaces them with
a fixed marker string when message count exceeds max_messages.
"""

from __future__ import annotations

from ... import hooks as global_hooks
from ...actions import compact as compact_action
from ...compaction import helpers


class MarkerTail:
    DEFAULT_SUMMARY_FORMAT = "[snipped $N earlier messages]"

    @classmethod
    def install(
        cls,
        session=None,
        max_messages: int = 20,
        keep_recent: int = 10,
        summary_format: str = DEFAULT_SUMMARY_FORMAT,
    ):
        instance = cls(
            max_messages=max_messages,
            keep_recent=keep_recent,
            summary_format=summary_format,
        )
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_projection", instance.on_pre_projection)
        return instance.on_pre_projection

    def __init__(
        self,
        max_messages: int,
        keep_recent: int,
        summary_format: str = DEFAULT_SUMMARY_FORMAT,
    ):
        if not (
            isinstance(max_messages, int)
            and isinstance(keep_recent, int)
            and max_messages > keep_recent >= 0
        ):
            raise ValueError("max_messages must be > keep_recent >= 0")
        self._max_messages = max_messages
        self._keep_recent = keep_recent
        self._summary_format = summary_format

    def on_pre_projection(self, *, session) -> None:
        messages = helpers.message_events(session.log)
        if len(messages) <= self._max_messages:
            return

        candidate_seqs = [m.seq for m in messages[: len(messages) - self._keep_recent]]
        safe_seqs = helpers.tool_pair_safe_range(session.log, candidate_seqs)
        if not safe_seqs:
            return

        compact_action.call(
            session,
            replaces=safe_seqs,
            summary=self._summary_format.replace("$N", str(len(safe_seqs))),
        )
